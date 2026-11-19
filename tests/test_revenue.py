from fastapi.testclient import TestClient

from deadinternet.api import create_app
from deadinternet.domain.experiment import Affiliate, Status
from tests.helpers import experiment, open_store


def test_revenue_route_raises_the_total_and_keeps_a_ledger(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(experiment(id="exp-1"))
    with TestClient(create_app(store)) as client:
        first = client.post(
            "/experiments/exp-1/revenue",
            json={"amount_cents": 250, "note": "tiktok payout"},
        )
        assert first.status_code == 200
        assert first.json()["revenue_cents"] == 250
        assert first.json()["entry"]["amount_cents"] == 250
        assert first.json()["entry"]["note"] == "tiktok payout"
        assert first.json()["entry"]["created_at"]

        second = client.post("/experiments/exp-1/revenue", json={"amount_cents": 100})
        assert second.status_code == 200
        assert second.json()["revenue_cents"] == 350

        ledger = client.get("/experiments/exp-1/revenue")
    assert ledger.status_code == 200
    entries = ledger.json()
    assert [entry["amount_cents"] for entry in entries] == [100, 250]
    assert [entry["note"] for entry in entries] == ["", "tiktok payout"]
    assert all(entry["experiment_id"] == "exp-1" for entry in entries)
    assert all(entry["created_at"] for entry in entries)
    assert store.get_experiment("exp-1").revenue_cents == 350


def test_revenue_for_an_unknown_experiment_is_404(tmp_path):
    store = open_store(tmp_path)
    with TestClient(create_app(store)) as client:
        posted = client.post("/experiments/exp-missing/revenue", json={"amount_cents": 10})
        listed = client.get("/experiments/exp-missing/revenue")
    assert posted.status_code == 404
    assert listed.status_code == 404


def test_revenue_amount_must_be_a_positive_whole_number_of_cents(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(experiment(id="exp-1"))
    with TestClient(create_app(store)) as client:
        for body in ({}, {"amount_cents": 0}, {"amount_cents": -5}, {"amount_cents": "many"}):
            response = client.post("/experiments/exp-1/revenue", json=body)
            assert response.status_code == 422, body
        ledger = client.get("/experiments/exp-1/revenue")
    assert ledger.status_code == 200
    assert ledger.json() == []
    assert store.get_experiment("exp-1").revenue_cents == 0


def test_results_show_the_recorded_revenue(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(experiment(id="exp-1"))
    store.insert_experiment(experiment(id="exp-2", money=Affiliate(tracking_code="def", merchant="acme")))
    with TestClient(create_app(store)) as client:
        assert client.post("/experiments/exp-1/revenue", json={"amount_cents": 250, "note": "tiktok"}).status_code == 200
        assert client.post("/experiments/exp-2/revenue", json={"amount_cents": 50, "note": "instagram"}).status_code == 200
        rows = client.get("/results").json()
    revenue = {row["id"]: row["revenue_cents"] for row in rows}
    assert revenue == {"exp-1": 250, "exp-2": 50}
    assert sum(revenue.values()) == 300


def test_suggest_ranks_the_richer_parent_above_the_click_heavy_one(tmp_path):
    store = open_store(tmp_path)
    store.upsert_theme("history", "History")
    store.upsert_niche("niche-1", "history", "Niche")
    store.upsert_presenter("presenter-1", "Alex", "heygen")
    store.upsert_voice("voice-1", "Nova", "eleven")
    store.upsert_hook("question", "Question")
    store.upsert_hook("result", "Result")
    store.upsert_offer("acme", "Acme", "https://example.test/acme", merchant="acme")
    store.insert_experiment(
        experiment(
            id="exp-clicks",
            status=Status.complete,
            clicks=9,
            money=Affiliate(tracking_code="abc", merchant="acme"),
        )
    )
    store.insert_experiment(
        experiment(
            id="exp-rich",
            status=Status.complete,
            clicks=0,
            money=Affiliate(tracking_code="def", merchant="acme"),
        )
    )
    # A third finished row in the same cell reaches the sample floor (US-027),
    # without which the honest ranker stays silent and suggests nothing.
    store.insert_experiment(
        experiment(
            id="exp-floor",
            status=Status.complete,
            clicks=1,
            money=Affiliate(tracking_code="ghi", merchant="acme"),
        )
    )
    with TestClient(create_app(store)) as client:
        before = client.post("/suggest").json()
        assert before[0]["parent_ids"] == ["exp-clicks"]

        payout = client.post(
            "/experiments/exp-rich/revenue",
            json={"amount_cents": 500, "note": "tiktok payout"},
        )
        assert payout.status_code == 200

        after = client.post("/suggest").json()
    assert after[0]["parent_ids"] == ["exp-rich"]
    assert store.get_experiment("exp-rich").revenue_cents == 500


def test_a_reversal_lowers_the_total_and_keeps_both_rows(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(experiment(id="exp-1"))
    with TestClient(create_app(store)) as client:
        mis_entered = client.post(
            "/experiments/exp-1/revenue",
            json={"amount_cents": 250, "note": "tiktok payout"},
        ).json()["entry"]
        assert client.post("/experiments/exp-1/revenue", json={"amount_cents": 100}).status_code == 200

        reversal = client.post(
            f"/experiments/exp-1/revenue/{mis_entered['id']}/reverse",
            json={"note": "typo: the payout was 25"},
        )
        assert reversal.status_code == 200
        payload = reversal.json()
        assert payload["revenue_cents"] == 100
        assert payload["entry"]["amount_cents"] == -250
        assert payload["entry"]["reverses_entry_id"] == mis_entered["id"]
        assert payload["entry"]["note"] == "typo: the payout was 25"
        assert payload["entry"]["created_at"]

        entries = client.get("/experiments/exp-1/revenue").json()
    # Newest first: the reversal, then the untouched payout, then the original.
    assert [entry["id"] for entry in entries] == [3, 2, mis_entered["id"]]
    assert [entry["amount_cents"] for entry in entries] == [-250, 100, 250]
    assert entries[0]["reverses_entry_id"] == mis_entered["id"]
    assert entries[1]["reverses_entry_id"] is None
    assert entries[2]["reverses_entry_id"] is None
    assert store.get_experiment("exp-1").revenue_cents == 100


def test_reversing_the_same_entry_twice_is_refused(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(experiment(id="exp-1"))
    with TestClient(create_app(store)) as client:
        entry = client.post(
            "/experiments/exp-1/revenue",
            json={"amount_cents": 250, "note": "tiktok payout"},
        ).json()["entry"]
        first = client.post(
            f"/experiments/exp-1/revenue/{entry['id']}/reverse",
            json={"note": "typo"},
        )
        assert first.status_code == 200

        second = client.post(
            f"/experiments/exp-1/revenue/{entry['id']}/reverse",
            json={"note": "again"},
        )
        assert second.status_code == 409
        # The refusal names the reversal that already corrected the entry.
        assert f"already reversed by entry {first.json()['entry']['id']}" in second.json()["detail"]

        entries = client.get("/experiments/exp-1/revenue").json()
    assert len(entries) == 2
    assert store.get_experiment("exp-1").revenue_cents == 0


def test_a_reversal_that_would_take_the_total_below_0_is_refused(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(experiment(id="exp-1"))
    with TestClient(create_app(store)) as client:
        entry = client.post(
            "/experiments/exp-1/revenue",
            json={"amount_cents": 250, "note": "tiktok payout"},
        ).json()["entry"]
        # A counter-only adjustment (add_revenue) leaves the total smaller
        # than the ledger entry; a full reversal must be refused.
        store.add_revenue("exp-1", -200)

        response = client.post(
            f"/experiments/exp-1/revenue/{entry['id']}/reverse",
            json={"note": "typo"},
        )
        assert response.status_code == 409
        assert "below 0" in response.json()["detail"]
    assert store.get_experiment("exp-1").revenue_cents == 50
    assert len(store.list_revenue_entries("exp-1")) == 1


def test_reversal_for_an_unknown_experiment_or_entry_is_404(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(experiment(id="exp-1"))
    store.insert_experiment(experiment(id="exp-2", money=Affiliate(tracking_code="def", merchant="acme")))
    with TestClient(create_app(store)) as client:
        entry = client.post(
            "/experiments/exp-1/revenue",
            json={"amount_cents": 250, "note": "tiktok payout"},
        ).json()["entry"]
        unknown_experiment = client.post(
            "/experiments/exp-missing/revenue/1/reverse",
            json={"note": "typo"},
        )
        unknown_entry = client.post(
            "/experiments/exp-1/revenue/999/reverse",
            json={"note": "typo"},
        )
        # An entry belongs to the experiment it was recorded under.
        other_experiment = client.post(
            f"/experiments/exp-2/revenue/{entry['id']}/reverse",
            json={"note": "typo"},
        )
    assert unknown_experiment.status_code == 404
    assert unknown_entry.status_code == 404
    assert other_experiment.status_code == 404
    assert store.get_experiment("exp-1").revenue_cents == 250
    assert store.get_experiment("exp-2").revenue_cents == 0


def test_a_reversal_needs_a_note(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(experiment(id="exp-1"))
    with TestClient(create_app(store)) as client:
        entry = client.post(
            "/experiments/exp-1/revenue",
            json={"amount_cents": 250, "note": "tiktok payout"},
        ).json()["entry"]
        for body in ({}, {"note": ""}, {"note": "   "}):
            response = client.post(
                f"/experiments/exp-1/revenue/{entry['id']}/reverse",
                json=body,
            )
            assert response.status_code == 422, body
        entries = client.get("/experiments/exp-1/revenue").json()
    assert len(entries) == 1
    assert store.get_experiment("exp-1").revenue_cents == 250


def test_a_reversal_row_cannot_itself_be_reversed(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(experiment(id="exp-1"))
    with TestClient(create_app(store)) as client:
        entry = client.post(
            "/experiments/exp-1/revenue",
            json={"amount_cents": 250, "note": "tiktok payout"},
        ).json()["entry"]
        reversal = client.post(
            f"/experiments/exp-1/revenue/{entry['id']}/reverse",
            json={"note": "typo"},
        ).json()["entry"]

        again = client.post(
            f"/experiments/exp-1/revenue/{reversal['id']}/reverse",
            json={"note": "undo the undo"},
        )
        assert again.status_code == 409
        assert "is a reversal, not a payout" in again.json()["detail"]
    assert store.get_experiment("exp-1").revenue_cents == 0
    assert len(store.list_revenue_entries("exp-1")) == 2

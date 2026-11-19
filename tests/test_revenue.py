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

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from deadinternet.api.app import create_app
from deadinternet.domain.experiment import Affiliate, FactorDiff, Status
from tests.helpers import experiment, open_store


def _seed(store) -> None:
    store.upsert_theme("history", "History")
    store.upsert_niche("niche-1", "history", "Niche")
    store.upsert_voice("voice-1", "Voice", "local")
    store.upsert_presenter("presenter-1", "Presenter", "local")
    store.upsert_hook("question", "Question")
    store.upsert_hook("result", "Result")
    store.upsert_offer("acme", "Acme", "https://example.test/acme", merchant="acme")


def test_flow_from_starter_grid_to_a_draft_proposal(tmp_path):
    store = open_store(tmp_path)
    _seed(store)
    client = TestClient(create_app(store))
    started = client.post(
        "/starter",
        json={
            "niche_ids": ["niche-1"],
            "money": {"kind": "affiliate", "tracking_code": "abc", "merchant": "acme"},
            "hook_id": "question",
            "voice_id": "voice-1",
            "presenter_id": "presenter-1",
        },
    )
    assert started.status_code == 200, started.text
    faceless = next(row for row in started.json() if row["style"]["kind"] == "faceless")
    avatar = next(row for row in started.json() if row["style"]["kind"] == "avatar")
    experiment_id = faceless["id"]
    board = client.post(f"/experiments/{experiment_id}/approve-board")
    assert board.status_code == 200, board.text
    assert board.json()["status"] == "board_approved"
    store.save_experiment(
        replace(
            store.get_experiment(avatar["id"]),
            money=Affiliate(tracking_code="other", merchant="acme"),
        )
    )

    rendered = client.post(f"/experiments/{experiment_id}/render")
    assert rendered.status_code == 200, rendered.text
    assert rendered.json()["status"] == "in_review"

    # Approve eight days ago: the 7-day measurement window is always already
    # closed, so the unforced complete below can never become a 409.
    approved_at = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    approved = client.post(
        f"/experiments/{experiment_id}/approve",
        json={"now": approved_at},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approved_at"] == approved_at

    posted = client.post(
        f"/experiments/{experiment_id}/publications",
        json={"platform": "youtube", "account_id": "acct-1", "token": None},
    )
    assert posted.status_code == 200, posted.text
    publication_id = posted.json()["id"]
    assert posted.json()["status"] == "manual_needed"

    pasted = client.post(
        f"/publications/{publication_id}/url",
        json={"url": "https://youtube.example/watch/1"},
    )
    assert pasted.status_code == 200, pasted.text
    assert pasted.json()["status"] == "posted"

    snapshot = client.post(
        "/snapshots",
        json={"publication_id": publication_id, "views": 10, "watch_time_seconds": 4},
    )
    assert snapshot.status_code == 200, snapshot.text

    click = client.get("/r/abc", follow_redirects=False)
    assert click.status_code == 302
    assert click.headers["location"] == "https://example.test/acme"

    closed = client.post(f"/experiments/{experiment_id}/complete")
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "complete"
    assert closed.json()["clicks"] == 1

    before = {row["id"] for row in client.get("/experiments").json()}
    # US-027: the one finished row sits in a cell below the sample floor, so
    # the honest ranker refuses to crown it and says why instead of
    # returning [] (which reads as "nothing to do").
    thin = client.post("/suggest")
    assert thin.status_code == 422, thin.text
    assert "3 completed videos" in thin.json()["detail"]
    # The refusal writes nothing.
    assert {row["id"] for row in client.get("/experiments").json()} == before

    # Give the cell its floor of finished rows; the ranker may speak again.
    store.insert_experiment(
        experiment(
            id="exp-seed-1",
            status=Status.complete,
            money=Affiliate(tracking_code="seed-1", merchant="acme"),
        )
    )
    store.insert_experiment(
        experiment(
            id="exp-seed-2",
            status=Status.complete,
            money=Affiliate(tracking_code="seed-2", merchant="acme"),
        )
    )
    before = {row["id"] for row in client.get("/experiments").json()}
    suggestion = client.post("/suggest")
    assert suggestion.status_code == 200, suggestion.text
    drafts = suggestion.json()
    assert len(drafts) == 1
    assert drafts[0]["parent_ids"] == [experiment_id]
    # US-027: one deliberate factor change per draft, never two.
    assert len(drafts[0]["factor_diffs"]) == 1
    after = {row["id"] for row in client.get("/experiments").json()}
    assert after == before

    # US-031: accepting the suggestion keeps its lineage. The stored factor
    # list is what the server derived from the parent, not the declared one.
    draft = drafts[0]
    accepted = client.post(
        "/experiments",
        json={
            "niche_id": draft["niche_id"],
            "hook_id": draft["hook_id"],
            "hypothesis": draft["hypothesis"],
            "script": draft["script"],
            "caption": draft["caption"],
            "length_sec": draft["length_sec"],
            "style": draft["style"],
            "money": draft["money"],
            "parent_ids": draft["parent_ids"],
            "factor_diffs": draft["factor_diffs"],
        },
    )
    assert accepted.status_code == 200, accepted.text
    child_id = accepted.json()["id"]
    child = store.get_experiment(child_id)
    assert child.parent_ids == (experiment_id,)
    assert child.factor_diffs == (
        FactorDiff(
            field="style",
            parent_value="faceless/stills/voice-1/bold",
            next_value="avatar/presenter-1/voice-1",
        ),
    )
    assert {row["id"] for row in client.get("/experiments").json()} == after | {child_id}
    suggested_files = list(tmp_path.rglob("*.mp4"))
    assert suggested_files == []

from dataclasses import replace

from fastapi.testclient import TestClient

from deadinternet.api.app import create_app
from deadinternet.domain.experiment import Affiliate
from tests.helpers import open_store


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

    approved = client.post(
        f"/experiments/{experiment_id}/approve",
        json={"now": "2026-10-31T12:00:00Z"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approved_at"] == "2026-10-31T12:00:00Z"

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
    suggestion = client.post("/suggest")
    assert suggestion.status_code == 200, suggestion.text
    drafts = suggestion.json()
    assert len(drafts) == 1
    assert len(drafts[0]["factor_diffs"]) >= 2
    after = {row["id"] for row in client.get("/experiments").json()}
    assert after == before
    suggested_files = list(tmp_path.rglob("*.mp4"))
    assert suggested_files == []

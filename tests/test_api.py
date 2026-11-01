from pathlib import Path

from fastapi.testclient import TestClient

from deadinternet.domain.experiment import (
    Affiliate,
    FacelessStyle,
    Look,
    Platform,
    PlatformPayout,
    Status,
)
from deadinternet.api import create_app
from tests.helpers import experiment, experiment_body, open_store

NOW = "2026-10-31T12:00:00Z"


class _SpyRenderer:
    def __init__(self):
        self.calls = []

    def render(self, experiment, media_dir):
        self.calls.append(experiment.id)
        folder = Path(media_dir)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{experiment.id}.mp4"
        target.write_bytes(b"video")
        return experiment


def test_approve_on_a_draft_returns_409(tmp_path):
    store = open_store(tmp_path)
    with TestClient(create_app(store)) as client:
        created = client.post("/experiments", json=experiment_body())
        assert created.status_code == 200
        assert created.json()["status"] == "draft"
        response = client.post("/experiments/exp-1/approve", json={"now": NOW})
        assert response.status_code == 409
        results = client.get("/results")
    assert store.get_experiment("exp-1").status == Status.draft
    assert results.status_code == 200
    row = results.json()[0]
    assert row["revenue_cents"] == 0
    assert row["clicks"] == 0
    assert row["below_sample_floor"] is True
    assert "winner" not in row


def test_approve_in_review_returns_approved(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(
        experiment(id="exp-review", status=Status.in_review, file_path="data/videos/exp-review.mp4")
    )
    with TestClient(create_app(store)) as client:
        response = client.post("/experiments/exp-review/approve", json={"now": NOW})
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["approved_at"] == NOW
    assert store.get_experiment("exp-review").status == Status.approved


def test_tiktok_rewards_under_a_minute_cannot_be_approved(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(
        experiment(
            id="exp-tt",
            status=Status.in_review,
            length_sec=45,
            file_path="data/videos/exp-tt.mp4",
            money=PlatformPayout(platform=Platform.tiktok),
            style=FacelessStyle(look=Look.stills, voice_id="voice-1", caption_style="bold"),
        )
    )
    with TestClient(create_app(store)) as client:
        response = client.post("/experiments/exp-tt/approve", json={"now": NOW})
    assert response.status_code == 422
    assert response.json()["detail"] == "TikTok Creator Rewards videos must be longer than 60 seconds"
    assert store.get_experiment("exp-tt").status == Status.in_review


def test_redirect_records_one_experiments_click(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(experiment(id="exp-a", money=Affiliate(tracking_code="code-a", merchant="acme")))
    store.insert_experiment(experiment(id="exp-b", money=Affiliate(tracking_code="code-b", merchant="other")))
    with TestClient(create_app(store)) as client:
        response = client.get("/r/code-a", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://example.test/acme"
    assert store.get_experiment("exp-a").clicks == 1
    assert store.get_experiment("exp-b").clicks == 0


def test_suggest_does_not_create_a_video_file(tmp_path):
    store = open_store(tmp_path)
    store.upsert_niche("niche-1", "Niche")
    store.upsert_presenter("presenter-1", "Alex", "heygen")
    store.upsert_voice("voice-1", "Nova", "eleven")
    store.upsert_hook("question", "Question")
    store.upsert_hook("result", "Result")
    store.upsert_offer("acme", "Acme", "https://example.test/acme", merchant="acme")
    store.insert_experiment(
        experiment(
            id="exp-parent",
            status=Status.complete,
            revenue_cents=500,
            clicks=4,
            money=Affiliate(tracking_code="abc", merchant="acme"),
        )
    )
    spy = _SpyRenderer()
    with TestClient(create_app(store, renderer=spy)) as client:
        response = client.post("/suggest")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert spy.calls == []
    assert [row.id for row in store.list_experiments()] == ["exp-parent"]
    assert list(tmp_path.rglob("*.mp4")) == []


def test_starter_inserts_drafts_without_rendering(tmp_path):
    store = open_store(tmp_path)
    spy = _SpyRenderer()
    with TestClient(create_app(store, renderer=spy)) as client:
        response = client.post(
            "/starter",
            json={
                "niche_ids": ["niche-1", "niche-2"],
                "money": {"kind": "affiliate", "tracking_code": "abc", "merchant": "acme"},
                "hook_id": "question",
                "voice_id": "voice-1",
                "presenter_id": "presenter-1",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 4
    assert {row["status"] for row in body} == {"draft"}
    assert [row["style"]["kind"] for row in body].count("faceless") == 2
    assert [row["style"]["kind"] for row in body].count("avatar") == 2
    assert spy.calls == []
    assert len(store.list_experiments()) == 4
    assert list(tmp_path.rglob("*.mp4")) == []


def test_render_reaches_review_and_the_cap_is_429(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(experiment(id="exp-render"))
    with TestClient(create_app(store)) as client:
        rendered = client.post("/experiments/exp-render/render")
        assert rendered.status_code == 200
        assert rendered.json()["status"] == "in_review"
        assert rendered.json()["file_path"].endswith("exp-render.mp4")
        again = client.post("/experiments/exp-render/render")
        assert again.status_code == 409
    assert store.get_experiment("exp-render").status == Status.in_review
    store.set_setting("render_cap", 0)
    store.insert_experiment(experiment(id="exp-capped"))
    with TestClient(create_app(store)) as client:
        capped = client.post("/experiments/exp-capped/render")
    assert capped.status_code == 429
    assert store.get_experiment("exp-capped").status == Status.draft


def test_publish_duplicate_url_and_manual_url(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(
        experiment(id="exp-post", status=Status.in_review, file_path="data/videos/exp-post.mp4")
    )
    with TestClient(create_app(store)) as client:
        approved = client.post("/experiments/exp-post/approve", json={"now": NOW})
        assert approved.status_code == 200
        first = client.post(
            "/experiments/exp-post/publications",
            json={"platform": "tiktok", "account_id": "acct-1", "token": "secret"},
        )
        second = client.post(
            "/experiments/exp-post/publications",
            json={"platform": "tiktok", "account_id": "acct-1", "token": "secret"},
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["status"] == "posted"
        assert second.json()["id"] == first.json()["id"]
        assert store.get_experiment("exp-post").status == Status.live
        assert len(store.list_publications("exp-post")) == 1

        store.insert_experiment(
            experiment(id="exp-manual", status=Status.in_review, file_path="data/videos/exp-manual.mp4")
        )
        manual_ready = client.post("/experiments/exp-manual/approve", json={"now": NOW})
        assert manual_ready.status_code == 200
        manual = client.post(
            "/experiments/exp-manual/publications",
            json={"platform": "instagram", "account_id": "acct-1", "token": None},
        )
        assert manual.status_code == 200
        assert manual.json()["status"] == "manual_needed"
        assert manual.json()["manual_pack"]["caption"] == "Watch this."
        assert store.get_experiment("exp-manual").status == Status.approved
        posted = client.post(
            f"/publications/{manual.json()['id']}/url",
            json={"url": "https://instagram.example/manual/1"},
        )
        assert posted.status_code == 200
        assert posted.json()["status"] == "posted"
        assert posted.json()["post_url"] == "https://instagram.example/manual/1"
    assert store.get_experiment("exp-manual").status == Status.live

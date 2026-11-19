import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from deadinternet.api import create_app
from deadinternet.api.app import _render_cap
from deadinternet.domain.experiment import (
    Affiliate,
    FacelessStyle,
    Look,
    Platform,
    PlatformPayout,
    PublicationStatus,
    Status,
    mark_rendered,
)
from tests.helpers import experiment, experiment_body, open_store

NOW = "2026-10-31T12:00:00Z"


def _series(store, niche_id="niche-1", theme_id="history", name="Series"):
    store.upsert_theme(theme_id, "History")
    store.upsert_niche(niche_id, theme_id, name)


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


class _SlowRenderer:
    """Stands in for ffmpeg: slow enough to expose concurrent renders."""

    def __init__(self, delay: float = 0.25):
        self.delay = delay
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def render(self, experiment, media_dir):
        with self._lock:
            self.calls.append(experiment.id)
        time.sleep(self.delay)
        folder = Path(media_dir)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{experiment.id}.mp4"
        target.write_bytes(b"video")
        return mark_rendered(experiment, str(target))


def test_approve_on_a_draft_returns_409(tmp_path):
    store = open_store(tmp_path)
    _series(store)
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
    store.upsert_offer("acme", "Acme", "https://acme.test/deal", merchant="acme")
    store.insert_experiment(experiment(id="exp-a", money=Affiliate(tracking_code="code-a", merchant="acme")))
    store.insert_experiment(experiment(id="exp-b", money=Affiliate(tracking_code="code-b", merchant="other")))
    with TestClient(create_app(store)) as client:
        response = client.get("/r/code-a", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://acme.test/deal"
    assert store.get_experiment("exp-a").clicks == 1
    assert store.get_experiment("exp-b").clicks == 0


def test_offer_url_saved_through_the_api_redirects_affiliate_clicks(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    store.insert_experiment(experiment(id="exp-a", money=Affiliate(tracking_code="code-a", merchant="acme")))
    with TestClient(create_app(store)) as client:
        saved = client.post(
            "/offers",
            json={"id": "acme", "url": "https://acme.example/deal"},
        )
        assert saved.status_code == 200
        assert saved.json()["url"] == "https://acme.example/deal"
        response = client.get("/r/code-a", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://acme.example/deal"
    assert store.get_experiment("exp-a").clicks == 1


def test_affiliate_click_without_a_saved_offer_url_returns_404(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    store.insert_experiment(experiment(id="exp-a", money=Affiliate(tracking_code="code-a", merchant="acme")))
    with TestClient(create_app(store)) as client:
        response = client.get("/r/code-a", follow_redirects=False)
    assert response.status_code == 404
    assert "acme" in response.json()["detail"]
    assert store.get_experiment("exp-a").clicks == 0


def test_offer_url_must_be_http(tmp_path):
    store = open_store(tmp_path)
    with TestClient(create_app(store)) as client:
        response = client.post("/offers", json={"id": "acme", "url": "ftp://acme.example"})
    assert response.status_code == 422


def test_conflicting_theme_recreation_is_refused(tmp_path):
    store = open_store(tmp_path)
    with TestClient(create_app(store)) as client:
        first = client.post("/themes", json={"id": "history", "name": "History", "language": "en"})
        assert first.status_code == 200
        same = client.post("/themes", json={"id": "history", "name": "History", "language": "en"})
        assert same.status_code == 200
        conflict = client.post("/themes", json={"id": "history", "name": "Past", "language": "fr"})
        assert conflict.status_code == 409
    theme = store.get_theme("history")
    assert (theme.name, theme.language) == ("History", "en")


def test_conflicting_niche_recreation_is_refused(tmp_path):
    store = open_store(tmp_path)
    with TestClient(create_app(store)) as client:
        created = client.post("/themes", json={"id": "history", "name": "History", "language": "en"})
        assert created.status_code == 200
        first = client.post("/niches", json={"id": "war", "theme_id": "history", "name": "War"})
        assert first.status_code == 200
        conflict = client.post("/niches", json={"id": "war", "theme_id": "history", "name": "Peace"})
        assert conflict.status_code == 409
        moved = client.post("/niches", json={"id": "war", "theme_id": "history", "name": "War"})
        assert moved.status_code == 200
    niche = store.get_niche("war")
    assert (niche.theme_id, niche.name) == ("history", "War")


def test_suggest_does_not_create_a_video_file(tmp_path):
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
    assert response.json()[0]["beats"][0]["spoken"] == response.json()[0]["script"]
    assert spy.calls == []
    assert [row.id for row in store.list_experiments()] == ["exp-parent"]
    assert list(tmp_path.rglob("*.mp4")) == []


def test_starter_inserts_drafts_without_rendering(tmp_path):
    store = open_store(tmp_path)
    _series(store, "niche-1")
    _series(store, "niche-2")
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
    assert len(list(tmp_path.rglob("*.storyboard.json"))) == 4
    assert list(tmp_path.rglob("*.mp4")) == []


def test_render_reaches_review_and_the_cap_is_429(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    with TestClient(create_app(store)) as client:
        created = client.post("/experiments", json=experiment_body(id="exp-render"))
        assert created.status_code == 200
        approved = client.post("/experiments/exp-render/approve-board")
        assert approved.status_code == 200
        rendered = client.post("/experiments/exp-render/render")
        assert rendered.status_code == 200
        assert rendered.json()["status"] == "in_review"
        file_path = rendered.json()["file_path"]
        assert "history" in file_path
        assert "niche-1" in file_path
        assert file_path.endswith("exp-render.mp4")
        again = client.post("/experiments/exp-render/render")
        assert again.status_code == 409
    assert store.get_experiment("exp-render").status == Status.in_review
    store.set_setting("render_cap", 0)
    with TestClient(create_app(store)) as client:
        created = client.post(
            "/experiments",
            json=experiment_body(
                id="exp-capped",
                money={"kind": "affiliate", "tracking_code": "code-capped", "merchant": "acme"},
            ),
        )
        assert created.status_code == 200
        assert client.post("/experiments/exp-capped/approve-board").status_code == 200
        capped = client.post("/experiments/exp-capped/render")
    assert capped.status_code == 429
    assert store.get_experiment("exp-capped").status == Status.board_approved


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
        assert manual.json()["manual_pack"]["experiment_id"] == "exp-manual"
        assert manual.json()["manual_pack"]["account_id"] == "acct-1"
        assert manual.json()["manual_pack"]["script"] == "Here is the spoken script."
        assert store.get_experiment("exp-manual").status == Status.approved
        posted = client.post(
            f"/publications/{manual.json()['id']}/url",
            json={"url": "https://instagram.example/manual/1"},
        )
        assert posted.status_code == 200
        assert posted.json()["status"] == "posted"
        assert posted.json()["post_url"] == "https://instagram.example/manual/1"
        listed = client.get("/experiments/exp-manual/publications")
        assert listed.status_code == 200
        assert listed.json()[0]["post_url"] == "https://instagram.example/manual/1"
    assert store.get_experiment("exp-manual").status == Status.live


def test_short_tiktok_draft_is_refused_and_catalog_records_ids(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    with TestClient(create_app(store)) as client:
        refused = client.post(
            "/experiments",
            json=experiment_body(
                id="exp-short",
                length_sec=45,
                money={"kind": "platform_payout", "platform": "tiktok"},
            ),
        )
        assert refused.status_code == 422
        created = client.post("/experiments", json=experiment_body())
        assert created.status_code == 200
        catalog = client.get("/catalog")
        assert catalog.status_code == 200
        body = catalog.json()
        assert body["niche_ids"] == ["niche-1"]
        assert body["voice_ids"] == ["voice-1"]
        assert body["hook_ids"] == ["question"]
        assert "acme" in body["offer_ids"]
        assert body["render_cap"] == 8
        blank = client.post(
            "/starter",
            json={
                "niche_ids": ["niche-1"],
                "money": {"kind": "affiliate", "tracking_code": "abc", "merchant": "acme"},
                "hook_id": " ",
                "voice_id": "voice-1",
                "presenter_id": "presenter-1",
            },
        )
        assert blank.status_code == 422
    assert store.get_experiment("exp-1").status == Status.draft


def test_tiktok_starter_is_long_enough_to_approve(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    with TestClient(create_app(store)) as client:
        started = client.post(
            "/starter",
            json={
                "niche_ids": ["niche-1"],
                "money": {"kind": "platform_payout", "platform": "tiktok"},
                "hook_id": "question",
                "voice_id": "voice-1",
                "presenter_id": "presenter-1",
            },
        )
    assert started.status_code == 200, started.text
    assert {row["length_sec"] for row in started.json()} == {75}
    assert "presenter-1" in store.catalog().presenter_ids


def test_media_serves_only_files_inside_the_media_dir(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    outside = tmp_path / "secret.mp4"
    outside.write_bytes(b"secret")
    store.insert_experiment(experiment(id="exp-out", status=Status.in_review, file_path=str(outside)))

    class _WritingRenderer:
        def render(self, row, media_dir):
            from deadinternet.domain.experiment import mark_rendered

            folder = Path(media_dir)
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"{row.id}.mp4"
            target.write_bytes(b"video")
            return mark_rendered(row, str(target))

    with TestClient(create_app(store, renderer=_WritingRenderer())) as client:
        hidden = client.get("/media/exp-out")
        assert hidden.status_code == 404
        assert (
            client.post(
                "/experiments",
                json=experiment_body(
                    id="exp-play",
                    money={"kind": "affiliate", "tracking_code": "code-play", "merchant": "acme"},
                ),
            ).status_code
            == 200
        )
        assert client.post("/experiments/exp-play/approve-board").status_code == 200
        rendered = client.post("/experiments/exp-play/render")
        assert rendered.status_code == 200
        played = client.get("/media/exp-play")
        assert played.status_code == 200
        assert played.content == b"video"
        missing = client.get("/media/missing")
        assert missing.status_code == 404


def test_results_report_views_from_the_latest_snapshots(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    with TestClient(create_app(store)) as client:
        assert client.post("/experiments", json=experiment_body(id="exp-views")).status_code == 200
        assert client.post("/experiments/exp-views/approve-board").status_code == 200
        assert client.post("/experiments/exp-views/render").status_code == 200
        assert client.post("/experiments/exp-views/approve", json={"now": NOW}).status_code == 200
        posted = client.post(
            "/experiments/exp-views/publications",
            json={"platform": "tiktok", "account_id": "acct-1", "token": "secret"},
        )
        assert posted.status_code == 200
        assert posted.json()["status"] == "posted"
        client.post("/snapshots", json={"publication_id": posted.json()["id"], "views": 100})
        client.post("/snapshots", json={"publication_id": posted.json()["id"], "views": 250})
        manual = client.post(
            "/experiments/exp-views/publications",
            json={"platform": "youtube", "account_id": "acct-1", "token": ""},
        )
        assert manual.json()["status"] == "manual_needed"
        assert client.post(
            f"/publications/{manual.json()['id']}/url",
            json={"url": "https://youtube.example/v/1"},
        ).status_code == 200
        plain = client.post(
            "/experiments",
            json=experiment_body(
                id="exp-plain",
                money={"kind": "affiliate", "tracking_code": "code-plain", "merchant": "acme"},
            ),
        )
        assert plain.status_code == 200
        rows = client.get("/results").json()
    by_id = {row["id"]: row for row in rows}
    assert by_id["exp-views"]["views"] == 250
    assert by_id["exp-plain"]["views"] == 0


def test_unknown_niche_and_a_draft_render_are_refused(tmp_path):
    store = open_store(tmp_path)
    with TestClient(create_app(store)) as client:
        missing = client.post("/experiments", json=experiment_body())
        assert missing.status_code == 422
        _series(store)
        created = client.post("/experiments", json=experiment_body())
        assert created.status_code == 200
        refused = client.post("/experiments/exp-1/render")
        assert refused.status_code == 409
    assert store.get_experiment("exp-1").status == Status.draft


def test_a_changed_storyboard_does_not_spend_a_render(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    with TestClient(create_app(store)) as client:
        assert client.post("/experiments", json=experiment_body()).status_code == 200
        assert client.post("/experiments/exp-1/approve-board").status_code == 200
        board = tmp_path / "media" / "history" / "niche-1" / "exp-1.storyboard.json"
        text = board.read_text(encoding="utf-8")
        board.write_text(text.replace("spoken script", "other script"), encoding="utf-8")
        refused = client.post("/experiments/exp-1/render")
        assert refused.status_code == 409
    assert store.get_experiment("exp-1").status == Status.draft
    assert store.get_experiment("exp-1").board_hash is None
    day = datetime.now(timezone.utc).date().isoformat()
    assert store.renders_started_today(day) == 0


def test_save_before_the_file_review_and_a_locked_board(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    beats = [
        {"spoken": "First line.", "on_screen": "One", "visual_note": "wide"},
        {"spoken": "Second line.", "on_screen": "", "visual_note": "close"},
    ]
    with TestClient(create_app(store)) as client:
        assert client.post("/experiments", json=experiment_body()).status_code == 200
        saved = client.put("/experiments/exp-1/storyboard", json={"beats": beats})
        assert saved.status_code == 200
        assert saved.json()["script"] == "First line.\nSecond line."
        assert saved.json()["status"] == "draft"
        assert client.post("/experiments/exp-1/approve-board").status_code == 200
        rendered = client.post("/experiments/exp-1/render")
        assert rendered.status_code == 200
        board = tmp_path / "media" / "history" / "niche-1" / "exp-1.storyboard.json"
        before = board.read_text(encoding="utf-8")
        locked = client.put(
            "/experiments/exp-1/storyboard",
            json={"beats": [{"spoken": "Too late.", "on_screen": "", "visual_note": ""}]},
        )
        assert locked.status_code == 409
        assert board.read_text(encoding="utf-8") == before


def test_duplicate_experiment_id_is_409_and_changes_nothing(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    with TestClient(create_app(store)) as client:
        first = client.post("/experiments", json=experiment_body())
        assert first.status_code == 200
        board = tmp_path / "media" / "history" / "niche-1" / "exp-1.storyboard.json"
        before = board.read_bytes()
        row_before = store.get_experiment("exp-1")
        second = client.post(
            "/experiments",
            json=experiment_body(hypothesis="A different take", script="A different script."),
        )
        assert second.status_code == 409
        assert board.read_bytes() == before
    assert store.get_experiment("exp-1") == row_before


@pytest.mark.parametrize(
    "bad_id", ["CON", "nul", "COM1", "lpt9", "a:b", "exp.", "tail ", "what?"]
)
def test_unsafe_experiment_ids_are_refused_with_nothing_written(tmp_path, bad_id):
    store = open_store(tmp_path)
    _series(store)
    with TestClient(create_app(store)) as client:
        response = client.post("/experiments", json=experiment_body(id=bad_id))
        assert response.status_code == 422
    assert store.list_experiments() == []
    assert list(tmp_path.rglob("*.storyboard.json")) == []


@pytest.mark.parametrize("bad_id", ["CON", "a:b", "name.", "sp "])
def test_unsafe_theme_and_niche_ids_are_refused(tmp_path, bad_id):
    store = open_store(tmp_path)
    with TestClient(create_app(store)) as client:
        theme = client.post("/themes", json={"id": bad_id, "name": "History"})
        assert theme.status_code == 422
        assert client.post("/themes", json={"id": "history", "name": "History"}).status_code == 200
        niche = client.post("/niches", json={"id": bad_id, "theme_id": "history", "name": "War"})
        assert niche.status_code == 422
    assert store.list_niches() == []


def test_manual_url_must_be_http_and_a_duplicate_is_409(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(
        experiment(id="exp-post", status=Status.in_review, file_path="data/videos/exp-post.mp4")
    )
    with TestClient(create_app(store)) as client:
        assert client.post("/experiments/exp-post/approve", json={"now": NOW}).status_code == 200
        first = client.post(
            "/experiments/exp-post/publications",
            json={"platform": "instagram", "account_id": "acct-1", "token": None},
        )
        second = client.post(
            "/experiments/exp-post/publications",
            json={"platform": "youtube", "account_id": "acct-1", "token": None},
        )
        assert first.status_code == 200
        assert second.status_code == 200
        refused = client.post(
            f"/publications/{first.json()['id']}/url",
            json={"url": "ftp://example.com/video"},
        )
        assert refused.status_code == 422
        blank = client.post(
            f"/publications/{first.json()['id']}/url",
            json={"url": "   "},
        )
        assert blank.status_code == 422
        assert {row["status"] for row in client.get("/experiments/exp-post/publications").json()} == {
            "manual_needed"
        }
        posted = client.post(
            f"/publications/{first.json()['id']}/url",
            json={"url": "https://instagram.example/v/1"},
        )
        assert posted.status_code == 200
        duplicate = client.post(
            f"/publications/{second.json()['id']}/url",
            json={"url": "https://instagram.example/v/1"},
        )
        assert duplicate.status_code == 409
    by_id = {row.id: row for row in store.list_publications("exp-post")}
    assert by_id[first.json()["id"]].post_url == "https://instagram.example/v/1"
    assert by_id[second.json()["id"]].status is PublicationStatus.manual_needed


def test_a_non_numeric_render_cap_falls_back_to_the_default(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    store.set_setting("render_cap", "banana")
    with TestClient(create_app(store)) as client:
        catalog = client.get("/catalog")
        assert catalog.status_code == 200
        assert catalog.json()["render_cap"] == 8
        assert client.post("/experiments", json=experiment_body(id="exp-cap")).status_code == 200
        assert client.post("/experiments/exp-cap/approve-board").status_code == 200
        rendered = client.post("/experiments/exp-cap/render")
        assert rendered.status_code == 200
    for raw in (None, "", "  ", "8x", {"n": 1}, [4]):
        store.set_setting("render_cap", raw)
        assert _render_cap(store) == 8, raw


def test_an_own_offer_experiment_without_a_url_is_refused(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    with TestClient(create_app(store)) as client:
        refused = client.post(
            "/experiments",
            json=experiment_body(
                id="exp-own",
                money={"kind": "own_offer", "tracking_code": "own-1", "offer_url": "  "},
            ),
        )
        assert refused.status_code == 422
    assert store.list_experiments() == []
    assert list(tmp_path.rglob("*.storyboard.json")) == []


def test_an_offer_with_a_blank_url_is_refused(tmp_path):
    store = open_store(tmp_path)
    with TestClient(create_app(store)) as client:
        response = client.post("/offers", json={"id": "acme", "url": "   "})
    assert response.status_code == 422
    assert store.get_offer("acme") is None


def test_a_tracking_code_already_used_by_another_experiment_is_refused(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    with TestClient(create_app(store)) as client:
        assert client.post("/experiments", json=experiment_body()).status_code == 200
        affiliate_dup = client.post(
            "/experiments",
            json=experiment_body(id="exp-aff", caption="Another affiliate cut."),
        )
        assert affiliate_dup.status_code == 422
        own_dup = client.post(
            "/experiments",
            json=experiment_body(
                id="exp-own",
                money={
                    "kind": "own_offer",
                    "tracking_code": "abc",
                    "offer_url": "https://shop.example/offer",
                },
            ),
        )
        assert own_dup.status_code == 422
    assert [row.id for row in store.list_experiments()] == ["exp-1"]
    assert list(tmp_path.rglob("*.storyboard.json")) == [
        tmp_path / "media" / "history" / "niche-1" / "exp-1.storyboard.json"
    ]


def test_concurrent_rends_cannot_overspend_the_cap(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    store.set_setting("render_cap", 1)
    renderer = _SlowRenderer()
    bodies = [
        experiment_body(
            id="exp-a",
            money={"kind": "affiliate", "tracking_code": "code-a", "merchant": "acme"},
        ),
        experiment_body(
            id="exp-b",
            money={"kind": "affiliate", "tracking_code": "code-b", "merchant": "acme"},
        ),
    ]
    with TestClient(create_app(store, renderer=renderer)) as client:
        for body in bodies:
            assert client.post("/experiments", json=body).status_code == 200
            assert client.post(f"/experiments/{body['id']}/approve-board").status_code == 200
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(client.post, f"/experiments/{body['id']}/render") for body in bodies
            ]
            codes = sorted(future.result().status_code for future in futures)
    assert codes == [200, 429]
    day = datetime.now(timezone.utc).date().isoformat()
    assert store.renders_started_today(day) == 1
    assert len(renderer.calls) == 1


def test_concurrent_rends_of_one_experiment_render_once(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    renderer = _SlowRenderer()
    with TestClient(create_app(store, renderer=renderer)) as client:
        assert (
            client.post(
                "/experiments",
                json=experiment_body(
                    id="exp-a",
                    money={"kind": "affiliate", "tracking_code": "code-a", "merchant": "acme"},
                ),
            ).status_code
            == 200
        )
        assert client.post("/experiments/exp-a/approve-board").status_code == 200
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(client.post, "/experiments/exp-a/render") for _ in range(2)]
            codes = sorted(future.result().status_code for future in futures)
    assert codes == [200, 409]
    assert renderer.calls == ["exp-a"]
    assert store.get_experiment("exp-a").status == Status.in_review

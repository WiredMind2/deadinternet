import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from deadinternet.api import create_app
from deadinternet.api.app import _clicks_window, _parse_iso, _render_cap
from deadinternet.domain.experiment import (
    Affiliate,
    FactorDiff,
    FacelessStyle,
    Look,
    Platform,
    PlatformPayout,
    PublicationStatus,
    Status,
    mark_rendered,
)
from tests.helpers import experiment, experiment_body, open_store
from tests.test_store import _LEGACY_EXPERIMENTS_SCHEMA, _legacy_row, _store as _registered_store

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


class _CrashingRenderer:
    """Stands in for an ffmpeg that dies mid-flight."""

    def render(self, experiment, media_dir):
        raise RuntimeError("boom while rendering")


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


def test_approve_with_an_unparseable_now_is_refused(tmp_path):
    """US-027: a bad clock would make the measurement window silently never
    close, so the approve route validates the timestamp it is given."""
    store = open_store(tmp_path)
    _series(store)
    store.insert_experiment(
        experiment(id="exp-review", status=Status.in_review, file_path="data/videos/exp-review.mp4")
    )
    with TestClient(create_app(store)) as client:
        response = client.post("/experiments/exp-review/approve", json={"now": "yesterday"})
    assert response.status_code == 422
    assert response.json()["detail"] == "now must be an ISO timestamp"
    assert store.get_experiment("exp-review").approved_at is None


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
    # The parent's cell needs three finished rows before suggest will use it.
    store.insert_experiment(
        experiment(
            id="exp-sib-1",
            status=Status.complete,
            money=Affiliate(tracking_code="sib-1", merchant="acme"),
        )
    )
    store.insert_experiment(
        experiment(
            id="exp-sib-2",
            status=Status.complete,
            money=Affiliate(tracking_code="sib-2", merchant="acme"),
        )
    )
    spy = _SpyRenderer()
    with TestClient(create_app(store, renderer=spy)) as client:
        response = client.post("/suggest")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["beats"][0]["spoken"] == response.json()[0]["script"]
    assert spy.calls == []
    assert [row.id for row in store.list_experiments()] == [
        "exp-parent",
        "exp-sib-1",
        "exp-sib-2",
    ]
    assert list(tmp_path.rglob("*.mp4")) == []


def test_suggest_without_an_eligible_parent_is_422_naming_the_floor(tmp_path):
    """US-027: with the proposer unset (the fallback path), a lone finished
    row is too thin to name a cause, and the operator is told why instead
    of reading an empty list as "nothing to do"."""
    store = open_store(tmp_path)
    _series(store)
    store.insert_experiment(experiment(id="exp-lone", status=Status.complete))
    with TestClient(create_app(store)) as client:
        response = client.post("/suggest")
    assert response.status_code == 422
    assert "3 completed videos" in response.json()["detail"]
    assert [row.id for row in store.list_experiments()] == ["exp-lone"]
    assert list(tmp_path.rglob("*.mp4")) == []


def test_an_accepted_draft_keeps_its_parent_and_derived_factor_list(tmp_path):
    """US-031: accepting a draft stores its lineage. The factor list is what
    the server derived from the parent with changed_factors, and the child's
    own tracking code never reads as a money change."""
    store = open_store(tmp_path)
    _series(store)
    store.insert_experiment(experiment(id="exp-parent"))
    with TestClient(create_app(store)) as client:
        created = client.post(
            "/experiments",
            json=experiment_body(
                id="exp-child",
                parent_ids=["exp-parent"],
                style={"kind": "avatar", "presenter_id": "presenter-1", "voice_id": "voice-1"},
                money={"kind": "affiliate", "tracking_code": "abc-c2", "merchant": "acme"},
            ),
        )
    assert created.status_code == 200, created.text
    assert created.json()["parent_ids"] == ["exp-parent"]
    assert created.json()["factor_diffs"] == [
        {
            "field": "style",
            "parent_value": "faceless/stills/voice-1/bold",
            "next_value": "avatar/presenter-1/voice-1",
        }
    ]
    stored = store.get_experiment("exp-child")
    assert stored.parent_ids == ("exp-parent",)
    assert stored.factor_diffs == (
        FactorDiff(
            field="style",
            parent_value="faceless/stills/voice-1/bold",
            next_value="avatar/presenter-1/voice-1",
        ),
    )


def test_a_declared_factor_list_is_advisory_only(tmp_path):
    """US-031: the body's declared diffs are never stored. The draft below
    claims a hook change; the server derives the style change it really made."""
    store = open_store(tmp_path)
    _series(store)
    store.insert_experiment(experiment(id="exp-parent"))
    with TestClient(create_app(store)) as client:
        created = client.post(
            "/experiments",
            json=experiment_body(
                id="exp-child",
                parent_ids=["exp-parent"],
                factor_diffs=[
                    {"field": "hook", "parent_value": "question", "next_value": "result"}
                ],
                style={"kind": "avatar", "presenter_id": "presenter-1", "voice_id": "voice-1"},
                money={"kind": "affiliate", "tracking_code": "abc-c2", "merchant": "acme"},
            ),
        )
    assert created.status_code == 200, created.text
    stored = store.get_experiment("exp-child")
    assert [diff.field for diff in stored.factor_diffs] == ["style"]
    assert stored.factor_diffs == (
        FactorDiff(
            field="style",
            parent_value="faceless/stills/voice-1/bold",
            next_value="avatar/presenter-1/voice-1",
        ),
    )


def test_an_unknown_parent_is_refused_with_nothing_written(tmp_path):
    """US-031: parent_ids are stored as given but validated; a name the lab
    does not know is a 422 naming it, and the refusal writes nothing."""
    store = open_store(tmp_path)
    _series(store)
    with TestClient(create_app(store)) as client:
        response = client.post(
            "/experiments",
            json=experiment_body(parent_ids=["exp-ghost"]),
        )
    assert response.status_code == 422
    assert response.json()["detail"] == "unknown parent exp-ghost"
    assert store.list_experiments() == []
    assert list(tmp_path.rglob("*.storyboard.json")) == []


def test_derived_diffs_name_every_moved_factor(tmp_path):
    """US-031: changed_factors names the five synthesis factors; a draft
    that moves four of them records each one's values on either side."""
    store = open_store(tmp_path)
    _series(store)
    _series(store, "niche-2")
    store.insert_experiment(
        experiment(
            id="exp-parent",
            money=PlatformPayout(platform=Platform.tiktok),
            length_sec=75,
        )
    )
    with TestClient(create_app(store)) as client:
        created = client.post(
            "/experiments",
            json=experiment_body(
                id="exp-child",
                parent_ids=["exp-parent"],
                niche_id="niche-2",
                hook_id="result",
                length_sec=45,
                money={"kind": "affiliate", "tracking_code": "abc-c2", "merchant": "acme"},
            ),
        )
    assert created.status_code == 200, created.text
    assert created.json()["factor_diffs"] == [
        {"field": "niche", "parent_value": "niche-1", "next_value": "niche-2"},
        {"field": "money", "parent_value": "platform_payout/tiktok", "next_value": "affiliate/acme"},
        {"field": "hook", "parent_value": "question", "next_value": "result"},
        {"field": "length", "parent_value": "75", "next_value": "45"},
    ]


def test_results_carry_lineage_for_rows_with_diffs(tmp_path):
    """US-031: Results can name the factor that moved only if the payload
    carries the stored lineage, so _experiment_json exposes both fields."""
    store = open_store(tmp_path)
    _series(store)
    store.insert_experiment(
        experiment(
            id="exp-child",
            parent_ids=("exp-parent",),
            factor_diffs=(FactorDiff(field="style", parent_value="faceless", next_value="avatar"),),
        )
    )
    with TestClient(create_app(store)) as client:
        rows = client.get("/results").json()
    row = next(item for item in rows if item["id"] == "exp-child")
    assert row["parent_ids"] == ["exp-parent"]
    assert row["factor_diffs"] == [
        {"field": "style", "parent_value": "faceless", "next_value": "avatar"}
    ]


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


def test_starter_gives_every_draft_a_distinct_code_across_niches(tmp_path):
    store = open_store(tmp_path)
    _series(store, "niche-1")
    _series(store, "niche-2")
    store.insert_experiment(
        experiment(id="exp-old", money=Affiliate(tracking_code="abc", merchant="acme"))
    )
    with TestClient(create_app(store)) as client:
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
    rows = response.json()
    assert len(rows) == 4
    codes = [row["money"]["tracking_code"] for row in rows]
    # Two niches, one grid: every draft is recoded away from the shared base
    # code and from each other. The stored experiment keeps "abc".
    assert sorted(codes) == ["abc-2", "abc-3", "abc-avatar", "abc-avatar-2"]
    for code in codes:
        assert store.add_click(code) == 1
    clicks = {row.id: row.clicks for row in store.list_experiments()}
    assert clicks["exp-old"] == 0
    assert sorted(clicks.values()) == [0, 1, 1, 1, 1]


def test_a_starter_grid_with_a_blank_tracking_code_is_refused(tmp_path):
    """US-024: a blank code would mint "-avatar"/"-avatar-2" drafts that
    credit nobody; affiliate and own-offer money must name its code."""
    store = open_store(tmp_path)
    _series(store)
    with TestClient(create_app(store)) as client:
        response = client.post(
            "/starter",
            json={
                "niche_ids": ["niche-1"],
                "money": {"kind": "affiliate", "tracking_code": "   ", "merchant": "acme"},
                "hook_id": "question",
                "voice_id": "voice-1",
                "presenter_id": "presenter-1",
            },
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "tracking_code is required"
    assert store.list_experiments() == []
    assert list(tmp_path.rglob("*.storyboard.json")) == []


def test_own_offer_money_without_a_web_url_is_refused_everywhere(tmp_path):
    """US-011: a click on /r/{code} opens the offer URL; a scheme the
    browser will not navigate counts a click and sends it nowhere."""
    store = open_store(tmp_path)
    _series(store)
    with TestClient(create_app(store)) as client:
        created = client.post(
            "/experiments",
            json=experiment_body(
                id="exp-js",
                money={"kind": "own_offer", "tracking_code": "js-1", "offer_url": "javascript:alert(1)"},
            ),
        )
        assert created.status_code == 422
        assert created.json()["detail"] == "own_offer offer_url must start with http:// or https://"
        starter = client.post(
            "/starter",
            json={
                "niche_ids": ["niche-1"],
                "money": {"kind": "own_offer", "tracking_code": "own-1", "offer_url": "   "},
                "hook_id": "question",
                "voice_id": "voice-1",
                "presenter_id": "presenter-1",
            },
        )
        assert starter.status_code == 422
        assert starter.json()["detail"] == "own_offer money needs an offer_url"
    assert store.list_experiments() == []


def test_a_tracking_code_that_cannot_be_a_url_segment_is_refused(tmp_path):
    """US-024: the code is the /r/{code} path segment; a space or a slash
    in it can never be hit, on either creation route."""
    store = open_store(tmp_path)
    _series(store)
    with TestClient(create_app(store)) as client:
        created = client.post(
            "/experiments",
            json=experiment_body(
                money={"kind": "affiliate", "tracking_code": "my code", "merchant": "acme"}
            ),
        )
        assert created.status_code == 422
        assert (
            created.json()["detail"]
            == "tracking_code must be letters, digits, dots, hyphens, or underscores"
        )
        starter = client.post(
            "/starter",
            json={
                "niche_ids": ["niche-1"],
                "money": {"kind": "affiliate", "tracking_code": "a/b", "merchant": "acme"},
                "hook_id": "question",
                "voice_id": "voice-1",
                "presenter_id": "presenter-1",
            },
        )
        assert starter.status_code == 422
        assert (
            starter.json()["detail"]
            == "tracking_code must be letters, digits, dots, hyphens, or underscores"
        )
    assert store.list_experiments() == []


def test_results_separate_windowed_clicks_from_the_total(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    now = datetime.now(timezone.utc)
    store.insert_experiment(
        experiment(
            id="exp-recent",
            status=Status.live,
            approved_at=now.isoformat(),
            money=Affiliate(tracking_code="recent", merchant="acme"),
        )
    )
    store.insert_experiment(
        experiment(
            id="exp-closed",
            status=Status.live,
            approved_at=(now - timedelta(days=30)).isoformat(),
            money=Affiliate(tracking_code="closed", merchant="acme"),
        )
    )
    store.insert_experiment(
        experiment(
            id="exp-plain",
            money=Affiliate(tracking_code="plain", merchant="acme"),
        )
    )
    for _ in range(2):
        store.add_click("recent")
        store.add_click("closed")
        store.add_click("plain")
    with TestClient(create_app(store)) as client:
        rows = client.get("/results").json()
    by_id = {row["id"]: row for row in rows}
    assert by_id["exp-recent"]["clicks"] == 2
    assert by_id["exp-recent"]["clicks_window"] == 2
    # The 7-day window closed 23 days ago: today's clicks sit outside it.
    assert by_id["exp-closed"]["clicks"] == 2
    assert by_id["exp-closed"]["clicks_window"] == 0
    # Never approved: no window has opened, so nothing is windowed yet.
    assert by_id["exp-plain"]["clicks"] == 2
    assert by_id["exp-plain"]["clicks_window"] == 0


def test_complete_inside_the_window_is_409_naming_the_end_unless_forced(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    approved_at = datetime.now(timezone.utc).isoformat()
    store.insert_experiment(
        experiment(id="exp-young", status=Status.live, approved_at=approved_at)
    )
    with TestClient(create_app(store)) as client:
        early = client.post("/experiments/exp-young/complete")
        assert early.status_code == 409
        assert "measurement window ends" in early.json()["detail"]
        assert store.get_experiment("exp-young").status is Status.live
        forced = client.post("/experiments/exp-young/complete", json={"force": True})
        assert forced.status_code == 200
        assert forced.json()["status"] == "complete"


def test_complete_after_the_window_or_without_approved_at_needs_no_body(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    now = datetime.now(timezone.utc)
    store.insert_experiment(
        experiment(
            id="exp-old",
            status=Status.live,
            approved_at=(now - timedelta(days=30)).isoformat(),
        )
    )
    store.insert_experiment(
        experiment(
            id="exp-clockless",
            status=Status.live,
            money=Affiliate(tracking_code="clockless", merchant="acme"),
        )
    )
    with TestClient(create_app(store)) as client:
        closed = client.post("/experiments/exp-old/complete")
        assert closed.status_code == 200
        assert closed.json()["status"] == "complete"
        clockless = client.post("/experiments/exp-clockless/complete")
        assert clockless.status_code == 200
        assert clockless.json()["status"] == "complete"


def test_the_first_post_stamps_the_window_anchor_on_the_server_clock(tmp_path):
    """US-035: the window anchor is the first posted publication, stamped by
    the server. A video approved a month ago but posted now is back inside
    its window: the anchor ignores the stale approval because the post is
    later, so the unforced complete refuses until the window really ends."""
    store = open_store(tmp_path)
    _series(store)
    store.insert_experiment(
        experiment(id="exp-post", status=Status.in_review, file_path="data/videos/exp-post.mp4")
    )
    with TestClient(create_app(store)) as client:
        month_old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        approved = client.post("/experiments/exp-post/approve", json={"now": month_old})
        assert approved.status_code == 200
        assert approved.json()["approved_at"] == month_old
        before = datetime.now(timezone.utc)
        posted = client.post(
            "/experiments/exp-post/publications",
            json={"platform": "tiktok", "account_id": "acct-1", "token": "secret"},
        )
        after = datetime.now(timezone.utc)
        assert posted.status_code == 200
        assert posted.json()["status"] == "posted"
        stored = store.get_experiment("exp-post")
        stamped = _parse_iso(stored.first_posted_at)
        assert stamped is not None
        # The stamp is whole-second (like every clock this lab writes), so
        # the bounds compare at that granularity.
        assert before.replace(microsecond=0) <= stamped <= after
        assert stored.approved_at == month_old

        early = client.post("/experiments/exp-post/complete")
        assert early.status_code == 409
        assert "measurement window ends" in early.json()["detail"]
        # The payload shows the same end Board and Post display: anchored
        # at the fresh post, seven days out, not at the month-old approval.
        row = next(item for item in client.get("/results").json() if item["id"] == "exp-post")
        assert row["first_posted_at"] == stored.first_posted_at
        end = _parse_iso(row["window_end"])
        assert before.replace(microsecond=0) + timedelta(days=7) <= end <= after + timedelta(days=7)

        forced = client.post("/experiments/exp-post/complete", json={"force": True})
        assert forced.status_code == 200
        assert forced.json()["status"] == "complete"


def test_clicks_after_the_post_are_windowed_and_pre_post_clicks_are_not(tmp_path):
    """US-035: `_clicks_window` opens at the same anchor as the complete
    guard. A click between approval and the first post sits before the
    anchor and stays outside the window; one after the post is inside."""
    store = open_store(tmp_path)
    _series(store)
    approved_at = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    store.insert_experiment(
        experiment(
            id="exp-click",
            status=Status.approved,
            approved_at=approved_at,
            clicks=2,
            money=Affiliate(tracking_code="win-1", merchant="acme"),
        )
    )
    backdated = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    for _ in range(2):
        store._conn.execute(
            "INSERT INTO clicks (tracking_code, experiment_id, created_at) VALUES (?, ?, ?)",
            ("win-1", "exp-click", backdated),
        )
    store._conn.commit()
    with TestClient(create_app(store)) as client:
        posted = client.post(
            "/experiments/exp-click/publications",
            json={"platform": "tiktok", "account_id": "acct-1", "token": "secret"},
        )
        assert posted.status_code == 200
        store.add_click("win-1")
        rows = client.get("/results").json()
    row = next(item for item in rows if item["id"] == "exp-click")
    assert row["clicks"] == 3
    assert row["clicks_window"] == 1


def test_pasting_the_manual_url_stamps_the_first_post_too(tmp_path):
    """US-035: the manual pack route is the other path to `posted`, so it
    stamps the same anchor on the server clock."""
    store = open_store(tmp_path)
    _series(store)
    store.insert_experiment(
        experiment(id="exp-manual", status=Status.in_review, file_path="data/videos/exp-manual.mp4")
    )
    with TestClient(create_app(store)) as client:
        assert client.post("/experiments/exp-manual/approve", json={"now": NOW}).status_code == 200
        manual = client.post(
            "/experiments/exp-manual/publications",
            json={"platform": "instagram", "account_id": "acct-1", "token": None},
        )
        assert manual.status_code == 200
        assert manual.json()["status"] == "manual_needed"
        assert store.get_experiment("exp-manual").first_posted_at is None
        before = datetime.now(timezone.utc)
        pasted = client.post(
            f"/publications/{manual.json()['id']}/url",
            json={"url": "https://instagram.example/manual/1"},
        )
        after = datetime.now(timezone.utc)
        assert pasted.status_code == 200
        stamped = _parse_iso(store.get_experiment("exp-manual").first_posted_at)
        assert stamped is not None
        assert before.replace(microsecond=0) <= stamped <= after
        early = client.post("/experiments/exp-manual/complete")
        assert early.status_code == 409
        assert "measurement window ends" in early.json()["detail"]


def test_a_second_platforms_post_never_moves_the_first_post_stamp(tmp_path):
    """US-035: the anchor is the FIRST post. A second platform's post must
    not re-open the window from its own later stamp."""
    store = open_store(tmp_path)
    _series(store)
    store.insert_experiment(
        experiment(id="exp-two", status=Status.in_review, file_path="data/videos/exp-two.mp4")
    )
    with TestClient(create_app(store)) as client:
        assert client.post("/experiments/exp-two/approve", json={"now": NOW}).status_code == 200
        first = client.post(
            "/experiments/exp-two/publications",
            json={"platform": "tiktok", "account_id": "acct-1", "token": "secret"},
        )
        assert first.status_code == 200
        stamped = store.get_experiment("exp-two").first_posted_at
        assert stamped is not None
        second = client.post(
            "/experiments/exp-two/publications",
            json={"platform": "youtube", "account_id": "acct-1", "token": "secret"},
        )
        assert second.status_code == 200
        assert store.get_experiment("exp-two").first_posted_at == stamped


def test_a_crashing_renderer_lands_in_render_failed_not_rendering(tmp_path):
    """US-018: a renderer that dies mid-flight must not strand the row in
    `rendering`, where no route can reach it again. The failure is recorded
    and the operator can re-render from `render_failed`."""
    store = open_store(tmp_path)
    _series(store)
    with TestClient(
        create_app(store, renderer=_CrashingRenderer()),
        raise_server_exceptions=False,
    ) as client:
        created = client.post("/experiments", json=experiment_body(id="exp-crash"))
        assert created.status_code == 200
        assert client.post("/experiments/exp-crash/approve-board").status_code == 200
        response = client.post("/experiments/exp-crash/render")
        assert response.status_code == 500
    stored = store.get_experiment("exp-crash")
    assert stored.status is Status.render_failed
    assert "boom while rendering" in stored.render_error


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
            experiment(
                id="exp-manual",
                status=Status.in_review,
                file_path="data/videos/exp-manual.mp4",
                money=Affiliate(tracking_code="manual-1", merchant="acme"),
            )
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


def test_a_publication_needs_an_account_id(tmp_path):
    """A blank account_id would store a publication nobody can attribute."""
    store = open_store(tmp_path)
    store.insert_experiment(
        experiment(id="exp-post", status=Status.in_review, file_path="data/videos/exp-post.mp4")
    )
    with TestClient(create_app(store)) as client:
        approved = client.post("/experiments/exp-post/approve", json={"now": NOW})
        assert approved.status_code == 200
        posted = client.post(
            "/experiments/exp-post/publications",
            json={"platform": "tiktok", "account_id": "   ", "token": None},
        )
    assert posted.status_code == 422
    assert posted.json()["detail"] == "account_id is required"
    assert store.list_publications("exp-post") == []


def test_publication_payloads_no_longer_carry_the_dead_payout_cents(tmp_path):
    """US-036: `payout_cents` was written by nothing and duplicated the
    revenue ledger (the closing audit's flag), so it is dropped from every
    payload that serves a publication."""
    store = open_store(tmp_path)
    store.insert_experiment(
        experiment(id="exp-post", status=Status.in_review, file_path="data/videos/exp-post.mp4")
    )
    with TestClient(create_app(store)) as client:
        assert client.post("/experiments/exp-post/approve", json={"now": NOW}).status_code == 200
        posted = client.post(
            "/experiments/exp-post/publications",
            json={"platform": "tiktok", "account_id": "acct-1", "token": "secret"},
        )
        assert posted.status_code == 200
        assert "payout_cents" not in posted.json()
        listed = client.get("/experiments/exp-post/publications")
        assert listed.status_code == 200
        assert all("payout_cents" not in row for row in listed.json())


def test_the_upgrade_surfaces_each_tracking_code_rename(tmp_path):
    """US-039: the recorded renames are served to the dashboard, and the
    experiments list carries the current (post-migration) code the Copy
    link button reads its URL from."""
    path = tmp_path / "legacy-renames-api.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE niches (id TEXT PRIMARY KEY, name TEXT NOT NULL, language TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO niches (id, name, language) VALUES ('history', 'History', 'en')")
    conn.execute(_LEGACY_EXPERIMENTS_SCHEMA)
    conn.executemany(
        """
        INSERT INTO experiments (
            id, niche_id, hypothesis, hook_id, script, caption, style_json, money_json,
            status, length_sec, measurement_window_days, language
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [_legacy_row("exp-first", "abc"), _legacy_row("exp-second", "abc")],
    )
    conn.commit()
    conn.close()

    store = _registered_store(path)
    with TestClient(create_app(store)) as client:
        served = client.get("/tracking-code-renames")
        assert served.status_code == 200
        assert served.json() == [
            {"experiment_id": "exp-second", "old_code": "abc", "new_code": "abc-2"}
        ]
        rows = client.get("/experiments").json()
    by_id = {row["id"]: row for row in rows}
    # The Copy link button builds its URL from this served code.
    assert by_id["exp-first"]["money"]["tracking_code"] == "abc"
    assert by_id["exp-second"]["money"]["tracking_code"] == "abc-2"

    # A lab with nothing recorded serves an empty list, not an error.
    fresh = open_store(tmp_path)
    with TestClient(create_app(fresh)) as client:
        assert client.get("/tracking-code-renames").json() == []


class _ClickTimesStore:
    """Stands in for the store: only list_click_times is needed."""

    def __init__(self, times):
        self._times = list(times)

    def list_click_times(self, experiment_id):
        return list(self._times)


def test_clicks_window_is_inclusive_at_both_ends():
    """US-025: the window runs approved_at to approved_at + window days,
    with both ends counted; anything before or after stays out."""
    approved = experiment(
        id="exp-b",
        approved_at="2026-11-01T12:00:00Z",
        measurement_window_days=7,
    )
    times = [
        "2026-11-01T12:00:00Z",  # exactly at the start
        "2026-11-08T12:00:00Z",  # exactly at the end
        "2026-11-08T12:00:01Z",  # one second past the end
        "2026-10-30T00:00:00Z",  # before the window opened
    ]
    assert _clicks_window(_ClickTimesStore(times), approved) == 2


def test_clicks_window_is_zero_when_the_clock_cannot_be_read():
    approved = experiment(id="exp-b", approved_at="yesterday")
    assert _clicks_window(_ClickTimesStore(["2026-11-01T00:00:00Z"]), approved) == 0


def test_a_click_writes_one_log_row_the_counter_agrees_with(tmp_path):
    """US-025: every click leaves a log row with a readable timestamp, and
    the legacy counter equals the log's row count."""
    store = open_store(tmp_path)
    _series(store)
    store.upsert_offer("acme", "Acme", "https://example.test/acme", merchant="acme")
    store.insert_experiment(
        experiment(id="exp-hit", money=Affiliate(tracking_code="hit-1", merchant="acme"))
    )
    with TestClient(create_app(store)) as client:
        response = client.get("/r/hit-1", follow_redirects=False)
        assert response.status_code == 302
    times = store.list_click_times("exp-hit")
    assert len(times) == 1
    assert datetime.fromisoformat(times[0].replace("Z", "+00:00"))
    assert len(times) == store.get_experiment("exp-hit").clicks


def test_a_valid_own_offer_experiment_records_the_offer(tmp_path):
    store = open_store(tmp_path)
    _series(store)
    with TestClient(create_app(store)) as client:
        created = client.post(
            "/experiments",
            json=experiment_body(
                id="exp-own",
                money={
                    "kind": "own_offer",
                    "tracking_code": "own-1",
                    "offer_url": "https://shop.example/offer",
                },
            ),
        )
        assert created.status_code == 200, created.text
        starter = client.post(
            "/starter",
            json={
                "niche_ids": ["niche-1"],
                "money": {
                    "kind": "own_offer",
                    "tracking_code": "own-grid",
                    "offer_url": "https://shop.example/offer",
                },
                "hook_id": "question",
                "voice_id": "voice-1",
                "presenter_id": "presenter-1",
            },
        )
        assert starter.status_code == 200, starter.text
        codes = [row["money"]["tracking_code"] for row in starter.json()]
        # The faceless draft keeps the operator's code; the avatar branch
        # carries its own suffix so one grid never shares a click counter.
        assert codes == ["own-grid", "own-grid-avatar"]
    assert store.get_experiment("exp-own").status == Status.draft


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
    # Captured before the request: a UTC-midnight crossing between the
    # render attempt and the assert must not move the day under test.
    day = datetime.now(timezone.utc).date().isoformat()
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


def test_a_measurement_window_of_less_than_a_day_is_refused(tmp_path):
    """A zero or negative window would close the moment the experiment is
    approved, so the window must be at least one day."""
    store = open_store(tmp_path)
    _series(store)
    with TestClient(create_app(store)) as client:
        for days in (0, -3):
            response = client.post(
                "/experiments",
                json=experiment_body(measurement_window_days=days),
            )
            assert response.status_code == 422, days
    assert store.list_experiments() == []
    assert list(tmp_path.rglob("*.storyboard.json")) == []


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
        # Captured before the renders: a UTC-midnight crossing between the
        # request and the assert must not move the day under test.
        day = datetime.now(timezone.utc).date().isoformat()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(client.post, f"/experiments/{body['id']}/render") for body in bodies
            ]
            codes = sorted(future.result().status_code for future in futures)
    assert codes == [200, 429]
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

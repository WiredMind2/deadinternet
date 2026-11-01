from dataclasses import replace

import pytest

from deadinternet.domain.experiment import (
    AvatarStyle,
    Experiment,
    FacelessStyle,
    Look,
    OwnOffer,
    Platform,
    PlatformPayout,
    Publication,
    PublicationStatus,
    Status,
    Affiliate,
)
from deadinternet.store import Store


def _faceless(**overrides) -> Experiment:
    base = dict(
        id="exp-face",
        niche_id="niche-1",
        hypothesis="A question hook travels",
        hook_id="question",
        script="Spoken script for the faceless cut.",
        caption="Watch this.",
        style=FacelessStyle(look=Look.clips, voice_id="voice-1", caption_style="bold"),
        money=Affiliate(tracking_code="aff-face", merchant="acme"),
        status=Status.draft,
        length_sec=45,
        proposal_id="prop-1",
        approved_at=None,
        measurement_window_days=7,
        file_path=None,
        render_error=None,
        language="en",
        clicks=4,
        revenue_cents=1200,
    )
    base.update(overrides)
    return Experiment(**base)


def _avatar(**overrides) -> Experiment:
    base = dict(
        id="exp-avatar",
        niche_id="niche-2",
        hypothesis="The presenter converts",
        hook_id="result",
        script="Avatar script for the own offer.",
        caption="Link below.",
        style=AvatarStyle(presenter_id="presenter-1", voice_id="voice-2"),
        money=OwnOffer(tracking_code="own-avatar", offer_url="https://shop.example/offer"),
        status=Status.approved,
        length_sec=52,
        proposal_id=None,
        approved_at="2026-10-31T12:00:00Z",
        measurement_window_days=14,
        file_path="data/videos/exp-avatar.mp4",
        render_error=None,
        language="fr",
        clicks=1,
        revenue_cents=50,
    )
    base.update(overrides)
    return Experiment(**base)


def _payout(**overrides) -> Experiment:
    base = dict(
        id="exp-payout",
        niche_id="niche-1",
        hypothesis="Rewards need a longer cut",
        hook_id="question",
        script="Longer script for the platform payout.",
        caption="Stay for the minute.",
        style=FacelessStyle(look=Look.stills, voice_id="voice-1", caption_style="minimal"),
        money=PlatformPayout(platform=Platform.youtube),
        status=Status.live,
        length_sec=75,
        proposal_id=None,
        approved_at="2026-10-30T12:00:00Z",
        measurement_window_days=7,
        file_path="data/videos/exp-payout.mp4",
        render_error=None,
        language="en",
        clicks=0,
        revenue_cents=0,
    )
    base.update(overrides)
    return Experiment(**base)


def _by_id(rows: list[Experiment]) -> dict[str, Experiment]:
    return {row.id: row for row in rows}


def test_round_trip_faceless_affiliate_and_avatar_own_offer(tmp_path):
    path = str(tmp_path / "lab.sqlite")
    store = Store(path)
    face = _faceless()
    avatar = _avatar()
    payout = _payout()
    store.insert_experiment(face)
    store.insert_experiment(avatar)
    store.insert_experiment(payout)

    assert store.get_experiment(face.id) == face
    assert isinstance(store.get_experiment(face.id).style, FacelessStyle)
    assert isinstance(store.get_experiment(face.id).money, Affiliate)
    assert store.get_experiment(avatar.id) == avatar
    assert isinstance(store.get_experiment(avatar.id).style, AvatarStyle)
    assert isinstance(store.get_experiment(avatar.id).money, OwnOffer)
    assert store.get_experiment(payout.id) == payout
    assert isinstance(store.get_experiment(payout.id).money, PlatformPayout)
    assert _by_id(store.list_experiments()) == {
        face.id: face,
        avatar.id: avatar,
        payout.id: payout,
    }

    edited = replace(
        face,
        status=Status.render_failed,
        render_error="encoder",
        hypothesis="Updated hypothesis",
        clicks=9,
        revenue_cents=2000,
    )
    store.save_experiment(edited)
    assert store.get_experiment(face.id) == edited

    reopened = Store(path)
    assert reopened.get_experiment(face.id) == edited
    assert reopened.get_experiment(avatar.id) == avatar
    assert reopened.get_experiment(payout.id) == payout


def test_second_add_of_the_same_post_url_keeps_one_publication(tmp_path):
    store = Store(str(tmp_path / "lab.sqlite"))
    face = _faceless()
    avatar = _avatar()
    store.insert_experiment(face)
    store.insert_experiment(avatar)
    url = "https://www.tiktok.com/@lab/video/1"
    first = Publication(
        id="pub-1",
        experiment_id=face.id,
        platform=Platform.tiktok,
        account_id="acct-1",
        status=PublicationStatus.posted,
        post_url=url,
        payout_cents=0,
    )
    duplicate = Publication(
        id="pub-2",
        experiment_id=face.id,
        platform=Platform.instagram,
        account_id="acct-2",
        status=PublicationStatus.failed,
        post_url=url,
        error="ignored",
        payout_cents=99,
    )
    assert store.add_publication(first) == first
    assert store.add_publication(duplicate) == first
    assert store.publication_by_url(face.id, url) == first
    assert store.list_publications(face.id) == [first]
    assert store.publication_by_url(avatar.id, url) is None

    other = Publication(
        id="pub-3",
        experiment_id=avatar.id,
        platform=Platform.tiktok,
        account_id="acct-1",
        status=PublicationStatus.posted,
        post_url=url,
    )
    assert store.add_publication(other) == other
    assert len(store.list_publications(avatar.id)) == 1

    queued_a = Publication(
        id="pub-q1",
        experiment_id=face.id,
        platform=Platform.youtube,
        account_id="acct-3",
        status=PublicationStatus.queued,
    )
    queued_b = Publication(
        id="pub-q2",
        experiment_id=face.id,
        platform=Platform.youtube,
        account_id="acct-3",
        status=PublicationStatus.queued,
    )
    store.add_publication(queued_a)
    store.add_publication(queued_b)
    assert store.list_publications(face.id) == [first, queued_a, queued_b]

    saved = replace(first, status=PublicationStatus.posted, payout_cents=40)
    store.save_publication(saved)
    assert store.publication_by_url(face.id, url) == saved


def test_renders_started_today_counts_only_that_day(tmp_path):
    store = Store(str(tmp_path / "lab.sqlite"))
    store.record_render_start("exp-face", "2026-10-31")
    store.record_render_start("exp-face", "2026-10-31")
    store.record_render_start("exp-avatar", "2026-11-01")
    assert store.renders_started_today("2026-10-31") == 2
    assert store.renders_started_today("2026-11-01") == 1
    assert store.renders_started_today("2026-10-30") == 0


def test_add_click_matches_affiliate_or_own_offer_tracking_code(tmp_path):
    path = str(tmp_path / "lab.sqlite")
    store = Store(path)
    face = _faceless(clicks=0, revenue_cents=0)
    avatar = _avatar(clicks=0, revenue_cents=0)
    payout = _payout()
    store.insert_experiment(face)
    store.insert_experiment(avatar)
    store.insert_experiment(payout)

    assert store.add_click("aff-face") == 1
    assert store.add_click("aff-face") == 2
    assert store.get_experiment(face.id).clicks == 2
    assert store.get_experiment(avatar.id).clicks == 0
    assert store.get_experiment(payout.id).clicks == 0

    assert store.add_click("own-avatar") == 1
    assert store.get_experiment(avatar.id).clicks == 1
    assert store.get_experiment(face.id).clicks == 2
    assert store.get_experiment(payout.id).clicks == 0

    store.add_revenue(face.id, 30)
    assert store.get_experiment(face.id).revenue_cents == 30
    assert store.get_experiment(avatar.id).revenue_cents == 0

    with pytest.raises(KeyError):
        store.add_click("missing-code")
    assert store.get_experiment(face.id).clicks == 2

    reopened = Store(path)
    assert reopened.get_experiment(face.id).clicks == 2
    assert reopened.get_experiment(avatar.id).clicks == 1
    assert reopened.get_experiment(payout.id).clicks == 0


def test_catalog_lists_ids_and_every_experiment(tmp_path):
    store = Store(str(tmp_path / "lab.sqlite"))
    store.upsert_niche("niche-1", "Floor mats")
    store.upsert_niche("niche-1", "Floor mats", language="fr")
    store.upsert_presenter("presenter-1", "Alex", "heygen")
    store.upsert_voice("voice-1", "Nova", "eleven")
    store.upsert_voice("voice-2", "Reed", "eleven")
    store.upsert_offer("offer-1", "Acme mat", "https://shop.example/offer", merchant="acme")
    store.upsert_hook("question", "Question")
    store.upsert_hook("result", "Result")
    store.upsert_account("acct-1", Platform.tiktok, "@lab")
    face = _faceless(clicks=0, revenue_cents=0)
    avatar = _avatar(clicks=0, revenue_cents=0)
    store.insert_experiment(face)
    store.insert_experiment(avatar)

    catalog = store.catalog()
    assert catalog.niche_ids == frozenset({"niche-1"})
    assert catalog.presenter_ids == frozenset({"presenter-1"})
    assert catalog.voice_ids == frozenset({"voice-1", "voice-2"})
    assert catalog.hook_ids == frozenset({"question", "result"})
    assert {"offer-1", "https://shop.example/offer", "acme"} <= catalog.offer_ids
    assert catalog.parents == {face.id: face, avatar.id: avatar}

    assert store.get_setting("daily_render_cap", 8) == 8
    store.set_setting("daily_render_cap", 8)
    store.set_setting("daily_render_cap", 6)
    assert store.get_setting("daily_render_cap", 8) == 6


def test_snapshots_keep_insert_order(tmp_path):
    store = Store(str(tmp_path / "lab.sqlite"))
    face = _faceless()
    store.insert_experiment(face)
    publication = store.add_publication(
        Publication(
            id="pub-1",
            experiment_id=face.id,
            platform=Platform.tiktok,
            account_id="acct-1",
            status=PublicationStatus.posted,
            post_url="https://www.tiktok.com/@lab/video/9",
        )
    )
    store.add_snapshot(publication.id, "2026-10-31T00:00:00Z", 10, 4, 1, 0, 0)
    store.add_snapshot(publication.id, "2026-11-01T00:00:00Z", 25, 9, 3, 1, 2)
    assert store.list_snapshots(publication.id) == [
        {
            "publication_id": publication.id,
            "captured_at": "2026-10-31T00:00:00Z",
            "views": 10,
            "watch_time_seconds": 4,
            "likes": 1,
            "comments": 0,
            "shares": 0,
        },
        {
            "publication_id": publication.id,
            "captured_at": "2026-11-01T00:00:00Z",
            "views": 25,
            "watch_time_seconds": 9,
            "likes": 3,
            "comments": 1,
            "shares": 2,
        },
    ]
    assert store.list_snapshots("missing") == []

import json
import sqlite3
from dataclasses import replace

import pytest

from deadinternet.domain.experiment import (
    AvatarStyle,
    Experiment,
    FacelessStyle,
    FactorDiff,
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
from tests.helpers import OPENED_STORES, experiment


def _store(path) -> Store:
    """A Store the conftest cleanup closes with the open_store() ones."""
    store = Store(str(path))
    OPENED_STORES.append(store)
    return store


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
    store = _store(path)
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
    )
    store.save_experiment(edited)
    assert store.get_experiment(face.id) == edited

    # A save from a stale copy must never rewrite the click and revenue
    # counters; those belong to add_click and add_revenue alone.
    stale = replace(edited, clicks=9, revenue_cents=2000)
    store.save_experiment(stale)
    kept = store.get_experiment(face.id)
    assert kept.clicks == face.clicks
    assert kept.revenue_cents == face.revenue_cents

    reopened = _store(path)
    assert reopened.get_experiment(face.id) == edited
    assert reopened.get_experiment(avatar.id) == avatar
    assert reopened.get_experiment(payout.id) == payout


def test_a_save_between_click_and_revenue_never_erases_them(tmp_path):
    store = _store(tmp_path / "lab.sqlite")
    face = _faceless(clicks=3, revenue_cents=0)
    store.insert_experiment(face)

    stale = store.get_experiment(face.id)
    assert store.add_click("aff-face") == 4
    store.save_experiment(stale)
    assert store.get_experiment(face.id).clicks == 4

    stale = store.get_experiment(face.id)
    store.add_revenue(face.id, 250)
    store.save_experiment(stale)
    stored = store.get_experiment(face.id)
    assert stored.clicks == 4
    assert stored.revenue_cents == 250


def test_record_revenue_on_an_unknown_experiment_changes_nothing(tmp_path):
    """US-026: the total and the ledger are one transaction, so a refused
    recording leaves both exactly as they were."""
    store = _store(tmp_path / "lab.sqlite")
    face = _faceless()
    store.insert_experiment(face)

    with pytest.raises(KeyError):
        store.record_revenue("exp-missing", 250, "payout", "2026-11-01T00:00:00Z")
    stored = store.get_experiment(face.id)
    assert stored.revenue_cents == face.revenue_cents
    assert store.list_revenue_entries(face.id) == []
    assert store.list_revenue_entries("exp-missing") == []


def test_second_add_of_the_same_post_url_keeps_one_publication(tmp_path):
    store = _store(tmp_path / "lab.sqlite")
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
    store = _store(tmp_path / "lab.sqlite")
    store.record_render_start("exp-face", "2026-10-31")
    store.record_render_start("exp-face", "2026-10-31")
    store.record_render_start("exp-avatar", "2026-11-01")
    assert store.renders_started_today("2026-10-31") == 2
    assert store.renders_started_today("2026-11-01") == 1
    assert store.renders_started_today("2026-10-30") == 0


def test_add_click_matches_affiliate_or_own_offer_tracking_code(tmp_path):
    path = str(tmp_path / "lab.sqlite")
    store = _store(path)
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

    reopened = _store(path)
    assert reopened.get_experiment(face.id).clicks == 2
    assert reopened.get_experiment(avatar.id).clicks == 1
    assert reopened.get_experiment(payout.id).clicks == 0


def test_catalog_lists_ids_and_every_experiment(tmp_path):
    store = _store(tmp_path / "lab.sqlite")
    store.upsert_theme("history", "History")
    store.upsert_theme("history", "History", language="fr")
    store.upsert_niche("niche-1", "history", "Floor mats")
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
    assert catalog.theme_ids == frozenset({"history"})
    assert store.get_theme("history").language == "fr"
    assert catalog.niche_ids == frozenset({"niche-1"})
    assert store.get_niche("niche-1").theme_id == "history"
    assert catalog.presenter_ids == frozenset({"presenter-1"})
    assert catalog.voice_ids == frozenset({"voice-1", "voice-2"})
    assert catalog.hook_ids == frozenset({"question", "result"})
    assert {"offer-1", "https://shop.example/offer", "acme"} <= catalog.offer_ids
    assert catalog.parents == {face.id: face, avatar.id: avatar}

    # A remembered merchant (empty url) never erases an operator-saved url.
    store.upsert_offer("offer-1", "Acme mat", "", merchant="acme")
    assert store.get_offer("offer-1")["url"] == "https://shop.example/offer"
    store.upsert_offer("offer-1", "Acme mat", "https://shop.example/new", merchant="acme")
    assert store.get_offer("offer-1")["url"] == "https://shop.example/new"
    assert store.get_offer("missing") is None

    # The cap wiring reads `render_cap` (app.py _render_cap); a missing key
    # of any name falls back to the default.
    assert store.get_setting("daily_render_cap", 8) == 8
    store.set_setting("render_cap", 6)
    assert store.get_setting("render_cap", 8) == 6


def test_snapshots_keep_insert_order(tmp_path):
    store = _store(tmp_path / "lab.sqlite")
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


def test_add_snapshot_keeps_absent_counts_absent(tmp_path):
    """US-038: absence is stored as NULL and reads back as None; a real
    zero keeps its meaning as a measured zero."""
    store = _store(tmp_path / "lab.sqlite")
    store.add_snapshot("pub-1", "2026-11-01T00:00:00Z", None, None, 0, None, None)
    rows = store.list_snapshots("pub-1")
    assert rows[0]["views"] is None
    assert rows[0]["watch_time_seconds"] is None
    assert rows[0]["likes"] == 0
    assert rows[0]["comments"] is None
    assert rows[0]["shares"] is None


def test_legacy_snapshots_upgrade_to_nullable_counts(tmp_path):
    """US-038: a legacy snapshots table with NOT NULL counts upgrades to
    nullable ones. Recorded zeros keep their meaning (a stored 0 was sent
    as 0 at the time); an absent count afterwards stores as absent.
    Re-opening the migrated file is a no-op."""
    path = tmp_path / "legacy-snapshots.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publication_id TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            views INTEGER NOT NULL,
            watch_time_seconds INTEGER NOT NULL,
            likes INTEGER NOT NULL,
            comments INTEGER NOT NULL,
            shares INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO snapshots (
            publication_id, captured_at, views, watch_time_seconds, likes, comments, shares
        ) VALUES ('pub-1', '2026-11-01T00:00:00Z', 10, 0, 0, 0, 0)
        """
    )
    conn.commit()
    conn.close()

    store = _store(path)
    rows = store.list_snapshots("pub-1")
    assert rows[0]["views"] == 10
    assert rows[0]["likes"] == 0
    store.add_snapshot("pub-1", "2026-11-02T00:00:00Z", None, None, None, None, None)
    rows = store.list_snapshots("pub-1")
    assert len(rows) == 2
    assert rows[1]["views"] is None
    assert rows[1]["watch_time_seconds"] is None

    reopened = _store(path)
    after = reopened.list_snapshots("pub-1")
    assert len(after) == 2
    assert after[0]["views"] == 10
    assert after[1]["views"] is None


def test_legacy_niche_rows_become_a_theme_and_a_series(tmp_path):
    path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE niches (id TEXT PRIMARY KEY, name TEXT NOT NULL, language TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO niches (id, name, language) VALUES ('history', 'History', 'en')")
    conn.execute(
        """
        CREATE TABLE experiments (
            id TEXT PRIMARY KEY,
            niche_id TEXT NOT NULL,
            hypothesis TEXT NOT NULL,
            hook_id TEXT NOT NULL,
            script TEXT NOT NULL,
            caption TEXT NOT NULL,
            style_json TEXT NOT NULL,
            money_json TEXT NOT NULL,
            status TEXT NOT NULL,
            length_sec INTEGER NOT NULL,
            proposal_id TEXT,
            approved_at TEXT,
            measurement_window_days INTEGER NOT NULL,
            file_path TEXT,
            render_error TEXT,
            language TEXT NOT NULL,
            clicks INTEGER NOT NULL DEFAULT 0,
            revenue_cents INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO experiments (
            id, niche_id, hypothesis, hook_id, script, caption, style_json, money_json,
            status, length_sec, measurement_window_days, language
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "exp-old",
            "history",
            "Keep the old cell",
            "question",
            "Old script",
            "Old caption",
            json.dumps(
                {
                    "kind": "faceless",
                    "look": "stills",
                    "voice_id": "voice-1",
                    "caption_style": "bold",
                }
            ),
            json.dumps({"kind": "affiliate", "tracking_code": "abc", "merchant": "acme"}),
            "draft",
            45,
            7,
            "en",
        ),
    )
    conn.commit()
    conn.close()

    store = _store(path)
    assert store.get_theme("history").language == "en"
    niche = store.get_niche("history")
    assert niche.theme_id == "history"
    assert niche.name == "History"
    loaded = store.get_experiment("exp-old")
    assert loaded.niche_id == "history"
    assert loaded.script == "Old script"
    assert loaded.board_hash is None


_LEGACY_EXPERIMENTS_SCHEMA = """
        CREATE TABLE experiments (
            id TEXT PRIMARY KEY,
            niche_id TEXT NOT NULL,
            hypothesis TEXT NOT NULL,
            hook_id TEXT NOT NULL,
            script TEXT NOT NULL,
            caption TEXT NOT NULL,
            style_json TEXT NOT NULL,
            money_json TEXT NOT NULL,
            status TEXT NOT NULL,
            length_sec INTEGER NOT NULL,
            proposal_id TEXT,
            approved_at TEXT,
            measurement_window_days INTEGER NOT NULL,
            file_path TEXT,
            render_error TEXT,
            language TEXT NOT NULL,
            clicks INTEGER NOT NULL DEFAULT 0,
            revenue_cents INTEGER NOT NULL DEFAULT 0
        )
"""


def _legacy_row(row_id: str, tracking_code: str) -> tuple:
    return (
        row_id,
        "history",
        "Keep the old cell",
        "question",
        f"Old script {row_id}",
        "Old caption",
        json.dumps(
            {
                "kind": "faceless",
                "look": "stills",
                "voice_id": "voice-1",
                "caption_style": "bold",
            }
        ),
        json.dumps({"kind": "affiliate", "tracking_code": tracking_code, "merchant": "acme"}),
        "draft",
        45,
        7,
        "en",
    )


def test_legacy_duplicate_tracking_codes_are_renamed_not_deleted(tmp_path):
    """US-024: a legacy database with duplicate codes upgrades without
    crashing and without deleting rows; new duplicates are then refused."""
    path = tmp_path / "legacy-duplicates.sqlite"
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

    store = _store(path)
    first = store.get_experiment("exp-first")
    second = store.get_experiment("exp-second")
    # The earliest row keeps the shared code; the later duplicate is recoded.
    assert first.money.tracking_code == "abc"
    assert second.money.tracking_code == "abc-2"

    # After the upgrade the unique index refuses any new duplicate outright.
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_experiment(replace(first, id="exp-new"))

    # Re-opening the migrated file is a no-op: the codes stay put.
    reopened = _store(path)
    assert reopened.get_experiment("exp-first").money.tracking_code == "abc"
    assert reopened.get_experiment("exp-second").money.tracking_code == "abc-2"


def test_legacy_click_counters_are_backfilled_into_the_log(tmp_path):
    """US-025: the counter and the log must agree, including for clicks
    recorded before the log existed. The backfill is idempotent."""
    path = tmp_path / "legacy-clicks.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE niches (id TEXT PRIMARY KEY, name TEXT NOT NULL, language TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO niches (id, name, language) VALUES ('history', 'History', 'en')")
    conn.execute(_LEGACY_EXPERIMENTS_SCHEMA)
    conn.execute(
        """
        INSERT INTO experiments (
            id, niche_id, hypothesis, hook_id, script, caption, style_json, money_json,
            status, length_sec, measurement_window_days, language, clicks
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _legacy_row("exp-clicks", "abc")[:12] + (5,),
    )
    conn.commit()
    conn.close()

    store = _store(path)
    times = store.list_click_times("exp-clicks")
    assert len(times) == 5
    assert all(times[0] == stamp for stamp in times)
    assert store.get_experiment("exp-clicks").clicks == 5

    # Re-opening neither adds rows nor moves the counter.
    reopened = _store(path)
    assert len(reopened.list_click_times("exp-clicks")) == 5
    assert reopened.get_experiment("exp-clicks").clicks == 5


def test_the_duplicate_code_migration_records_every_rename(tmp_path):
    """US-039: each rename is recorded with the row id and both codes, once.
    Re-opening the migrated file neither rewrites the log nor appends."""
    path = tmp_path / "legacy-rename-log.sqlite"
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
        [
            _legacy_row("exp-first", "abc"),
            _legacy_row("exp-second", "abc"),
            _legacy_row("exp-third", "abc"),
        ],
    )
    conn.commit()
    conn.close()

    store = _store(path)
    recorded = store.get_setting("tracking_code_renames")
    assert recorded == [
        {"experiment_id": "exp-second", "old_code": "abc", "new_code": "abc-2"},
        {"experiment_id": "exp-third", "old_code": "abc", "new_code": "abc-3"},
    ]

    # A lab with no duplicates records nothing.
    clean = _store(str(path.parent / "clean.sqlite"))
    clean.insert_experiment(
        _faceless(id="exp-clean", money=Affiliate(tracking_code="clean", merchant="acme"))
    )
    assert clean.get_setting("tracking_code_renames") is None

    reopened = _store(path)
    assert reopened.get_setting("tracking_code_renames") == recorded


def test_lineage_round_trips_through_insert_and_save(tmp_path):
    """US-031: parent_ids and factor_diffs persist on the experiment, and a
    save never erases them."""
    store = _store(tmp_path / "lab.sqlite")
    parent = _faceless()
    store.insert_experiment(parent)
    child = _avatar(
        parent_ids=(parent.id,),
        factor_diffs=(
            FactorDiff(
                field="style",
                parent_value="faceless/clips/voice-1/bold",
                next_value="avatar/presenter-1/voice-2",
            ),
        ),
    )
    store.insert_experiment(child)
    assert store.get_experiment(child.id) == child

    saved = replace(child, status=Status.complete)
    store.save_experiment(saved)
    kept = store.get_experiment(child.id)
    assert kept.status is Status.complete
    assert kept.parent_ids == (parent.id,)
    assert kept.factor_diffs == child.factor_diffs

    reopened = _store(tmp_path / "lab.sqlite")
    assert reopened.get_experiment(child.id) == saved


def test_legacy_rows_upgrade_with_empty_lineage(tmp_path):
    """US-031: a legacy database without the lineage columns upgrades
    cleanly. Old rows read back with no parents and no factor diffs, and
    new lineage written afterwards round-trips."""
    path = tmp_path / "legacy-lineage.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE niches (id TEXT PRIMARY KEY, name TEXT NOT NULL, language TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO niches (id, name, language) VALUES ('history', 'History', 'en')")
    conn.execute(_LEGACY_EXPERIMENTS_SCHEMA)
    conn.execute(
        """
        INSERT INTO experiments (
            id, niche_id, hypothesis, hook_id, script, caption, style_json, money_json,
            status, length_sec, measurement_window_days, language
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _legacy_row("exp-old", "abc"),
    )
    conn.commit()
    conn.close()

    store = _store(path)
    loaded = store.get_experiment("exp-old")
    assert loaded.parent_ids == ()
    assert loaded.factor_diffs == ()

    child = _faceless(
        id="exp-child",
        money=Affiliate(tracking_code="aff-child", merchant="acme"),
        parent_ids=("exp-old",),
        factor_diffs=(FactorDiff(field="hook", parent_value="question", next_value="result"),),
    )
    store.insert_experiment(child)
    approved = replace(child, status=Status.board_approved)
    store.save_experiment(approved)
    assert store.get_experiment("exp-child") == approved

    # Re-opening the migrated file is a no-op: the columns stay in place.
    reopened = _store(path)
    assert reopened.get_experiment("exp-old").parent_ids == ()
    assert reopened.get_experiment("exp-child") == approved


def test_legacy_rows_upgrade_without_the_first_post_stamp(tmp_path):
    """US-035: a legacy database without first_posted_at upgrades cleanly.
    Old rows read back with no stamp (their window falls back to
    approved_at), a stamp written afterwards round-trips, and re-opening
    the migrated file is a no-op."""
    path = tmp_path / "legacy-first-post.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE niches (id TEXT PRIMARY KEY, name TEXT NOT NULL, language TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO niches (id, name, language) VALUES ('history', 'History', 'en')")
    conn.execute(_LEGACY_EXPERIMENTS_SCHEMA)
    conn.execute(
        """
        INSERT INTO experiments (
            id, niche_id, hypothesis, hook_id, script, caption, style_json, money_json,
            status, length_sec, measurement_window_days, language
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _legacy_row("exp-old", "abc"),
    )
    conn.commit()
    conn.close()

    store = _store(path)
    loaded = store.get_experiment("exp-old")
    assert loaded.first_posted_at is None
    stamped = replace(loaded, first_posted_at="2026-11-19T00:00:00Z")
    store.save_experiment(stamped)
    assert store.get_experiment("exp-old") == stamped

    reopened = _store(path)
    assert reopened.get_experiment("exp-old") == stamped


def test_a_failed_ledger_insert_rolls_the_total_back(tmp_path):
    """US-026: the total and the ledger are one transaction. A trigger
    aborts the ledger insert; the raised UPDATE must roll back with it."""
    store = _store(tmp_path / "lab.sqlite")
    store.insert_experiment(experiment(id="exp-1"))
    store._conn.execute(
        "CREATE TRIGGER no_ledger BEFORE INSERT ON revenue_ledger "
        "BEGIN SELECT RAISE(ABORT, 'boom'); END"
    )
    with pytest.raises(sqlite3.Error, match="boom"):
        store.record_revenue("exp-1", 250, "tiktok", "2026-11-19T00:00:00Z")
    assert store.get_experiment("exp-1").revenue_cents == 0
    assert store.list_revenue_entries("exp-1") == []


def test_reverse_revenue_lowers_the_total_and_links_the_rows(tmp_path):
    """US-037: a reversal writes one negative row that points back at the
    entry it corrects, and the total drops by the reversed amount."""
    store = _store(tmp_path / "lab.sqlite")
    face = _faceless(revenue_cents=0)
    store.insert_experiment(face)
    original = store.record_revenue(face.id, 250, "tiktok", "2026-11-19T00:00:00Z")
    store.record_revenue(face.id, 100, "", "2026-11-19T00:05:00Z")

    reversal = store.reverse_revenue(face.id, original["id"], "typo", "2026-11-19T00:10:00Z")

    assert store.get_experiment(face.id).revenue_cents == 100
    entries = store.list_revenue_entries(face.id)
    assert [entry["id"] for entry in entries] == [reversal["id"], 2, original["id"]]
    assert entries[0]["amount_cents"] == -250
    assert entries[0]["reverses_entry_id"] == original["id"]
    assert entries[0]["note"] == "typo"
    assert entries[2]["amount_cents"] == 250
    assert entries[2]["reverses_entry_id"] is None


def test_reverse_revenue_refuses_double_reversals_and_reversals_of_reversals(tmp_path):
    """US-037: one reversal per payout. The refusal names the reversal
    that already corrected the entry, and nothing changes on refusal."""
    store = _store(tmp_path / "lab.sqlite")
    face = _faceless(revenue_cents=0)
    store.insert_experiment(face)
    original = store.record_revenue(face.id, 250, "tiktok", "2026-11-19T00:00:00Z")

    first = store.reverse_revenue(face.id, original["id"], "typo", "2026-11-19T00:10:00Z")
    with pytest.raises(ValueError, match=f"already reversed by entry {first['id']}"):
        store.reverse_revenue(face.id, original["id"], "again", "2026-11-19T00:15:00Z")
    with pytest.raises(ValueError, match="is a reversal, not a payout"):
        store.reverse_revenue(face.id, first["id"], "undo the undo", "2026-11-19T00:20:00Z")

    with pytest.raises(KeyError):
        store.reverse_revenue(face.id, 999, "no such row", "2026-11-19T00:25:00Z")
    with pytest.raises(KeyError):
        store.reverse_revenue("exp-missing", original["id"], "no such experiment", "2026-11-19T00:30:00Z")

    assert store.get_experiment(face.id).revenue_cents == 0
    assert len(store.list_revenue_entries(face.id)) == 2


def test_reverse_revenue_never_takes_the_total_below_zero(tmp_path):
    """US-037: the guard defends a counter a ledger row no longer matches
    (a counter-only adjustment can leave one behind); the refused reversal
    leaves the total and the ledger exactly as they were."""
    store = _store(tmp_path / "lab.sqlite")
    face = _faceless(revenue_cents=0)
    store.insert_experiment(face)
    original = store.record_revenue(face.id, 250, "tiktok", "2026-11-19T00:00:00Z")
    store.add_revenue(face.id, -200)

    with pytest.raises(ValueError, match="below 0"):
        store.reverse_revenue(face.id, original["id"], "typo", "2026-11-19T00:10:00Z")
    assert store.get_experiment(face.id).revenue_cents == 50
    assert len(store.list_revenue_entries(face.id)) == 1


def test_a_failed_reversal_insert_rolls_the_total_back(tmp_path):
    """US-037: the total and the reversal row are one transaction. A
    trigger aborts the reversal insert; the lowered total must roll back
    with it."""
    store = _store(tmp_path / "lab.sqlite")
    store.insert_experiment(experiment(id="exp-1"))
    original = store.record_revenue("exp-1", 250, "tiktok", "2026-11-19T00:00:00Z")
    store._conn.execute(
        "CREATE TRIGGER no_reversal BEFORE INSERT ON revenue_ledger "
        "BEGIN SELECT RAISE(ABORT, 'boom'); END"
    )
    with pytest.raises(sqlite3.Error, match="boom"):
        store.reverse_revenue("exp-1", original["id"], "typo", "2026-11-19T00:10:00Z")
    assert store.get_experiment("exp-1").revenue_cents == 250
    assert [entry["id"] for entry in store.list_revenue_entries("exp-1")] == [original["id"]]


def test_legacy_ledger_upgrades_with_the_reversal_link(tmp_path):
    """US-037: a legacy database whose ledger has no reverses_entry_id
    upgrades cleanly. Old rows read back with no link, and a reversal
    written afterwards round-trips. Re-opening is a no-op."""
    path = tmp_path / "legacy-reversals.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE niches (id TEXT PRIMARY KEY, name TEXT NOT NULL, language TEXT NOT NULL)")
    conn.execute("INSERT INTO niches (id, name, language) VALUES ('history', 'History', 'en')")
    conn.execute(_LEGACY_EXPERIMENTS_SCHEMA)
    conn.execute(
        """
        CREATE TABLE revenue_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO experiments (
            id, niche_id, hypothesis, hook_id, script, caption, style_json, money_json,
            status, length_sec, measurement_window_days, language, revenue_cents
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _legacy_row("exp-old", "abc")[:12] + (250,),
    )
    conn.execute(
        """
        INSERT INTO revenue_ledger (experiment_id, amount_cents, note, created_at)
        VALUES ('exp-old', 250, 'tiktok', '2026-11-01T00:00:00Z')
        """
    )
    conn.commit()
    conn.close()

    store = _store(path)
    entries = store.list_revenue_entries("exp-old")
    assert len(entries) == 1
    assert entries[0]["reverses_entry_id"] is None

    reversal = store.reverse_revenue("exp-old", entries[0]["id"], "typo", "2026-11-19T00:00:00Z")
    assert store.get_experiment("exp-old").revenue_cents == 0
    after = store.list_revenue_entries("exp-old")
    assert [entry["amount_cents"] for entry in after] == [-250, 250]
    assert after[0]["reverses_entry_id"] == reversal["reverses_entry_id"] == entries[0]["id"]

    reopened = _store(path)
    assert reopened.get_experiment("exp-old").revenue_cents == 0
    assert [entry["amount_cents"] for entry in reopened.list_revenue_entries("exp-old")] == [-250, 250]


def test_a_failed_click_log_insert_rolls_the_counter_back(tmp_path):
    """US-025: the counter and the log are one transaction. A trigger
    aborts the log insert; the counter must roll back with it."""
    store = _store(tmp_path / "lab.sqlite")
    store.insert_experiment(experiment(id="exp-1"))
    store._conn.execute(
        "CREATE TRIGGER no_click_log BEFORE INSERT ON clicks "
        "BEGIN SELECT RAISE(ABORT, 'boom'); END"
    )
    with pytest.raises(sqlite3.Error, match="boom"):
        store.add_click("abc")
    assert store.get_experiment("exp-1").clicks == 0
    assert store.list_click_times("exp-1") == []

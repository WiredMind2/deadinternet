"""SQLite persistence for experiments, posts, and catalog rows."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from deadinternet.domain.experiment import (
    Affiliate,
    AvatarStyle,
    Experiment,
    FacelessStyle,
    Look,
    Money,
    Niche,
    OwnOffer,
    Platform,
    PlatformPayout,
    Publication,
    PublicationStatus,
    Status,
    Style,
    Theme,
)
from deadinternet.domain.proposal import Catalog

_SCHEMA = """
CREATE TABLE IF NOT EXISTS themes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    language TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS niches (
    id TEXT PRIMARY KEY,
    theme_id TEXT NOT NULL,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS presenters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS voices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS offers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    merchant TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    handle TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hooks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiments (
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
    revenue_cents INTEGER NOT NULL DEFAULT 0,
    board_hash TEXT
);

CREATE TABLE IF NOT EXISTS render_starts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL,
    day TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS render_starts_day ON render_starts (day);

CREATE TABLE IF NOT EXISTS publications (
    id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    account_id TEXT NOT NULL,
    status TEXT NOT NULL,
    post_url TEXT,
    error TEXT,
    payout_cents INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS publications_experiment_post_url
ON publications (experiment_id, post_url)
WHERE post_url IS NOT NULL;

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    views INTEGER NOT NULL,
    watch_time_seconds INTEGER NOT NULL,
    likes INTEGER NOT NULL,
    comments INTEGER NOT NULL,
    shares INTEGER NOT NULL
);
"""


def _dump_style(style: Style) -> str:
    if isinstance(style, FacelessStyle):
        payload: dict[str, str] = {
            "kind": style.kind,
            "look": style.look.value,
            "voice_id": style.voice_id,
            "caption_style": style.caption_style,
        }
    elif isinstance(style, AvatarStyle):
        payload = {
            "kind": style.kind,
            "presenter_id": style.presenter_id,
            "voice_id": style.voice_id,
        }
    else:
        raise TypeError(f"unknown style {type(style)!r}")
    return json.dumps(payload)


def _load_style(payload: str) -> Style:
    raw = json.loads(payload)
    kind = raw["kind"]
    if kind == "faceless":
        return FacelessStyle(
            look=Look(raw["look"]),
            voice_id=raw["voice_id"],
            caption_style=raw["caption_style"],
        )
    if kind == "avatar":
        return AvatarStyle(presenter_id=raw["presenter_id"], voice_id=raw["voice_id"])
    raise ValueError(f"unknown style {kind}")


def _dump_money(money: Money) -> str:
    if isinstance(money, Affiliate):
        payload: dict[str, str] = {
            "kind": money.kind,
            "tracking_code": money.tracking_code,
            "merchant": money.merchant,
        }
    elif isinstance(money, PlatformPayout):
        payload = {"kind": money.kind, "platform": money.platform.value}
    elif isinstance(money, OwnOffer):
        payload = {
            "kind": money.kind,
            "tracking_code": money.tracking_code,
            "offer_url": money.offer_url,
        }
    else:
        raise TypeError(f"unknown money path {type(money)!r}")
    return json.dumps(payload)


def _load_money(payload: str) -> Money:
    raw = json.loads(payload)
    kind = raw["kind"]
    if kind == "affiliate":
        return Affiliate(tracking_code=raw["tracking_code"], merchant=raw["merchant"])
    if kind == "platform_payout":
        return PlatformPayout(platform=Platform(raw["platform"]))
    if kind == "own_offer":
        return OwnOffer(tracking_code=raw["tracking_code"], offer_url=raw["offer_url"])
    raise ValueError(f"unknown money path {kind}")


def _platform_text(platform: Platform | str) -> str:
    if isinstance(platform, Platform):
        return platform.value
    return str(platform)


def _experiment_values(experiment: Experiment) -> tuple:
    return (
        experiment.id,
        experiment.niche_id,
        experiment.hypothesis,
        experiment.hook_id,
        experiment.script,
        experiment.caption,
        _dump_style(experiment.style),
        _dump_money(experiment.money),
        experiment.status.value,
        experiment.length_sec,
        experiment.proposal_id,
        experiment.approved_at,
        experiment.measurement_window_days,
        experiment.file_path,
        experiment.render_error,
        experiment.language,
        experiment.clicks,
        experiment.revenue_cents,
        experiment.board_hash,
    )


def _experiment_from_row(row: sqlite3.Row) -> Experiment:
    return Experiment(
        id=row["id"],
        niche_id=row["niche_id"],
        hypothesis=row["hypothesis"],
        hook_id=row["hook_id"],
        script=row["script"],
        caption=row["caption"],
        style=_load_style(row["style_json"]),
        money=_load_money(row["money_json"]),
        status=Status(row["status"]),
        length_sec=row["length_sec"],
        proposal_id=row["proposal_id"],
        approved_at=row["approved_at"],
        measurement_window_days=row["measurement_window_days"],
        file_path=row["file_path"],
        render_error=row["render_error"],
        language=row["language"],
        clicks=row["clicks"],
        revenue_cents=row["revenue_cents"],
        board_hash=row["board_hash"],
    )


def _publication_values(publication: Publication) -> tuple:
    return (
        publication.id,
        publication.experiment_id,
        publication.platform.value,
        publication.account_id,
        publication.status.value,
        publication.post_url,
        publication.error,
        publication.payout_cents,
    )


def _publication_from_row(row: sqlite3.Row) -> Publication:
    return Publication(
        id=row["id"],
        experiment_id=row["experiment_id"],
        platform=Platform(row["platform"]),
        account_id=row["account_id"],
        status=PublicationStatus(row["status"]),
        post_url=row["post_url"],
        error=row["error"],
        payout_cents=row["payout_cents"],
    )


class Store:
    def __init__(self, path: str) -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate_legacy_niches()
        self._conn.executescript(_SCHEMA)
        self._ensure_board_hash()

    def _column_names(self, table: str) -> set[str]:
        row = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        if row is None:
            return set()
        info = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {item["name"] for item in info}

    def _migrate_legacy_niches(self) -> None:
        if "language" not in self._column_names("niches"):
            return
        with self._conn:
            self._conn.execute("ALTER TABLE niches RENAME TO themes")
            self._conn.execute(
                """
                CREATE TABLE niches (
                    id TEXT PRIMARY KEY,
                    theme_id TEXT NOT NULL,
                    name TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                INSERT INTO niches (id, theme_id, name)
                SELECT id, id, name FROM themes
                """
            )

    def _ensure_board_hash(self) -> None:
        columns = self._column_names("experiments")
        if columns and "board_hash" not in columns:
            self._conn.execute("ALTER TABLE experiments ADD COLUMN board_hash TEXT")
            self._conn.commit()

    def upsert_theme(self, id: str, name: str, language: str = "en") -> None:
        self._write(
            """
            INSERT INTO themes (id, name, language) VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                language = excluded.language
            """,
            (id, name, language),
        )

    def upsert_niche(self, id: str, theme_id: str, name: str) -> None:
        if self.get_theme(theme_id) is None:
            raise KeyError(theme_id)
        self._write(
            """
            INSERT INTO niches (id, theme_id, name) VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                theme_id = excluded.theme_id,
                name = excluded.name
            """,
            (id, theme_id, name),
        )

    def get_theme(self, id: str) -> Theme | None:
        row = self._conn.execute(
            "SELECT id, name, language FROM themes WHERE id = ?",
            (id,),
        ).fetchone()
        if row is None:
            return None
        return Theme(id=row["id"], name=row["name"], language=row["language"])

    def list_themes(self) -> list[Theme]:
        rows = self._conn.execute(
            "SELECT id, name, language FROM themes ORDER BY id"
        ).fetchall()
        return [Theme(id=row["id"], name=row["name"], language=row["language"]) for row in rows]

    def get_niche(self, id: str) -> Niche | None:
        row = self._conn.execute(
            "SELECT id, theme_id, name FROM niches WHERE id = ?",
            (id,),
        ).fetchone()
        if row is None:
            return None
        return Niche(id=row["id"], theme_id=row["theme_id"], name=row["name"])

    def list_niches(self) -> list[Niche]:
        rows = self._conn.execute(
            "SELECT id, theme_id, name FROM niches ORDER BY id"
        ).fetchall()
        return [
            Niche(id=row["id"], theme_id=row["theme_id"], name=row["name"]) for row in rows
        ]

    def upsert_presenter(self, id: str, name: str, provider: str) -> None:
        self._write(
            """
            INSERT INTO presenters (id, name, provider) VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                provider = excluded.provider
            """,
            (id, name, provider),
        )

    def upsert_voice(self, id: str, name: str, provider: str) -> None:
        self._write(
            """
            INSERT INTO voices (id, name, provider) VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                provider = excluded.provider
            """,
            (id, name, provider),
        )

    def upsert_offer(self, id: str, name: str, url: str, merchant: str = "") -> None:
        self._write(
            """
            INSERT INTO offers (id, name, url, merchant) VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                url = excluded.url,
                merchant = excluded.merchant
            """,
            (id, name, url, merchant),
        )

    def upsert_account(self, id: str, platform: Platform | str, handle: str) -> None:
        self._write(
            """
            INSERT INTO accounts (id, platform, handle) VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                platform = excluded.platform,
                handle = excluded.handle
            """,
            (id, _platform_text(platform), handle),
        )

    def upsert_hook(self, id: str, name: str) -> None:
        self._write(
            """
            INSERT INTO hooks (id, name) VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET name = excluded.name
            """,
            (id, name),
        )

    def set_setting(self, key: str, value: Any) -> None:
        self._write(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, json.dumps(value)),
        )

    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return default
        return json.loads(row["value"])

    def insert_experiment(self, experiment: Experiment) -> None:
        self._write(
            """
            INSERT INTO experiments (
                id, niche_id, hypothesis, hook_id, script, caption,
                style_json, money_json, status, length_sec,
                proposal_id, approved_at, measurement_window_days,
                file_path, render_error, language, clicks, revenue_cents, board_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _experiment_values(experiment),
        )

    def get_experiment(self, id: str) -> Experiment:
        row = self._conn.execute(
            "SELECT * FROM experiments WHERE id = ?",
            (id,),
        ).fetchone()
        if row is None:
            raise KeyError(id)
        return _experiment_from_row(row)

    def save_experiment(self, experiment: Experiment) -> None:
        self._require_experiment(experiment.id)
        self._write(
            """
            UPDATE experiments SET
                niche_id = ?,
                hypothesis = ?,
                hook_id = ?,
                script = ?,
                caption = ?,
                style_json = ?,
                money_json = ?,
                status = ?,
                length_sec = ?,
                proposal_id = ?,
                approved_at = ?,
                measurement_window_days = ?,
                file_path = ?,
                render_error = ?,
                language = ?,
                clicks = ?,
                revenue_cents = ?,
                board_hash = ?
            WHERE id = ?
            """,
            _experiment_values(experiment)[1:] + (experiment.id,),
        )

    def list_experiments(self) -> list[Experiment]:
        rows = self._conn.execute(
            "SELECT * FROM experiments ORDER BY rowid"
        ).fetchall()
        return [_experiment_from_row(row) for row in rows]

    def renders_started_today(self, day: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM render_starts WHERE day = ?",
            (day,),
        ).fetchone()
        return int(row["n"])

    def record_render_start(self, experiment_id: str, day: str) -> None:
        self._write(
            "INSERT INTO render_starts (experiment_id, day) VALUES (?, ?)",
            (experiment_id, day),
        )

    def add_publication(self, publication: Publication) -> Publication:
        if publication.post_url is not None:
            existing = self.publication_by_url(publication.experiment_id, publication.post_url)
            if existing is not None:
                return existing
        try:
            self._conn.execute(
                """
                INSERT INTO publications (
                    id, experiment_id, platform, account_id, status,
                    post_url, error, payout_cents
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _publication_values(publication),
            )
        except sqlite3.IntegrityError:
            self._conn.rollback()
            if publication.post_url is not None:
                existing = self.publication_by_url(
                    publication.experiment_id, publication.post_url
                )
                if existing is not None:
                    return existing
            raise
        self._conn.commit()
        return publication

    def publication_by_url(self, experiment_id: str, url: str) -> Publication | None:
        row = self._conn.execute(
            """
            SELECT * FROM publications
            WHERE experiment_id = ? AND post_url = ?
            """,
            (experiment_id, url),
        ).fetchone()
        if row is None:
            return None
        return _publication_from_row(row)

    def list_publications(self, experiment_id: str) -> list[Publication]:
        rows = self._conn.execute(
            """
            SELECT * FROM publications
            WHERE experiment_id = ?
            ORDER BY rowid
            """,
            (experiment_id,),
        ).fetchall()
        return [_publication_from_row(row) for row in rows]

    def save_publication(self, publication: Publication) -> None:
        row = self._conn.execute(
            "SELECT 1 FROM publications WHERE id = ?",
            (publication.id,),
        ).fetchone()
        if row is None:
            raise KeyError(publication.id)
        self._write(
            """
            UPDATE publications SET
                experiment_id = ?,
                platform = ?,
                account_id = ?,
                status = ?,
                post_url = ?,
                error = ?,
                payout_cents = ?
            WHERE id = ?
            """,
            _publication_values(publication)[1:] + (publication.id,),
        )

    def add_snapshot(
        self,
        publication_id: str,
        captured_at: str,
        views: int,
        watch_time_seconds: int,
        likes: int,
        comments: int,
        shares: int,
    ) -> None:
        self._write(
            """
            INSERT INTO snapshots (
                publication_id, captured_at, views, watch_time_seconds,
                likes, comments, shares
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                publication_id,
                captured_at,
                views,
                watch_time_seconds,
                likes,
                comments,
                shares,
            ),
        )

    def list_snapshots(self, publication_id: str) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT publication_id, captured_at, views, watch_time_seconds,
                   likes, comments, shares
            FROM snapshots
            WHERE publication_id = ?
            ORDER BY id
            """,
            (publication_id,),
        ).fetchall()
        return [
            {
                "publication_id": row["publication_id"],
                "captured_at": row["captured_at"],
                "views": row["views"],
                "watch_time_seconds": row["watch_time_seconds"],
                "likes": row["likes"],
                "comments": row["comments"],
                "shares": row["shares"],
            }
            for row in rows
        ]

    def add_click(self, tracking_code: str) -> int:
        cur = self._conn.execute(
            """
            UPDATE experiments
            SET clicks = clicks + 1
            WHERE id = (
                SELECT id FROM experiments
                WHERE json_extract(money_json, '$.tracking_code') = ?
                LIMIT 1
            )
            RETURNING clicks
            """,
            (tracking_code,),
        )
        row = cur.fetchone()
        if row is None:
            self._conn.rollback()
            raise KeyError(tracking_code)
        self._conn.commit()
        return int(row["clicks"])

    def add_revenue(self, experiment_id: str, cents: int) -> None:
        self._require_experiment(experiment_id)
        self._write(
            """
            UPDATE experiments
            SET revenue_cents = revenue_cents + ?
            WHERE id = ?
            """,
            (cents, experiment_id),
        )

    def catalog(self) -> Catalog:
        offer_ids: set[str] = set()
        for row in self._conn.execute("SELECT id, url, merchant FROM offers"):
            offer_ids.add(row["id"])
            if row["url"]:
                offer_ids.add(row["url"])
            if row["merchant"]:
                offer_ids.add(row["merchant"])
        parents = {experiment.id: experiment for experiment in self.list_experiments()}
        return Catalog(
            niche_ids=self._ids("niches"),
            presenter_ids=self._ids("presenters"),
            voice_ids=self._ids("voices"),
            offer_ids=frozenset(offer_ids),
            hook_ids=self._ids("hooks"),
            parents=parents,
            theme_ids=self._ids("themes"),
        )

    def _ids(self, table: str) -> frozenset[str]:
        if table not in {"themes", "niches", "presenters", "voices", "hooks"}:
            raise ValueError(table)
        rows = self._conn.execute(f"SELECT id FROM {table}").fetchall()
        return frozenset(row["id"] for row in rows)

    def _require_experiment(self, experiment_id: str) -> None:
        row = self._conn.execute(
            "SELECT 1 FROM experiments WHERE id = ?",
            (experiment_id,),
        ).fetchone()
        if row is None:
            raise KeyError(experiment_id)

    def _write(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        return cur

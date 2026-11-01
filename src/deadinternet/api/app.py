"""HTTP commands for experiments, the click redirect, and metric snapshots."""

import sqlite3
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from deadinternet.domain.experiment import (
    Beat,
    Experiment,
    IneligibleLength,
    InvalidBoard,
    InvalidTransition,
    Platform,
    Publication,
    PublicationStatus,
    RenderCapReached,
    Status,
    Style,
    approve,
    approve_board,
    complete,
    mark_posted,
    mark_rendered,
    reject,
    request_render,
    revise_board,
    script_from_beats,
)
from deadinternet.storyboard import (
    UnsafeId,
    check_segment,
    read_storyboard,
    storyboard_path,
    write_storyboard,
)
from deadinternet.domain.proposal import (
    DraftSpec,
    ProposalRejected,
    _money_from,
    _style_from,
    starter_grid,
)
from deadinternet.domain.rank import below_sample_floor, cell_size, suggest
from deadinternet.metrics.pull import record_snapshot
from deadinternet.track.redirect import hit


class Renderer(Protocol):
    def render(self, experiment: Experiment, media_dir: Path) -> Experiment:
        """Return the experiment in_review, or render_failed."""


class Publisher(Protocol):
    def publish(
        self,
        experiment: Experiment,
        platform: Platform,
        account_id: str,
        token: str | None = None,
    ) -> Any:
        """Return an object with .publication and optional .manual_pack."""


@dataclass(frozen=True)
class PublishResult:
    publication: Publication
    manual_pack: dict | None = None


class PlaceholderRenderer:
    """Marks a file path without calling ffmpeg."""

    def render(self, experiment: Experiment, media_dir: Path) -> Experiment:
        file_path = str(Path(media_dir) / f"{experiment.id}.mp4")
        return mark_rendered(experiment, file_path)


class PlaceholderPublisher:
    """Posts when a token is present. Otherwise returns a manual pack."""

    def publish(self, experiment: Experiment, platform: Platform, account_id: str, token: str | None = None):
        platform = platform if isinstance(platform, Platform) else Platform(platform)
        if token and token.strip():
            publication = Publication(
                id=f"pub-{uuid4().hex}",
                experiment_id=experiment.id,
                platform=platform,
                account_id=account_id,
                status=PublicationStatus.posted,
                post_url=f"https://{platform.value}.example/{account_id}/{experiment.id}",
            )
            return PublishResult(publication=publication)
        publication = Publication(
            id=f"pub-{uuid4().hex}",
            experiment_id=experiment.id,
            platform=platform,
            account_id=account_id,
            status=PublicationStatus.manual_needed,
        )
        pack = {
            "experiment_id": experiment.id,
            "platform": platform.value,
            "account_id": account_id,
            "caption": experiment.caption,
            "file_path": experiment.file_path,
            "script": experiment.script,
        }
        return PublishResult(publication=publication, manual_pack=pack)


class ExperimentIn(BaseModel):
    id: str | None = None
    niche_id: str
    hypothesis: str
    hook_id: str
    script: str | None = None
    beats: list[dict[str, Any]] | None = None
    caption: str
    style: dict[str, Any]
    money: dict[str, Any]
    length_sec: int
    proposal_id: str | None = None
    language: str = "en"
    measurement_window_days: int = 7


class ThemeIn(BaseModel):
    id: str
    name: str
    language: str = "en"


class NicheIn(BaseModel):
    id: str
    theme_id: str
    name: str


class StoryboardIn(BaseModel):
    beats: list[dict[str, Any]]


class ApproveIn(BaseModel):
    now: str


class PublicationIn(BaseModel):
    platform: str
    account_id: str
    token: str | None = None


class UrlIn(BaseModel):
    url: str


class StarterIn(BaseModel):
    niche_ids: list[str]
    money: dict[str, Any]
    hook_id: str
    voice_id: str
    presenter_id: str


class SnapshotIn(BaseModel):
    publication_id: str
    views: int = 0
    watch_time_seconds: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    captured_at: str | None = None
    failed: bool = False


class _ThreadSafeStore:
    """Serialize store calls and let FastAPI's worker threads use the file.

    Store opens SQLite on the caller's thread. Sync routes run on a worker
    thread, so the API reopens a file database with the thread check off.
    """

    def __init__(self, store):
        _share_sqlite(store)
        self._store = store
        self._lock = threading.Lock()

    def __getattr__(self, name):
        attr = getattr(self._store, name)
        if not callable(attr):
            return attr

        def locked(*args, **kwargs):
            with self._lock:
                return attr(*args, **kwargs)

        return locked


def _share_sqlite(store) -> None:
    path = getattr(store, "path", None)
    conn = getattr(store, "_conn", None)
    if path is None or conn is None or str(path) == ":memory:":
        return
    conn.close()
    shared = sqlite3.connect(str(path), check_same_thread=False)
    shared.row_factory = sqlite3.Row
    store._conn = shared


def create_app(store, renderer: Renderer | None = None, publisher: Publisher | None = None) -> FastAPI:
    store = _ThreadSafeStore(store)
    renderer = renderer or PlaceholderRenderer()
    publisher = publisher or PlaceholderPublisher()
    app = FastAPI(title="Dead Internet")
    app.state.store = store

    @app.exception_handler(InvalidTransition)
    def invalid_transition(_request, exc: InvalidTransition):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(RenderCapReached)
    def render_cap(_request, exc: RenderCapReached):
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    @app.exception_handler(IneligibleLength)
    def ineligible_length(_request, exc: IneligibleLength):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(ProposalRejected)
    def proposal_rejected(_request, exc: ProposalRejected):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(InvalidBoard)
    def invalid_board(_request, exc: InvalidBoard):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.get("/catalog")
    def get_catalog():
        catalog = store.catalog()
        return {
            "themes": [
                {"id": theme.id, "name": theme.name, "language": theme.language}
                for theme in store.list_themes()
            ],
            "niches": [
                {"id": niche.id, "theme_id": niche.theme_id, "name": niche.name}
                for niche in store.list_niches()
            ],
            "theme_ids": sorted(catalog.theme_ids),
            "niche_ids": sorted(catalog.niche_ids),
            "presenter_ids": sorted(catalog.presenter_ids),
            "voice_ids": sorted(catalog.voice_ids),
            "hook_ids": sorted(catalog.hook_ids),
            "offer_ids": sorted(catalog.offer_ids),
        }

    @app.post("/themes")
    def create_theme(body: ThemeIn):
        try:
            check_segment(body.id)
        except UnsafeId as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        store.upsert_theme(body.id, body.name, body.language)
        theme = store.get_theme(body.id)
        return {"id": theme.id, "name": theme.name, "language": theme.language}

    @app.post("/niches")
    def create_niche(body: NicheIn):
        try:
            check_segment(body.id)
            check_segment(body.theme_id)
        except UnsafeId as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if store.get_theme(body.theme_id) is None:
            raise HTTPException(status_code=422, detail=f"unknown theme {body.theme_id}")
        store.upsert_niche(body.id, body.theme_id, body.name)
        niche = store.get_niche(body.id)
        return {"id": niche.id, "theme_id": niche.theme_id, "name": niche.name}

    @app.get("/experiments")
    def get_experiments():
        return [_experiment_json(store, row) for row in store.list_experiments()]

    @app.post("/experiments")
    def create_experiment(body: ExperimentIn):
        raw = body.model_dump()
        try:
            beats = _beats_from_payload(raw)
            experiment = _experiment_from_body(raw, beats)
            niche = _require_niche(store, experiment.niche_id)
            check_segment(experiment.id)
        except (KeyError, ValueError, TypeError, UnsafeId) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        path = storyboard_path(_media_dir(store), niche.theme_id, niche.id, experiment.id)
        write_storyboard(path, beats)
        store.insert_experiment(experiment)
        return _experiment_json(store, experiment)

    @app.get("/experiments/{experiment_id}/storyboard")
    def get_storyboard(experiment_id: str):
        _require_experiment(store, experiment_id)
        beats, _digest = _load_board(store, experiment_id)
        return {"beats": [_beat_json(beat) for beat in beats]}

    @app.put("/experiments/{experiment_id}/storyboard")
    def put_storyboard(experiment_id: str, body: StoryboardIn):
        experiment = _require_experiment(store, experiment_id)
        if experiment.status not in {Status.draft, Status.board_approved, Status.render_failed}:
            raise HTTPException(
                status_code=409,
                detail=f"{experiment.status.value} cannot revise_board",
            )
        try:
            beats = _beats_from_payload({"beats": body.beats})
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        niche = _require_niche(store, experiment.niche_id)
        path = storyboard_path(_media_dir(store), niche.theme_id, niche.id, experiment.id)
        write_storyboard(path, beats)
        store.save_experiment(revise_board(experiment, beats))
        return _experiment_json(store, store.get_experiment(experiment.id))

    @app.post("/experiments/{experiment_id}/approve-board")
    def approve_storyboard(experiment_id: str):
        experiment = _require_experiment(store, experiment_id)
        beats, digest = _load_board(store, experiment_id)
        approved = approve_board(experiment, beats, digest)
        store.save_experiment(approved)
        return _experiment_json(store, approved)

    @app.post("/experiments/{experiment_id}/render")
    def render_experiment(experiment_id: str):
        experiment = _require_experiment(store, experiment_id)
        if experiment.status not in {Status.board_approved, Status.render_failed}:
            request_render(experiment, 0)
        niche = _require_niche(store, experiment.niche_id)
        path = storyboard_path(_media_dir(store), niche.theme_id, niche.id, experiment.id)
        beats, digest = _load_board(store, experiment_id)
        if digest != experiment.board_hash:
            store.save_experiment(revise_board(experiment, beats))
            raise HTTPException(status_code=409, detail="storyboard changed since approval")
        experiment = replace(experiment, script=script_from_beats(beats))
        day = _today()
        started = store.renders_started_today(day) or 0
        rendering = request_render(experiment, int(started), cap=_render_cap(store))
        store.record_render_start(experiment.id, day)
        rendered = renderer.render(rendering, path.parent)
        store.save_experiment(rendered)
        return _experiment_json(store, rendered)

    @app.post("/experiments/{experiment_id}/approve")
    def approve_experiment(experiment_id: str, body: ApproveIn):
        experiment = _require_experiment(store, experiment_id)
        approved = approve(experiment, now=body.now)
        store.save_experiment(approved)
        return _experiment_json(store, approved)

    @app.post("/experiments/{experiment_id}/reject")
    def reject_experiment(experiment_id: str):
        experiment = _require_experiment(store, experiment_id)
        rejected = reject(experiment)
        store.save_experiment(rejected)
        return _experiment_json(store, rejected)

    @app.post("/experiments/{experiment_id}/complete")
    def complete_experiment(experiment_id: str):
        experiment = _require_experiment(store, experiment_id)
        closed = complete(experiment)
        store.save_experiment(closed)
        return _experiment_json(store, closed)

    @app.post("/experiments/{experiment_id}/publications")
    def publish_experiment(experiment_id: str, body: PublicationIn):
        experiment = _require_experiment(store, experiment_id)
        if experiment.status not in (Status.approved, Status.live):
            raise HTTPException(status_code=409, detail=f"{experiment.status.value} cannot post")
        try:
            platform = Platform(body.platform)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        result = publisher.publish(experiment, platform, body.account_id, token=body.token)
        publication = result.publication
        if publication.post_url:
            existing = store.publication_by_url(experiment.id, publication.post_url)
            if existing is not None:
                store.save_experiment(mark_posted(experiment))
                return _publication_json(existing)
        stored = store.add_publication(publication)
        if isinstance(stored, Publication):
            publication = stored
        if publication.post_url:
            store.save_experiment(mark_posted(experiment))
        payload = _publication_json(publication)
        manual_pack = getattr(result, "manual_pack", None)
        if manual_pack:
            payload["manual_pack"] = manual_pack
        return payload

    @app.post("/publications/{publication_id}/url")
    def set_publication_url(publication_id: str, body: UrlIn):
        publication = _require_publication(store, publication_id)
        if publication.status != PublicationStatus.manual_needed:
            raise HTTPException(status_code=409, detail="publication is not waiting for a url")
        if not body.url:
            raise HTTPException(status_code=422, detail="url is required")
        experiment = _require_experiment(store, publication.experiment_id)
        if experiment.status not in (Status.approved, Status.live):
            raise HTTPException(status_code=409, detail=f"{experiment.status.value} cannot post")
        updated = replace(publication, status=PublicationStatus.posted, post_url=body.url, error=None)
        store.save_publication(updated)
        store.save_experiment(mark_posted(experiment))
        return _publication_json(updated)

    @app.get("/results")
    def results():
        experiments = list(store.list_experiments())
        rows = []
        for experiment in experiments:
            payload = _experiment_json(store, experiment)
            payload["below_sample_floor"] = below_sample_floor(cell_size(experiments, experiment))
            rows.append(payload)
        return rows

    @app.post("/starter")
    def start_grid(body: StarterIn):
        try:
            money = _money_from(body.money)
            niches = [_require_niche(store, niche_id) for niche_id in body.niche_ids]
            drafts = starter_grid(
                body.niche_ids, money, body.hook_id, body.voice_id, body.presenter_id
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        created = []
        niche_by_id = {niche.id: niche for niche in niches}
        for draft in drafts:
            experiment = _experiment_from_draft(draft)
            niche = niche_by_id[draft.niche_id]
            path = storyboard_path(_media_dir(store), niche.theme_id, niche.id, experiment.id)
            write_storyboard(path, draft.beats)
            store.insert_experiment(experiment)
            created.append(_experiment_json(store, experiment))
        return created

    @app.post("/suggest")
    def suggest_next():
        experiments = list(store.list_experiments())
        catalog = store.catalog()
        drafts = suggest(experiments, catalog)
        return [_draft_json(draft) for draft in drafts]

    @app.get("/r/{code}")
    def redirect_click(code: str):
        try:
            _count, destination = hit(store, code)
        except KeyError:
            raise HTTPException(status_code=404, detail="unknown tracking code") from None
        return RedirectResponse(url=destination, status_code=302)

    @app.post("/snapshots")
    def create_snapshot(body: SnapshotIn):
        record_snapshot(store, body.publication_id, body.model_dump())
        return {"ok": True}

    return app


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _render_cap(store) -> int:
    method = store.get_setting
    try:
        raw = method("render_cap", 8)
    except TypeError:
        try:
            raw = method("render_cap")
        except KeyError:
            return 8
    if raw is None or raw == "":
        return 8
    if isinstance(raw, str):
        raw = raw.strip()
    return int(raw)


def _media_dir(store) -> Path:
    raw = getattr(store, "path", None)
    if raw is None:
        raw = getattr(store, "db_path", None)
    if raw is None:
        raw = getattr(store, "_path", None)
    if raw is None:
        return Path("data") / "media"
    return Path(str(raw)).resolve().parent / "media"


def _require_experiment(store, experiment_id: str) -> Experiment:
    try:
        experiment = store.get_experiment(experiment_id)
    except KeyError:
        experiment = None
    if experiment is None:
        raise HTTPException(status_code=404, detail="unknown experiment")
    return experiment


def _publications(store) -> list[Publication]:
    method = store.list_publications
    try:
        return list(method())
    except TypeError:
        rows: list[Publication] = []
        for experiment in store.list_experiments():
            rows.extend(method(experiment.id))
        return rows


def _require_publication(store, publication_id: str) -> Publication:
    for row in _publications(store):
        if row.id == publication_id:
            return row
    raise HTTPException(status_code=404, detail="unknown publication")


def _beats_from_payload(raw: dict) -> tuple[Beat, ...]:
    beats = raw.get("beats")
    if beats is not None:
        parsed: list[Beat] = []
        for item in beats:
            if not isinstance(item, dict) or "spoken" not in item:
                raise ValueError("beat needs a spoken line")
            parsed.append(
                Beat(
                    spoken=str(item["spoken"]),
                    on_screen=str(item.get("on_screen") or ""),
                    visual_note=str(item.get("visual_note") or ""),
                )
            )
        return tuple(parsed)
    if raw.get("script") is None:
        raise ValueError("script or beats is required")
    return (Beat(spoken=str(raw["script"]), on_screen="", visual_note=""),)


def _require_niche(store, niche_id: str):
    check_segment(niche_id)
    niche = store.get_niche(niche_id)
    if niche is None:
        raise HTTPException(status_code=422, detail=f"unknown niche {niche_id}")
    check_segment(niche.theme_id)
    return niche


def _load_board(store, experiment_id: str) -> tuple[tuple[Beat, ...], str]:
    experiment = _require_experiment(store, experiment_id)
    niche = _require_niche(store, experiment.niche_id)
    path = storyboard_path(_media_dir(store), niche.theme_id, niche.id, experiment.id)
    try:
        return read_storyboard(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail="storyboard file is missing") from exc


def _beat_json(beat: Beat) -> dict[str, str]:
    return {
        "spoken": beat.spoken,
        "on_screen": beat.on_screen,
        "visual_note": beat.visual_note,
    }


def _experiment_from_body(raw: dict, beats: tuple[Beat, ...]) -> Experiment:
    return Experiment(
        id=raw.get("id") or uuid4().hex,
        niche_id=raw["niche_id"],
        hypothesis=raw["hypothesis"],
        hook_id=raw["hook_id"],
        script=script_from_beats(beats),
        caption=raw["caption"],
        style=_style_from(raw["style"]),
        money=_money_from(raw["money"]),
        status=Status.draft,
        length_sec=int(raw["length_sec"]),
        proposal_id=raw.get("proposal_id"),
        language=raw.get("language") or "en",
        measurement_window_days=int(raw.get("measurement_window_days") or 7),
    )


def _experiment_from_draft(draft: DraftSpec) -> Experiment:
    return Experiment(
        id=uuid4().hex,
        niche_id=draft.niche_id,
        hypothesis=draft.hypothesis,
        hook_id=draft.hook_id,
        script=draft.script,
        caption=draft.caption,
        style=draft.style,
        money=draft.money,
        status=Status.draft,
        length_sec=draft.length_sec,
    )


def _style_json(style: Style) -> dict:
    kind = style.kind
    if kind == "faceless":
        return {
            "kind": "faceless",
            "look": style.look.value,
            "voice_id": style.voice_id,
            "caption_style": style.caption_style,
        }
    return {
        "kind": "avatar",
        "presenter_id": style.presenter_id,
        "voice_id": style.voice_id,
    }


def _money_json(money) -> dict:
    if money.kind == "affiliate":
        return {"kind": "affiliate", "tracking_code": money.tracking_code, "merchant": money.merchant}
    if money.kind == "own_offer":
        return {"kind": "own_offer", "tracking_code": money.tracking_code, "offer_url": money.offer_url}
    return {"kind": "platform_payout", "platform": money.platform.value}


def _experiment_json(store, experiment: Experiment) -> dict:
    niche = store.get_niche(experiment.niche_id)
    return {
        "id": experiment.id,
        "theme_id": None if niche is None else niche.theme_id,
        "niche_id": experiment.niche_id,
        "hypothesis": experiment.hypothesis,
        "hook_id": experiment.hook_id,
        "script": experiment.script,
        "caption": experiment.caption,
        "style": _style_json(experiment.style),
        "money": _money_json(experiment.money),
        "status": experiment.status.value,
        "length_sec": experiment.length_sec,
        "proposal_id": experiment.proposal_id,
        "approved_at": experiment.approved_at,
        "measurement_window_days": experiment.measurement_window_days,
        "file_path": experiment.file_path,
        "render_error": experiment.render_error,
        "language": experiment.language,
        "clicks": experiment.clicks,
        "revenue_cents": experiment.revenue_cents,
        "board_hash": experiment.board_hash,
    }


def _publication_json(publication: Publication) -> dict:
    platform = publication.platform.value if isinstance(publication.platform, Platform) else publication.platform
    status = publication.status.value if isinstance(publication.status, PublicationStatus) else publication.status
    return {
        "id": publication.id,
        "experiment_id": publication.experiment_id,
        "platform": platform,
        "account_id": publication.account_id,
        "status": status,
        "post_url": publication.post_url,
        "error": publication.error,
        "payout_cents": publication.payout_cents,
    }


def _draft_json(draft: DraftSpec) -> dict:
    return {
        "parent_ids": list(draft.parent_ids),
        "factor_diffs": [
            {"field": diff.field, "parent_value": diff.parent_value, "next_value": diff.next_value}
            for diff in draft.factor_diffs
        ],
        "niche_id": draft.niche_id,
        "style": _style_json(draft.style),
        "money": _money_json(draft.money),
        "hook_id": draft.hook_id,
        "hypothesis": draft.hypothesis,
        "script": draft.script,
        "caption": draft.caption,
        "length_sec": draft.length_sec,
        "beats": [_beat_json(beat) for beat in draft.beats],
    }

"""HTTP commands for experiments, the click redirect, and metric snapshots."""

import re
import sqlite3
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from deadinternet.domain.experiment import (
    Affiliate,
    AvatarStyle,
    Beat,
    Experiment,
    FactorDiff,
    IneligibleLength,
    InvalidBoard,
    InvalidTransition,
    OwnOffer,
    Platform,
    PlatformPayout,
    Publication,
    PublicationStatus,
    RenderCapReached,
    Status,
    Style,
    approve,
    approve_board,
    complete,
    mark_posted,
    mark_render_failed,
    mark_rendered,
    reject,
    request_render,
    revise_board,
    script_from_beats,
    style_key,
)
from deadinternet.storyboard import (
    UnsafeId,
    check_segment,
    read_storyboard,
    storyboard_path,
    write_storyboard,
)
from deadinternet.domain.proposal import (
    Catalog,
    DraftSpec,
    ProposalRejected,
    _money_from,
    _money_path_key,
    _style_from,
    changed_factors,
    starter_grid,
)
from deadinternet.propose.agent import ProposerFailed, ProposerUnavailable
from deadinternet.domain.rank import (
    SAMPLE_FLOOR,
    below_sample_floor,
    cell_size,
    eligible_parents,
    suggest,
)
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


class Proposer(Protocol):
    def propose(self, experiments: list[Experiment], catalog: Catalog) -> list[DraftSpec]:
        """Return the next drafts. Do not persist them."""


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
    # US-031: lineage an accepted draft carries. The declared factor_diffs
    # are advisory only; the server derives what it stores.
    parent_ids: list[str] | None = None
    factor_diffs: list[dict[str, Any]] | None = None
    language: str = "en"
    measurement_window_days: int = Field(default=7, ge=1)


class ThemeIn(BaseModel):
    id: str
    name: str
    language: str = "en"


class NicheIn(BaseModel):
    id: str
    theme_id: str
    name: str


class OfferIn(BaseModel):
    id: str
    url: str
    name: str | None = None
    merchant: str = ""


class StoryboardIn(BaseModel):
    beats: list[dict[str, Any]]


class ApproveIn(BaseModel):
    now: str


class CompleteIn(BaseModel):
    force: bool = False


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
    views: int = Field(default=0, ge=0)
    watch_time_seconds: int = Field(default=0, ge=0)
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    captured_at: str | None = None
    failed: bool = False


class RevenueIn(BaseModel):
    amount_cents: int = Field(ge=1)
    note: str = ""


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


def create_app(
    store,
    renderer: Renderer | None = None,
    publisher: Publisher | None = None,
    proposer: Proposer | None = None,
) -> FastAPI:
    store = _ThreadSafeStore(store)
    renderer = renderer or PlaceholderRenderer()
    publisher = publisher or PlaceholderPublisher()
    app = FastAPI(title="Dead Internet")
    app.state.store = store
    # The cap check and the per-experiment claim must be one atomic step:
    # separate store locks let two requests both pass an 8-cap (or both
    # run ffmpeg on the same output path).
    render_gate = threading.Lock()
    renders_in_flight: set[str] = set()

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

    @app.exception_handler(ProposerUnavailable)
    def proposer_unavailable(_request, exc: ProposerUnavailable):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(ProposerFailed)
    def proposer_failed(_request, exc: ProposerFailed):
        return JSONResponse(status_code=502, content={"detail": str(exc)})

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
            "render_cap": _render_cap(store),
        }

    @app.post("/themes")
    def create_theme(body: ThemeIn):
        try:
            check_segment(body.id)
        except UnsafeId as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        existing = store.get_theme(body.id)
        if existing is not None and (existing.name, existing.language) != (body.name, body.language):
            raise HTTPException(
                status_code=409,
                detail=f"theme {body.id} already exists as {existing.name}/{existing.language}",
            )
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
        existing = store.get_niche(body.id)
        if existing is not None and (existing.theme_id, existing.name) != (body.theme_id, body.name):
            raise HTTPException(
                status_code=409,
                detail=f"niche {body.id} already exists under theme {existing.theme_id}",
            )
        store.upsert_niche(body.id, body.theme_id, body.name)
        niche = store.get_niche(body.id)
        return {"id": niche.id, "theme_id": niche.theme_id, "name": niche.name}

    @app.post("/offers")
    def create_offer(body: OfferIn):
        try:
            check_segment(body.id)
        except UnsafeId as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        url = body.url.strip()
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=422, detail="offer url must start with http:// or https://")
        store.upsert_offer(body.id, body.name or body.id, url, body.merchant or body.id)
        offer = store.get_offer(body.id)
        return {"id": offer["id"], "name": offer["name"], "url": offer["url"], "merchant": offer["merchant"]}

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
        parent_ids, factor_diffs = _lineage(store, raw, experiment)
        experiment = replace(experiment, parent_ids=parent_ids, factor_diffs=factor_diffs)
        _guard_length(experiment)
        _reject_unusable_own_offer_url(experiment.money)
        _reject_unsafe_tracking_code(experiment.money)
        _reject_known_tracking_code(store, experiment)
        try:
            store.insert_experiment(experiment)
        except sqlite3.IntegrityError as exc:
            # With UUID ids the realistic clash is the unique tracking-code
            # index, not the id; report the code the operator can act on.
            if "experiments_tracking_code" in str(exc):
                code = getattr(experiment.money, "tracking_code", "")
                raise HTTPException(
                    status_code=409,
                    detail=f"tracking code {code} is already used",
                ) from exc
            raise HTTPException(
                status_code=409,
                detail=f"experiment {experiment.id} already exists",
            ) from exc
        path = storyboard_path(_media_dir(store), niche.theme_id, niche.id, experiment.id)
        write_storyboard(path, beats)
        _remember_catalog(store, experiment)
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
        with render_gate:
            if experiment_id in renders_in_flight:
                raise HTTPException(status_code=409, detail="a render is already in progress")
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
            renders_in_flight.add(experiment_id)
        try:
            rendered = renderer.render(rendering, path.parent)
            store.save_experiment(rendered)
        except Exception as exc:
            # A crash between the claim and the save would strand the row in
            # `rendering` forever: no route can re-enter that state except
            # this one, so the failure is recorded before it propagates. A
            # finished render whose SAVE then failed is marked failed too —
            # recoverable-wrong beats unrecoverable-stuck, since render_failed
            # can re-render. The 500 carries the reason so the dashboard
            # names it instead of showing a generic failure.
            store.save_experiment(mark_render_failed(rendering, str(exc)))
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            # Keep the in-flight claim until the result is saved: releasing it
            # earlier would let a same-experiment request re-read the stale
            # status and start a second ffmpeg on the same output path.
            with render_gate:
                renders_in_flight.discard(experiment_id)
        return _experiment_json(store, rendered)

    @app.post("/experiments/{experiment_id}/approve")
    def approve_experiment(experiment_id: str, body: ApproveIn):
        experiment = _require_experiment(store, experiment_id)
        # An unparseable `now` would make the measurement window silently
        # never close (US-027): _reject_before_window_end and _clicks_window
        # both no-op on a value _parse_iso cannot read.
        if _parse_iso(body.now) is None:
            raise HTTPException(status_code=422, detail="now must be an ISO timestamp")
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
    def complete_experiment(experiment_id: str, body: CompleteIn | None = None):
        experiment = _require_experiment(store, experiment_id)
        if not (body and body.force):
            _reject_before_window_end(experiment)
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
        _require_text(body.account_id, "account_id")
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
        url = body.url.strip()
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=422, detail="url must start with http:// or https://")
        experiment = _require_experiment(store, publication.experiment_id)
        if experiment.status not in (Status.approved, Status.live):
            raise HTTPException(status_code=409, detail=f"{experiment.status.value} cannot post")
        updated = replace(publication, status=PublicationStatus.posted, post_url=url, error=None)
        try:
            store.save_publication(updated)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="that url is already stored for this experiment",
            ) from exc
        store.save_experiment(mark_posted(experiment))
        return _publication_json(updated)

    @app.get("/results")
    def results():
        experiments = list(store.list_experiments())
        rows = []
        for experiment in experiments:
            payload = _experiment_json(store, experiment)
            payload["views"] = _views_for(store, experiment.id)
            payload["clicks_window"] = _clicks_window(store, experiment)
            payload["below_sample_floor"] = below_sample_floor(cell_size(experiments, experiment))
            rows.append(payload)
        return rows

    @app.post("/starter")
    def start_grid(body: StarterIn):
        try:
            _require_text(body.hook_id, "hook_id")
            _require_text(body.voice_id, "voice_id")
            _require_text(body.presenter_id, "presenter_id")
            if not body.niche_ids or any(not str(niche).strip() for niche in body.niche_ids):
                raise HTTPException(status_code=422, detail="niche_ids is required")
            money = _money_from(body.money)
            # A blank code would mint "-avatar"/"-avatar-2" drafts that
            # credit nobody; the operator has to name the code.
            if isinstance(money, (Affiliate, OwnOffer)) and not money.tracking_code.strip():
                raise HTTPException(status_code=422, detail="tracking_code is required")
            _reject_unsafe_tracking_code(money)
            _reject_unusable_own_offer_url(money)
            niches = [_require_niche(store, niche_id) for niche_id in body.niche_ids]
            drafts = starter_grid(
                body.niche_ids,
                money,
                body.hook_id.strip(),
                body.voice_id.strip(),
                body.presenter_id.strip(),
            )
        except HTTPException:
            raise
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        created = []
        niche_by_id = {niche.id: niche for niche in niches}
        # Known behavior (audited 2026-11-19): each draft is its own
        # transaction. No reachable input fails mid-loop — codes are minted
        # per draft against the store and ids are UUIDs — but a mid-loop IO
        # error would leave the earlier drafts stored. The operator can
        # reject them; the grid is not rolled back.
        for draft in drafts:
            experiment = _experiment_from_draft(draft)
            niche = niche_by_id[draft.niche_id]
            _guard_length(experiment)
            experiment = _mint_unique_tracking_code(store, experiment)
            try:
                store.insert_experiment(experiment)
            except sqlite3.IntegrityError as exc:
                if "experiments_tracking_code" in str(exc):
                    code = getattr(experiment.money, "tracking_code", "")
                    raise HTTPException(
                        status_code=409,
                        detail=f"tracking code {code} is already used",
                    ) from exc
                raise HTTPException(
                    status_code=409,
                    detail=f"experiment {experiment.id} already exists",
                ) from exc
            path = storyboard_path(_media_dir(store), niche.theme_id, niche.id, experiment.id)
            write_storyboard(path, draft.beats)
            _remember_catalog(store, experiment)
            created.append(_experiment_json(store, experiment))
        return created

    @app.post("/suggest")
    def suggest_next():
        experiments = list(store.list_experiments())
        catalog = store.catalog()
        # The honest ranker's floor applies to every path (US-027): with no
        # eligible parent there is nothing to propose from, and a silent []
        # would read as "nothing to do" instead of "cells are too thin".
        if not eligible_parents(experiments):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"no finished cell has {SAMPLE_FLOOR} completed videos; "
                    "every cell is too thin to name a cause"
                ),
            )
        if proposer is None:
            drafts = suggest(experiments, catalog)
        else:
            drafts = proposer.propose(experiments, catalog)
        return [_draft_json(draft) for draft in drafts]

    @app.get("/r/{code}")
    def redirect_click(code: str):
        try:
            _count, destination = hit(store, code)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc) or "unknown tracking code") from None
        return RedirectResponse(url=destination, status_code=302)

    @app.post("/snapshots")
    def create_snapshot(body: SnapshotIn):
        _require_publication(store, body.publication_id)
        # Snapshots order by captured_at as a string (US-030): mixed offsets
        # or a space separator would sort wrongly, so a parseable value is
        # normalised to UTC Z-form and an unparseable one is refused.
        if body.captured_at is not None:
            parsed = _parse_iso(body.captured_at)
            if parsed is None:
                raise HTTPException(status_code=422, detail="captured_at must be an ISO timestamp")
            body.captured_at = (
                parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            )
        record_snapshot(store, body.publication_id, body.model_dump())
        return {"ok": True}

    @app.post("/experiments/{experiment_id}/revenue")
    def record_revenue(experiment_id: str, body: RevenueIn):
        experiment = _require_experiment(store, experiment_id)
        entry = store.record_revenue(
            experiment.id,
            body.amount_cents,
            body.note.strip(),
            _now(),
        )
        return {
            "entry": entry,
            "revenue_cents": store.get_experiment(experiment.id).revenue_cents,
        }

    @app.get("/experiments/{experiment_id}/revenue")
    def list_revenue(experiment_id: str):
        _require_experiment(store, experiment_id)
        return store.list_revenue_entries(experiment_id)

    @app.get("/publications/{publication_id}/snapshots")
    def list_publication_snapshots(publication_id: str):
        _require_publication(store, publication_id)
        return list(reversed(store.list_snapshots(publication_id)))

    @app.get("/experiments/{experiment_id}/publications")
    def list_experiment_publications(experiment_id: str):
        _require_experiment(store, experiment_id)
        return [_publication_json(row) for row in store.list_publications(experiment_id)]

    @app.get("/media/{experiment_id}")
    def media_file(experiment_id: str):
        experiment = _require_experiment(store, experiment_id)
        path = _media_file(store, experiment.file_path)
        if path is None:
            raise HTTPException(status_code=404, detail="rendered file is not available")
        return FileResponse(path, media_type="video/mp4", filename=path.name)

    return app


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 8


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


def _views_for(store, experiment_id: str) -> int:
    """Sum the latest snapshot views of every publication of one experiment."""
    total = 0
    for publication in store.list_publications(experiment_id):
        snapshots = store.list_snapshots(publication.id)
        if snapshots:
            total += int(snapshots[-1]["views"])
    return total


def _clicks_window(store, experiment: Experiment) -> int:
    """Clicks recorded between approved_at and the end of the measurement
    window (US-025). An experiment that was never approved has no window
    yet, so nothing is windowed (0) until approve stamps approved_at."""
    if not experiment.approved_at:
        return 0
    start = _parse_iso(experiment.approved_at)
    if start is None:
        return 0
    end = start + timedelta(days=experiment.measurement_window_days)
    windowed = 0
    for created_at in store.list_click_times(experiment.id):
        moment = _parse_iso(created_at)
        if moment is not None and start <= moment <= end:
            windowed += 1
    return windowed


def _parse_iso(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=422, detail=f"{label} is required")


def _guard_length(experiment: Experiment) -> None:
    """A TikTok Creator Rewards draft the lab can never approve is refused now."""
    if (
        isinstance(experiment.money, PlatformPayout)
        and experiment.money.platform is Platform.tiktok
        and experiment.length_sec <= 60
    ):
        raise IneligibleLength("TikTok Creator Rewards videos must be longer than 60 seconds")


def _reject_unusable_own_offer_url(money) -> None:
    """A click on /r/{code} opens this URL (US-011): it must exist and be a
    web URL on every creation path, or the counted click 302s nowhere. The
    RAW value is judged — the store keeps what was sent, so a padded URL
    that only looks clean after strip() is refused outright."""
    if not isinstance(money, OwnOffer):
        return
    url = money.offer_url
    if not url.strip():
        raise HTTPException(status_code=422, detail="own_offer money needs an offer_url")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="own_offer offer_url must start with http:// or https://")


_SAFE_CODE_RE = re.compile(r"[A-Za-z0-9._~-]+")


def _reject_unsafe_tracking_code(money) -> None:
    """The code becomes the /r/{code} path segment (US-024): a code with a
    space or a slash can never be hit, so it never reaches the store. The
    RAW value is judged, so `" abc "` is refused rather than stored with
    the padding; dot-only codes are refused as path-traversal shapes."""
    if not isinstance(money, (Affiliate, OwnOffer)):
        return
    code = money.tracking_code
    if not code:
        return
    if not _SAFE_CODE_RE.fullmatch(code) or not code.strip("."):
        raise HTTPException(
            status_code=422,
            detail="tracking_code must be letters, digits, dots, hyphens, or underscores",
        )


def _reject_known_tracking_code(store, experiment: Experiment) -> None:
    """Two experiments sharing a code would split one click counter."""
    money = experiment.money
    if not isinstance(money, (Affiliate, OwnOffer)) or not money.tracking_code:
        return
    for row in store.list_experiments():
        if row.id == experiment.id:
            continue
        other = row.money
        if isinstance(other, (Affiliate, OwnOffer)) and other.tracking_code == money.tracking_code:
            raise HTTPException(
                status_code=422,
                detail=f"tracking code {money.tracking_code} is already used by {row.id}",
            )


def _mint_unique_tracking_code(store, experiment: Experiment) -> Experiment:
    """Every video gets its own code (US-024): starter drafts over several
    niches would otherwise share one code and split one click counter.
    The operator names the code on POST /experiments (refused on a clash);
    the starter grid recodes its drafts instead."""
    money = experiment.money
    if not isinstance(money, (Affiliate, OwnOffer)) or not money.tracking_code:
        return experiment
    code = store.mint_tracking_code(money.tracking_code)
    if code == money.tracking_code:
        return experiment
    return replace(experiment, money=replace(money, tracking_code=code))


def _reject_before_window_end(experiment: Experiment) -> None:
    """A day-7 verdict needs the full window (US-027): completing early can
    crown a false winner, so the operator must wait or explicitly force it."""
    if not experiment.approved_at:
        return
    start = _parse_iso(experiment.approved_at)
    if start is None:
        return
    end = start + timedelta(days=experiment.measurement_window_days)
    if datetime.now(timezone.utc) < end:
        raise HTTPException(
            status_code=409,
            detail=(
                f"measurement window ends {end.isoformat()}; "
                'complete after it closes, or send {"force": true} to override'
            ),
        )


def _remember_catalog(store, experiment: Experiment) -> None:
    """Register the ids a new draft uses so suggest can accept them later.

    The niche is deliberately not written: it must already exist, and the
    experiment's niche_id carries its real theme.
    """
    hook = experiment.hook_id.strip()
    if hook:
        store.upsert_hook(hook, hook)
    voice = experiment.style.voice_id.strip()
    if voice:
        store.upsert_voice(voice, voice, "local")
    if isinstance(experiment.style, AvatarStyle):
        presenter = experiment.style.presenter_id.strip()
        if presenter:
            store.upsert_presenter(presenter, presenter, "local")
    money = experiment.money
    if isinstance(money, Affiliate):
        merchant = money.merchant.strip()
        if merchant:
            store.upsert_offer(merchant, merchant, "", merchant=merchant)
    elif isinstance(money, OwnOffer):
        url = money.offer_url.strip()
        if url:
            store.upsert_offer(url, url, url)


def _media_file(store, file_path: str | None) -> Path | None:
    """The rendered file, but only when it lives inside the media directory."""
    if not file_path:
        return None
    path = Path(file_path).resolve()
    root = _media_dir(store).resolve()
    if root not in path.parents or not path.is_file():
        return None
    return path


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


def _lineage(store, raw: dict, experiment: Experiment) -> tuple[tuple[str, ...], tuple[FactorDiff, ...]]:
    """US-031: an accepted draft keeps its parents, and the stored factor
    list is derived from those parents with changed_factors. The declared
    list is advisory only: the server never writes what the body claimed."""
    parent_ids = tuple(str(item) for item in raw.get("parent_ids") or ())
    if not parent_ids:
        return (), ()
    parents = []
    for parent_id in parent_ids:
        try:
            parents.append(store.get_experiment(parent_id))
        except KeyError:
            raise HTTPException(status_code=422, detail=f"unknown parent {parent_id}") from None
    draft = DraftSpec(
        parent_ids=parent_ids,
        factor_diffs=(),
        niche_id=experiment.niche_id,
        style=experiment.style,
        money=experiment.money,
        hook_id=experiment.hook_id,
        hypothesis=experiment.hypothesis,
        script=experiment.script,
        caption=experiment.caption,
        length_sec=experiment.length_sec,
    )
    diffs: list[FactorDiff] = []
    for parent in parents:
        for field in changed_factors(draft, parent):
            parent_value, next_value = _factor_values(field, draft, parent)
            diffs.append(
                FactorDiff(field=field, parent_value=parent_value, next_value=next_value)
            )
    return parent_ids, tuple(diffs)


def _factor_values(field: str, draft: DraftSpec, parent: Experiment) -> tuple[str, str]:
    """The values on either side of one changed factor, as Results can name them."""
    if field == "niche":
        return parent.niche_id, draft.niche_id
    if field == "style":
        return "/".join(style_key(parent.style)), "/".join(style_key(draft.style))
    if field == "money":
        # The money factor is the path, not the click code: every child
        # mints its own code (US-024), so the diff names the path only.
        return "/".join(_money_path_key(parent.money)), "/".join(_money_path_key(draft.money))
    if field == "hook":
        return parent.hook_id, draft.hook_id
    return str(parent.length_sec), str(draft.length_sec)


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
        "parent_ids": list(experiment.parent_ids),
        "factor_diffs": [
            {"field": diff.field, "parent_value": diff.parent_value, "next_value": diff.next_value}
            for diff in experiment.factor_diffs
        ],
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

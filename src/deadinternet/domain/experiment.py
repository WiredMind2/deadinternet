from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Literal


class Status(StrEnum):
    draft = "draft"
    board_approved = "board_approved"
    rendering = "rendering"
    render_failed = "render_failed"
    in_review = "in_review"
    rejected = "rejected"
    approved = "approved"
    live = "live"
    complete = "complete"


class Look(StrEnum):
    stills = "stills"
    clips = "clips"


class Platform(StrEnum):
    tiktok = "tiktok"
    instagram = "instagram"
    youtube = "youtube"


class PublicationStatus(StrEnum):
    queued = "queued"
    manual_needed = "manual_needed"
    posted = "posted"
    failed = "failed"


class Event(StrEnum):
    approve_board = "approve_board"
    revise_board = "revise_board"
    start_render = "start_render"
    render_ok = "render_ok"
    render_fail = "render_fail"
    approve = "approve"
    reject = "reject"
    post = "post"
    complete = "complete"


class DomainError(Exception):
    pass


class InvalidTransition(DomainError):
    pass


class RenderCapReached(DomainError):
    pass


class IneligibleLength(DomainError):
    pass


class InvalidBoard(DomainError):
    pass


@dataclass(frozen=True)
class FacelessStyle:
    look: Look
    voice_id: str
    caption_style: str
    kind: Literal["faceless"] = "faceless"


@dataclass(frozen=True)
class AvatarStyle:
    presenter_id: str
    voice_id: str
    kind: Literal["avatar"] = "avatar"


Style = FacelessStyle | AvatarStyle


@dataclass(frozen=True)
class Affiliate:
    tracking_code: str
    merchant: str
    kind: Literal["affiliate"] = "affiliate"


@dataclass(frozen=True)
class PlatformPayout:
    platform: Platform
    kind: Literal["platform_payout"] = "platform_payout"


@dataclass(frozen=True)
class OwnOffer:
    tracking_code: str
    offer_url: str
    kind: Literal["own_offer"] = "own_offer"


Money = Affiliate | PlatformPayout | OwnOffer


@dataclass(frozen=True)
class Beat:
    spoken: str
    on_screen: str = ""
    visual_note: str = ""


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    language: str


@dataclass(frozen=True)
class Niche:
    id: str
    theme_id: str
    name: str


@dataclass(frozen=True)
class Experiment:
    id: str
    niche_id: str
    hypothesis: str
    hook_id: str
    script: str
    caption: str
    style: Style
    money: Money
    status: Status
    length_sec: int
    proposal_id: str | None = None
    approved_at: str | None = None
    measurement_window_days: int = 7
    file_path: str | None = None
    render_error: str | None = None
    language: str = "en"
    clicks: int = 0
    revenue_cents: int = 0
    board_hash: str | None = None


@dataclass(frozen=True)
class Publication:
    id: str
    experiment_id: str
    platform: Platform
    account_id: str
    status: PublicationStatus
    post_url: str | None = None
    error: str | None = None
    payout_cents: int = 0


_ALLOWED: dict[tuple[Status, Event], Status] = {
    (Status.draft, Event.approve_board): Status.board_approved,
    (Status.board_approved, Event.revise_board): Status.draft,
    (Status.board_approved, Event.start_render): Status.rendering,
    (Status.render_failed, Event.start_render): Status.rendering,
    (Status.render_failed, Event.revise_board): Status.draft,
    (Status.rendering, Event.render_ok): Status.in_review,
    (Status.rendering, Event.render_fail): Status.render_failed,
    (Status.in_review, Event.approve): Status.approved,
    (Status.in_review, Event.reject): Status.rejected,
    (Status.approved, Event.post): Status.live,
    (Status.live, Event.post): Status.live,
    (Status.live, Event.complete): Status.complete,
}


def transition(experiment: Experiment, event: Event) -> Experiment:
    nxt = _ALLOWED.get((experiment.status, event))
    if nxt is None:
        raise InvalidTransition(f"{experiment.status.value} cannot {event.value}")
    return replace(experiment, status=nxt)


def script_from_beats(beats: Sequence[Beat]) -> str:
    return "\n".join(beat.spoken for beat in beats)


def require_approvable(beats: Sequence[Beat]) -> None:
    if len(beats) < 1:
        raise InvalidBoard("storyboard needs at least one beat")
    for beat in beats:
        if not beat.spoken.strip():
            raise InvalidBoard("every beat needs a spoken line")


def approve_board(experiment: Experiment, beats: Sequence[Beat], board_hash: str) -> Experiment:
    require_approvable(beats)
    moved = transition(experiment, Event.approve_board)
    return replace(moved, script=script_from_beats(beats), board_hash=board_hash)


def revise_board(experiment: Experiment, beats: Sequence[Beat]) -> Experiment:
    script = script_from_beats(beats)
    if experiment.status is Status.draft:
        return replace(experiment, script=script, board_hash=None)
    moved = transition(experiment, Event.revise_board)
    return replace(moved, script=script, board_hash=None)


def request_render(experiment: Experiment, renders_started_today: int, cap: int = 8) -> Experiment:
    if renders_started_today >= cap:
        raise RenderCapReached(f"daily render cap is {cap}")
    return transition(experiment, Event.start_render)


def mark_rendered(experiment: Experiment, file_path: str) -> Experiment:
    moved = transition(experiment, Event.render_ok)
    return replace(moved, file_path=file_path, render_error=None)


def mark_render_failed(experiment: Experiment, message: str) -> Experiment:
    moved = transition(experiment, Event.render_fail)
    return replace(moved, render_error=message, file_path=None)


def _tiktok_rewards(experiment: Experiment) -> bool:
    return (
        isinstance(experiment.money, PlatformPayout)
        and experiment.money.platform is Platform.tiktok
    )


def approve(experiment: Experiment, now: str) -> Experiment:
    if experiment.status is Status.approved:
        return experiment
    if _tiktok_rewards(experiment) and experiment.length_sec <= 60:
        raise IneligibleLength("TikTok Creator Rewards videos must be longer than 60 seconds")
    moved = transition(experiment, Event.approve)
    return replace(moved, approved_at=now)


def reject(experiment: Experiment) -> Experiment:
    if experiment.status is Status.rejected:
        return experiment
    return transition(experiment, Event.reject)


def mark_posted(experiment: Experiment) -> Experiment:
    return transition(experiment, Event.post)


def complete(experiment: Experiment) -> Experiment:
    return transition(experiment, Event.complete)


def style_key(style: Style) -> tuple[str, ...]:
    if isinstance(style, FacelessStyle):
        return ("faceless", style.look.value, style.voice_id, style.caption_style)
    return ("avatar", style.presenter_id, style.voice_id)

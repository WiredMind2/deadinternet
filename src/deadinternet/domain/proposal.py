from dataclasses import dataclass

from deadinternet.domain.experiment import (
    Affiliate,
    AvatarStyle,
    Beat,
    DomainError,
    Experiment,
    FacelessStyle,
    Look,
    Money,
    OwnOffer,
    Platform,
    PlatformPayout,
    Style,
    script_from_beats,
    style_key,
)


class ProposalRejected(DomainError):
    pass


@dataclass(frozen=True)
class FactorDiff:
    field: str
    parent_value: str
    next_value: str


@dataclass(frozen=True)
class DraftSpec:
    parent_ids: tuple[str, ...]
    factor_diffs: tuple[FactorDiff, ...]
    niche_id: str
    style: Style
    money: Money
    hook_id: str
    hypothesis: str
    script: str
    caption: str
    length_sec: int
    beats: tuple[Beat, ...] = ()


@dataclass(frozen=True)
class Catalog:
    niche_ids: frozenset[str]
    presenter_ids: frozenset[str]
    voice_ids: frozenset[str]
    offer_ids: frozenset[str]
    hook_ids: frozenset[str]
    parents: dict[str, Experiment]
    theme_ids: frozenset[str] = frozenset()


def _check_ids(draft: DraftSpec, catalog: Catalog) -> None:
    if draft.niche_id not in catalog.niche_ids:
        raise ProposalRejected(f"unknown niche {draft.niche_id}")
    if draft.hook_id not in catalog.hook_ids:
        raise ProposalRejected(f"unknown hook {draft.hook_id}")
    voice_id = draft.style.voice_id
    if voice_id not in catalog.voice_ids:
        raise ProposalRejected(f"unknown voice {voice_id}")
    if isinstance(draft.style, AvatarStyle) and draft.style.presenter_id not in catalog.presenter_ids:
        raise ProposalRejected(f"unknown presenter {draft.style.presenter_id}")
    if isinstance(draft.money, Affiliate) and draft.money.merchant not in catalog.offer_ids:
        raise ProposalRejected(f"unknown offer {draft.money.merchant}")
    if isinstance(draft.money, OwnOffer) and draft.money.offer_url not in catalog.offer_ids:
        raise ProposalRejected(f"unknown offer {draft.money.offer_url}")
    for parent_id in draft.parent_ids:
        if parent_id not in catalog.parents:
            raise ProposalRejected(f"unknown parent {parent_id}")


def _is_near_copy(draft: DraftSpec, parent: Experiment) -> bool:
    same_script = draft.script.strip() == parent.script.strip()
    return same_script and style_key(draft.style) == style_key(parent.style)


def parse_proposal(raw_drafts: list[dict], catalog: Catalog) -> list[DraftSpec]:
    parsed: list[DraftSpec] = []
    for raw in raw_drafts:
        beats = _beats_from(raw)
        draft = DraftSpec(
            parent_ids=tuple(raw.get("parent_ids", ())),
            factor_diffs=tuple(
                FactorDiff(**diff) for diff in raw.get("factor_diffs", ())
            ),
            niche_id=raw["niche_id"],
            style=_style_from(raw["style"]),
            money=_money_from(raw["money"]),
            hook_id=raw["hook_id"],
            hypothesis=raw["hypothesis"],
            script=script_from_beats(beats),
            caption=raw["caption"],
            length_sec=int(raw["length_sec"]),
            beats=beats,
        )
        _check_ids(draft, catalog)
        for parent_id in draft.parent_ids:
            if _is_near_copy(draft, catalog.parents[parent_id]):
                raise ProposalRejected("near-copy of an existing script and look")
        parsed.append(draft)
    return parsed


def _beats_from(raw: dict) -> tuple[Beat, ...]:
    raw_beats = raw.get("beats")
    if raw_beats:
        beats: list[Beat] = []
        for item in raw_beats:
            if "spoken" not in item:
                raise ProposalRejected("beat needs a spoken line")
            beats.append(
                Beat(
                    spoken=str(item["spoken"]),
                    on_screen=str(item.get("on_screen") or ""),
                    visual_note=str(item.get("visual_note") or ""),
                )
            )
        return tuple(beats)
    return (Beat(spoken=str(raw["script"]), on_screen="", visual_note=""),)


def _one_beat(spoken: str) -> tuple[Beat, ...]:
    return (Beat(spoken=spoken, on_screen="", visual_note=""),)


def _style_from(raw: dict) -> Style:
    if raw["kind"] == "faceless":
        return FacelessStyle(
            look=Look(raw["look"]),
            voice_id=raw["voice_id"],
            caption_style=raw["caption_style"],
        )
    if raw["kind"] == "avatar":
        return AvatarStyle(presenter_id=raw["presenter_id"], voice_id=raw["voice_id"])
    raise ProposalRejected(f"unknown style {raw['kind']}")


def _money_from(raw: dict) -> Money:
    if raw["kind"] == "affiliate":
        return Affiliate(tracking_code=raw["tracking_code"], merchant=raw["merchant"])
    if raw["kind"] == "platform_payout":
        return PlatformPayout(platform=Platform(raw["platform"]))
    if raw["kind"] == "own_offer":
        return OwnOffer(tracking_code=raw["tracking_code"], offer_url=raw["offer_url"])
    raise ProposalRejected(f"unknown money path {raw['kind']}")


def starter_grid(
    niche_ids: list[str],
    money: Money,
    hook_id: str,
    voice_id: str,
    presenter_id: str,
) -> list[DraftSpec]:
    drafts: list[DraftSpec] = []
    for niche_id in niche_ids:
        beats = _one_beat(f"Starter script for {niche_id}.")
        shared = dict(
            parent_ids=(),
            factor_diffs=(),
            niche_id=niche_id,
            money=money,
            hook_id=hook_id,
            hypothesis=f"Compare styles in {niche_id}",
            script=script_from_beats(beats),
            caption=f"Starter caption for {niche_id}.",
            length_sec=45,
            beats=beats,
        )
        drafts.append(
            DraftSpec(
                style=FacelessStyle(look=Look.stills, voice_id=voice_id, caption_style="bold"),
                **shared,
            )
        )
        drafts.append(
            DraftSpec(
                style=AvatarStyle(presenter_id=presenter_id, voice_id=voice_id),
                **shared,
            )
        )
    return drafts

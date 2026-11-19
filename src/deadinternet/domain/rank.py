from dataclasses import replace

from deadinternet.domain.experiment import (
    Affiliate,
    AvatarStyle,
    Beat,
    Experiment,
    FacelessStyle,
    Look,
    OwnOffer,
    Status,
    script_from_beats,
    style_key,
)
from deadinternet.domain.proposal import (
    Catalog,
    DraftSpec,
    FactorDiff,
    ProposalRejected,
    child_tracking_code,
    parse_proposal,
)


SAMPLE_FLOOR = 3


def cell_size(completed: list[Experiment], row: Experiment) -> int:
    key = (row.niche_id, style_key(row.style), _money_key(row))
    return sum(
        1
        for item in completed
        if item.status is Status.complete
        and (item.niche_id, style_key(item.style), _money_key(item)) == key
    )


def below_sample_floor(count: int, floor: int = SAMPLE_FLOOR) -> bool:
    return count < floor


def eligible_parents(rows: list[Experiment]) -> list[Experiment]:
    """Decision 4: a cell below the sample floor cannot name a cause, so a
    thin-cell row is never the parent. A row is eligible only when it is
    complete and its cell has reached the floor."""
    return [
        row
        for row in rows
        if row.status is Status.complete
        and not below_sample_floor(cell_size(rows, row))
    ]


def suggest(completed: list[Experiment], catalog: Catalog) -> list[DraftSpec]:
    eligible = eligible_parents(completed)
    if not eligible:
        return []
    parent = max(eligible, key=lambda row: (row.revenue_cents, row.clicks, row.id))
    next_style = _other_style(parent, catalog)
    diffs = (FactorDiff("style", style_key(parent.style)[0], style_key(next_style)[0]),)
    beats = (Beat(spoken=f"Follow-up script distinct from {parent.id}.", on_screen="", visual_note=""),)
    draft = DraftSpec(
        parent_ids=(parent.id,),
        factor_diffs=diffs,
        niche_id=parent.niche_id,
        style=next_style,
        money=_child_money(parent, completed),
        hook_id=parent.hook_id,
        hypothesis=f"Change style after {parent.id}",
        script=script_from_beats(beats),
        caption=parent.caption,
        length_sec=parent.length_sec,
        beats=beats,
    )
    return parse_proposal([_to_raw(draft)], catalog)


def _money_key(row: Experiment) -> str:
    return row.money.kind


def _child_money(parent: Experiment, rows: list[Experiment]):
    """One video, one code (US-024): a child derives `<parent>-c2` and never
    reuses the parent's exact code, so child clicks never credit the parent."""
    code = getattr(parent.money, "tracking_code", None)
    if not code:
        return parent.money
    taken = {
        row.money.tracking_code
        for row in rows
        if isinstance(row.money, (Affiliate, OwnOffer)) and row.money.tracking_code
    }
    return replace(parent.money, tracking_code=child_tracking_code(code, taken))


def _other_style(parent: Experiment, catalog: Catalog):
    if isinstance(parent.style, FacelessStyle):
        if not catalog.presenter_ids:
            raise ProposalRejected("catalog has no presenter to switch to")
        presenter_id = sorted(catalog.presenter_ids)[0]
        return AvatarStyle(presenter_id=presenter_id, voice_id=parent.style.voice_id)
    return FacelessStyle(look=Look.stills, voice_id=parent.style.voice_id, caption_style="bold")


def _to_raw(draft: DraftSpec) -> dict:
    style: dict
    if isinstance(draft.style, FacelessStyle):
        style = {
            "kind": "faceless",
            "look": draft.style.look.value,
            "voice_id": draft.style.voice_id,
            "caption_style": draft.style.caption_style,
        }
    else:
        style = {
            "kind": "avatar",
            "presenter_id": draft.style.presenter_id,
            "voice_id": draft.style.voice_id,
        }
    money = {"kind": draft.money.kind}
    if draft.money.kind == "affiliate":
        money.update(tracking_code=draft.money.tracking_code, merchant=draft.money.merchant)
    elif draft.money.kind == "own_offer":
        money.update(tracking_code=draft.money.tracking_code, offer_url=draft.money.offer_url)
    else:
        money.update(platform=draft.money.platform.value)
    return {
        "parent_ids": list(draft.parent_ids),
        "factor_diffs": [
            {"field": diff.field, "parent_value": diff.parent_value, "next_value": diff.next_value}
            for diff in draft.factor_diffs
        ],
        "niche_id": draft.niche_id,
        "style": style,
        "money": money,
        "hook_id": draft.hook_id,
        "hypothesis": draft.hypothesis,
        "script": draft.script,
        "caption": draft.caption,
        "length_sec": draft.length_sec,
        "beats": [
            {
                "spoken": beat.spoken,
                "on_screen": beat.on_screen,
                "visual_note": beat.visual_note,
            }
            for beat in draft.beats
        ],
    }


__all__ = [
    "ProposalRejected",
    "SAMPLE_FLOOR",
    "below_sample_floor",
    "cell_size",
    "eligible_parents",
    "suggest",
]

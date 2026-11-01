from deadinternet.domain.experiment import (
    AvatarStyle,
    Experiment,
    FacelessStyle,
    Look,
    Status,
    style_key,
)
from deadinternet.domain.proposal import Catalog, DraftSpec, FactorDiff, ProposalRejected, parse_proposal


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


def suggest(completed: list[Experiment], catalog: Catalog) -> list[DraftSpec]:
    finished = [row for row in completed if row.status is Status.complete]
    if not finished:
        return []
    parent = max(finished, key=lambda row: (row.revenue_cents, row.clicks, row.id))
    next_style = _other_style(parent, catalog)
    next_hook = _other_hook(parent.hook_id, catalog)
    diffs = (
        FactorDiff("style", style_key(parent.style)[0], style_key(next_style)[0]),
        FactorDiff("hook_id", parent.hook_id, next_hook),
    )
    draft = DraftSpec(
        parent_ids=(parent.id,),
        factor_diffs=diffs,
        niche_id=parent.niche_id,
        style=next_style,
        money=parent.money,
        hook_id=next_hook,
        hypothesis=f"Change style and hook after {parent.id}",
        script=f"Follow-up script distinct from {parent.id}.",
        caption=parent.caption,
        length_sec=parent.length_sec,
    )
    return parse_proposal([_to_raw(draft)], catalog)


def _money_key(row: Experiment) -> str:
    return row.money.kind


def _other_style(parent: Experiment, catalog: Catalog):
    if isinstance(parent.style, FacelessStyle):
        presenter_id = sorted(catalog.presenter_ids)[0]
        return AvatarStyle(presenter_id=presenter_id, voice_id=parent.style.voice_id)
    return FacelessStyle(look=Look.stills, voice_id=parent.style.voice_id, caption_style="bold")


def _other_hook(current: str, catalog: Catalog) -> str:
    for hook_id in sorted(catalog.hook_ids):
        if hook_id != current:
            return hook_id
    return current


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
    }


def assert_no_render_side_effect() -> None:
    """suggest() has no path to a renderer. This function exists so tests can import the boundary."""
    return None


__all__ = [
    "ProposalRejected",
    "below_sample_floor",
    "cell_size",
    "suggest",
]

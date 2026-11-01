"""Build real domain objects from fuzzed bytes. Harnesses share this module."""

from deadinternet.domain.experiment import (
    Affiliate,
    AvatarStyle,
    Experiment,
    FacelessStyle,
    IneligibleLength,
    InvalidTransition,
    Look,
    OwnOffer,
    Platform,
    PlatformPayout,
    RenderCapReached,
    Status,
)
from deadinternet.domain.proposal import Catalog, ProposalRejected
from deadinternet.publish.registry import PublishRefused

EXPECTED = (
    InvalidTransition,
    IneligibleLength,
    RenderCapReached,
    ProposalRejected,
    PublishRefused,
    KeyError,
    ValueError,
)


def text(fdp, limit: int = 24) -> str:
    raw = fdp.ConsumeUnicodeNoSurrogates(limit)
    return raw if raw else "x"


def pick(fdp, options):
    return options[fdp.ConsumeIntInRange(0, len(options) - 1)]


def money_from(fdp):
    kind = fdp.ConsumeIntInRange(0, 2)
    if kind == 0:
        return Affiliate(tracking_code=text(fdp, 12), merchant=text(fdp, 12))
    if kind == 1:
        return PlatformPayout(platform=pick(fdp, list(Platform)))
    return OwnOffer(tracking_code=text(fdp, 12), offer_url="https://example.test/" + text(fdp, 8))


def style_from(fdp):
    if fdp.ConsumeBool():
        return FacelessStyle(
            look=pick(fdp, list(Look)),
            voice_id=text(fdp, 8),
            caption_style="bold",
        )
    return AvatarStyle(presenter_id=text(fdp, 8), voice_id=text(fdp, 8))


def experiment_from(fdp, status: Status | None = None) -> Experiment:
    return Experiment(
        id=text(fdp, 12),
        niche_id=text(fdp, 12),
        hypothesis=text(fdp, 24),
        hook_id=text(fdp, 12),
        script=text(fdp, 48),
        caption=text(fdp, 24),
        style=style_from(fdp),
        money=money_from(fdp),
        status=status or pick(fdp, list(Status)),
        length_sec=fdp.ConsumeIntInRange(1, 180),
        clicks=fdp.ConsumeIntInRange(0, 1000),
        revenue_cents=fdp.ConsumeIntInRange(0, 100000),
    )


def catalog_for(row: Experiment) -> Catalog:
    voice_id = row.style.voice_id
    presenter_id = row.style.presenter_id if isinstance(row.style, AvatarStyle) else "presenter"
    offer_ids = set()
    if isinstance(row.money, Affiliate):
        offer_ids.add(row.money.merchant)
    if isinstance(row.money, OwnOffer):
        offer_ids.add(row.money.offer_url)
    return Catalog(
        niche_ids=frozenset({row.niche_id}),
        presenter_ids=frozenset({presenter_id}),
        voice_ids=frozenset({voice_id}),
        offer_ids=frozenset(offer_ids),
        hook_ids=frozenset({row.hook_id, "other-hook"}),
        parents={row.id: row},
    )


def proposal_raw(fdp, row: Experiment) -> dict:
    style = row.style
    if isinstance(style, FacelessStyle):
        style_raw = {
            "kind": "faceless",
            "look": style.look.value,
            "voice_id": style.voice_id,
            "caption_style": style.caption_style,
        }
    else:
        style_raw = {
            "kind": "avatar",
            "presenter_id": style.presenter_id,
            "voice_id": style.voice_id,
        }
    money = row.money
    if isinstance(money, Affiliate):
        money_raw = {"kind": "affiliate", "tracking_code": money.tracking_code, "merchant": money.merchant}
    elif isinstance(money, OwnOffer):
        money_raw = {"kind": "own_offer", "tracking_code": money.tracking_code, "offer_url": money.offer_url}
    else:
        money_raw = {"kind": "platform_payout", "platform": money.platform.value}
    if fdp.ConsumeBool():
        style_raw = {"kind": text(fdp, 8)}
    return {
        "parent_ids": [row.id] if fdp.ConsumeBool() else [],
        "factor_diffs": [],
        "niche_id": row.niche_id,
        "style": style_raw,
        "money": money_raw,
        "hook_id": row.hook_id,
        "hypothesis": text(fdp, 24),
        "script": text(fdp, 48),
        "caption": row.caption,
        "length_sec": fdp.ConsumeIntInRange(1, 180),
    }

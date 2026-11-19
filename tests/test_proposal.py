from dataclasses import replace

import pytest

from deadinternet.domain.experiment import (
    Affiliate,
    AvatarStyle,
    Experiment,
    FacelessStyle,
    Look,
    OwnOffer,
    Platform,
    PlatformPayout,
    Status,
)
from deadinternet.domain.proposal import (
    Catalog,
    ProposalRejected,
    changed_factors,
    parse_proposal,
    starter_grid,
)
from deadinternet.domain.rank import SAMPLE_FLOOR, below_sample_floor, cell_size, suggest


def _catalog(**overrides) -> Catalog:
    base = dict(
        niche_ids=frozenset({"niche-1"}),
        presenter_ids=frozenset({"presenter-1"}),
        voice_ids=frozenset({"voice-1"}),
        offer_ids=frozenset({"acme"}),
        hook_ids=frozenset({"question", "result"}),
        parents={},
    )
    base.update(overrides)
    return Catalog(**base)


def _parent() -> Experiment:
    return Experiment(
        id="exp-parent",
        niche_id="niche-1",
        hypothesis="Question hook",
        hook_id="question",
        script="Original spoken script.",
        caption="Caption",
        style=FacelessStyle(look=Look.stills, voice_id="voice-1", caption_style="bold"),
        money=Affiliate(tracking_code="abc", merchant="acme"),
        status=Status.complete,
        length_sec=50,
        revenue_cents=500,
    )


def _sibling(sid: str, revenue: int = 0) -> Experiment:
    """A finished row in the parent's cell: same niche, style, money kind."""
    return Experiment(
        id=sid,
        niche_id="niche-1",
        hypothesis="Question hook",
        hook_id="question",
        script=f"{sid} spoken script.",
        caption="Caption",
        style=FacelessStyle(look=Look.stills, voice_id="voice-1", caption_style="bold"),
        money=Affiliate(tracking_code=f"abc-{sid}", merchant="acme"),
        status=Status.complete,
        length_sec=50,
        revenue_cents=revenue,
    )


def _avatar_sibling(sid: str, revenue: int = 0) -> Experiment:
    return Experiment(
        id=sid,
        niche_id="niche-1",
        hypothesis="Avatar cut",
        hook_id="question",
        script=f"{sid} spoken script.",
        caption="Caption",
        style=AvatarStyle(presenter_id="presenter-1", voice_id="voice-1"),
        money=Affiliate(tracking_code=f"av-{sid}", merchant="acme"),
        status=Status.complete,
        length_sec=50,
        revenue_cents=revenue,
    )


def _raw_from_parent(script: str, style: dict, diffs: list | None = None) -> dict:
    return {
        "parent_ids": ["exp-parent"],
        "factor_diffs": diffs
        if diffs is not None
        else [
            {"field": "style", "parent_value": "faceless", "next_value": "avatar"},
            {"field": "hook_id", "parent_value": "question", "next_value": "result"},
        ],
        "niche_id": "niche-1",
        "style": style,
        "money": {"kind": "affiliate", "tracking_code": "abc", "merchant": "acme"},
        "hook_id": "result",
        "hypothesis": "Change two factors",
        "script": script,
        "caption": "Caption",
        "length_sec": 50,
    }


def test_unknown_presenter_rejects_the_whole_proposal():
    parent = _parent()
    catalog = _catalog(parents={parent.id: parent})
    raw = _raw_from_parent(
        "A different script.",
        {"kind": "avatar", "presenter_id": "missing", "voice_id": "voice-1"},
    )
    with pytest.raises(ProposalRejected):
        parse_proposal([raw], catalog)


def test_near_copy_is_refused():
    parent = _parent()
    catalog = _catalog(parents={parent.id: parent})
    raw = _raw_from_parent(
        parent.script,
        {
            "kind": "faceless",
            "look": "stills",
            "voice_id": "voice-1",
            "caption_style": "bold",
        },
    )
    with pytest.raises(ProposalRejected, match="near-copy"):
        parse_proposal([raw], catalog)


def test_suggest_changes_exactly_one_factor_and_derives_a_fresh_code():
    parent = _parent()
    rows = [parent, _sibling("sib-1", 100), _sibling("sib-2", 50)]
    catalog = _catalog(parents={row.id: row for row in rows})
    drafts = suggest(rows, catalog)
    assert len(drafts) == 1
    assert [diff.field for diff in drafts[0].factor_diffs] == ["style"]
    assert drafts[0].hook_id == parent.hook_id
    assert drafts[0].length_sec == parent.length_sec
    assert drafts[0].niche_id == parent.niche_id
    # One video, one code: the child derives `abc-c2`, never the parent's abc.
    assert drafts[0].money.tracking_code == "abc-c2"
    assert drafts[0].money.tracking_code != parent.money.tracking_code
    assert drafts[0].script != parent.script
    # The floor boundary is pinned, not just one side of it.
    assert below_sample_floor(SAMPLE_FLOOR - 1)
    assert not below_sample_floor(SAMPLE_FLOOR)


def test_suggest_returns_empty_when_a_two_row_cell_is_still_thin():
    parent = _parent()
    rows = [parent, _sibling("sib-1", 100)]
    assert suggest(rows, _catalog(parents={row.id: row for row in rows})) == []


def test_suggest_derives_the_next_child_code_when_c2_is_taken():
    parent = _parent()
    rows = [parent, _sibling("c2", 100), _sibling("sib-2", 50)]
    # The "c2" sibling already holds the code the first child would derive,
    # so the child code rolls forward instead of colliding.
    drafts = suggest(rows, _catalog(parents={row.id: row for row in rows}))
    assert drafts[0].money.tracking_code == "abc-c3"


def test_suggest_from_an_own_offer_parent_keeps_the_offer_and_mints_a_code():
    offer_url = "https://shop.example/offer"
    parent = replace(_parent(), money=OwnOffer(tracking_code="own-1", offer_url=offer_url))
    rows = [
        parent,
        replace(_sibling("sib-1", 100), money=OwnOffer(tracking_code="own-sib-1", offer_url=offer_url)),
        replace(_sibling("sib-2", 50), money=OwnOffer(tracking_code="own-sib-2", offer_url=offer_url)),
    ]
    catalog = _catalog(
        offer_ids=frozenset({"acme", offer_url}),
        parents={row.id: row for row in rows},
    )
    drafts = suggest(rows, catalog)
    assert isinstance(drafts[0].money, OwnOffer)
    assert drafts[0].money.offer_url == offer_url
    assert drafts[0].money.tracking_code == "own-1-c2"


def test_suggest_skips_a_thin_cell_parent_for_the_next_eligible_row():
    rich = _parent()  # top revenue, but its cell holds only itself
    supported = _avatar_sibling("exp-avatar-top", 100)
    rows = [rich, supported, _avatar_sibling("av-sib-1", 50), _avatar_sibling("av-sib-2", 10)]
    catalog = _catalog(parents={row.id: row for row in rows})
    drafts = suggest(rows, catalog)
    assert len(drafts) == 1
    assert drafts[0].parent_ids == (supported.id,)


def test_suggest_ranks_within_one_money_kind_not_across():
    """US-036 (decision 3): the parent pick ranks within the parent's money
    kind. The payout cell below out-earns the affiliate cell twenty to one,
    but the affiliate draft still names the affiliate cell's own winner, and
    the payout winner is proposed apart — never ranked against it."""
    affiliate_rows = [_parent(), _sibling("sib-1", 100), _sibling("sib-2", 50)]
    payout_top = replace(
        _parent(),
        id="exp-payout-top",
        money=PlatformPayout(platform=Platform.youtube),
        revenue_cents=9999,
        script="Payout script.",
    )
    payout_rows = [payout_top] + [
        replace(_sibling(f"pay-sib-{n}"), money=PlatformPayout(platform=Platform.youtube))
        for n in (1, 2)
    ]
    rows = affiliate_rows + payout_rows
    catalog = _catalog(parents={row.id: row for row in rows})
    drafts = suggest(rows, catalog)
    # One draft per money kind, in first-eligible-row order.
    assert [draft.money.kind for draft in drafts] == ["affiliate", "platform_payout"]
    assert drafts[0].parent_ids == ("exp-parent",)
    assert drafts[0].money.tracking_code == "abc-c2"
    assert drafts[1].parent_ids == ("exp-payout-top",)
    assert drafts[1].money == PlatformPayout(platform=Platform.youtube)


def test_suggest_returns_empty_when_every_finished_cell_is_thin():
    parent = _parent()
    assert suggest([parent], _catalog(parents={parent.id: parent})) == []


def test_a_draft_moving_two_factors_is_refused():
    parent = _parent()
    catalog = _catalog(parents={parent.id: parent})
    raw = _raw_from_parent(
        "A different script.",
        {"kind": "avatar", "presenter_id": "presenter-1", "voice_id": "voice-1"},
    )
    with pytest.raises(ProposalRejected, match="one deliberate factor"):
        parse_proposal([raw], catalog)


_OFFER_URL = "https://shop.example/offer"


def _raw_matching_parent(parent: Experiment, **overrides) -> dict:
    """A draft that copies the parent except where the test overrides it."""
    raw = {
        "parent_ids": ["exp-parent"],
        "factor_diffs": [],
        "niche_id": parent.niche_id,
        "style": {
            "kind": "faceless",
            "look": parent.style.look.value,
            "voice_id": parent.style.voice_id,
            "caption_style": parent.style.caption_style,
        },
        "money": {"kind": "affiliate", "tracking_code": "abc", "merchant": "acme"},
        "hook_id": parent.hook_id,
        "hypothesis": "One deliberate change.",
        "script": "A different script entirely.",
        "caption": "Caption",
        "length_sec": parent.length_sec,
    }
    raw.update(overrides)
    return raw


def _wide_catalog(parent: Experiment) -> Catalog:
    return _catalog(
        niche_ids=frozenset({"niche-1", "niche-2"}),
        offer_ids=frozenset({"acme", _OFFER_URL}),
        parents={parent.id: parent},
    )


@pytest.mark.parametrize(
    ("overrides", "changed"),
    [
        ({"niche_id": "niche-2"}, "niche"),
        ({"money": {"kind": "own_offer", "tracking_code": "abc", "offer_url": _OFFER_URL}}, "money"),
        ({"length_sec": 45}, "length"),
    ],
)
def test_each_factor_alone_is_a_deliberate_change(overrides, changed):
    """The one-factor rule accepts every factor on its own — niche, money
    path, and length were never exercised before this matrix."""
    parent = _parent()
    drafts = parse_proposal([_raw_matching_parent(parent, **overrides)], _wide_catalog(parent))
    assert changed_factors(drafts[0], parent) == [changed]


@pytest.mark.parametrize(
    "overrides",
    [
        # Niche plus style.
        {"niche_id": "niche-2", "style": {"kind": "avatar", "presenter_id": "presenter-1", "voice_id": "voice-1"}},
        # Money path plus hook.
        {
            "money": {"kind": "own_offer", "tracking_code": "abc", "offer_url": _OFFER_URL},
            "hook_id": "result",
        },
        # Length plus niche.
        {"length_sec": 45, "niche_id": "niche-2"},
    ],
)
def test_two_factors_from_the_wide_matrix_are_refused(overrides):
    parent = _parent()
    with pytest.raises(ProposalRejected, match="one deliberate factor"):
        parse_proposal([_raw_matching_parent(parent, **overrides)], _wide_catalog(parent))


def test_a_draft_moving_exactly_one_factor_parses():
    parent = _parent()
    catalog = _catalog(parents={parent.id: parent})
    raw = _raw_from_parent(
        "A different script.",
        {
            "kind": "faceless",
            "look": "stills",
            "voice_id": "voice-1",
            "caption_style": "bold",
        },
        # The draft moves exactly the hook; the declared list matches.
        diffs=[{"field": "hook_id", "parent_value": "question", "next_value": "result"}],
    )
    drafts = parse_proposal([raw], catalog)
    assert drafts[0].hook_id == "result"
    assert drafts[0].style == parent.style


def test_two_niches_score_as_different_cells():
    first = _parent()
    second = Experiment(
        id="exp-other",
        niche_id="niche-2",
        hypothesis=first.hypothesis,
        hook_id=first.hook_id,
        script=first.script,
        caption=first.caption,
        style=first.style,
        money=first.money,
        status=Status.complete,
        length_sec=first.length_sec,
    )
    rows = [first, second]
    assert cell_size(rows, first) == 1
    assert cell_size(rows, second) == 1


def test_suggest_without_a_presenter_is_a_clear_refusal():
    parent = _parent()
    rows = [parent, _sibling("sib-1"), _sibling("sib-2")]
    catalog = _catalog(presenter_ids=frozenset(), parents={row.id: row for row in rows})
    with pytest.raises(ProposalRejected, match="presenter"):
        suggest(rows, catalog)


def test_tiktok_starter_grid_is_longer_than_a_minute():
    from deadinternet.domain.experiment import Platform, PlatformPayout

    money = PlatformPayout(platform=Platform.tiktok)
    drafts = starter_grid(["niche-1"], money, "question", "voice-1", "presenter-1")
    assert drafts
    assert all(draft.length_sec > 60 for draft in drafts)


def test_starter_grid_creates_two_drafts_per_niche_without_rendering():
    money = Affiliate(tracking_code="abc", merchant="acme")
    drafts = starter_grid(["niche-1", "niche-2"], money, "question", "voice-1", "presenter-1")
    assert len(drafts) == 4
    kinds = [draft.style.kind for draft in drafts]
    assert kinds.count("faceless") == 2
    assert kinds.count("avatar") == 2
    assert all(draft.factor_diffs == () for draft in drafts)
    assert all(len(draft.beats) == 1 for draft in drafts)
    assert drafts[0].script == drafts[0].beats[0].spoken
    codes = {draft.money.tracking_code for draft in drafts}
    # The domain grid deliberately shares the base code across niches; the
    # API layer recodes every draft before insert (see
    # test_starter_gives_every_draft_a_distinct_code_across_niches).
    assert codes == {"abc", "abc-avatar"}

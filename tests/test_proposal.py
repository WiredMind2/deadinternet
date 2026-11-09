import pytest

from deadinternet.domain.experiment import (
    Affiliate,
    Experiment,
    FacelessStyle,
    Look,
    Status,
)
from deadinternet.domain.proposal import Catalog, ProposalRejected, parse_proposal, starter_grid
from deadinternet.domain.rank import below_sample_floor, cell_size, suggest


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


def _raw_from_parent(script: str, style: dict) -> dict:
    return {
        "parent_ids": ["exp-parent"],
        "factor_diffs": [
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


def test_suggest_changes_more_than_one_factor_and_does_not_render():
    parent = _parent()
    catalog = _catalog(parents={parent.id: parent})
    drafts = suggest([parent], catalog)
    assert len(drafts) == 1
    assert len(drafts[0].factor_diffs) >= 2
    assert drafts[0].script != parent.script
    assert below_sample_floor(1)


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
    catalog = _catalog(presenter_ids=frozenset(), parents={parent.id: parent})
    with pytest.raises(ProposalRejected, match="presenter"):
        suggest([parent], catalog)


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
    assert codes == {"abc", "abc-avatar"}

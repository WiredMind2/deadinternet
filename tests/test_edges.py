import sys

import pytest

from deadinternet.domain.experiment import (
    AvatarStyle,
    FacelessStyle,
    Look,
    Platform,
    PlatformPayout,
    Status,
    reject,
)
from deadinternet.domain.proposal import Catalog, ProposalRejected, parse_proposal
from deadinternet.domain.rank import assert_no_render_side_effect, suggest
from deadinternet.publish.registry import PublishRefused, publish
from deadinternet.render.faceless import default_runner, render_faceless
from deadinternet.render.registry import render
from deadinternet.runtime import LivePublisher, LiveRenderer
from tests.helpers import experiment


def _catalog(**overrides) -> Catalog:
    base = dict(
        niche_ids=frozenset({"niche-1"}),
        presenter_ids=frozenset({"presenter-1"}),
        voice_ids=frozenset({"voice-1"}),
        offer_ids=frozenset({"acme", "https://shop.example/offer"}),
        hook_ids=frozenset({"question", "result"}),
        parents={},
    )
    base.update(overrides)
    return Catalog(**base)


def _raw(**overrides) -> dict:
    body = {
        "parent_ids": [],
        "factor_diffs": [],
        "niche_id": "niche-1",
        "style": {
            "kind": "faceless",
            "look": "stills",
            "voice_id": "voice-1",
            "caption_style": "bold",
        },
        "money": {"kind": "affiliate", "tracking_code": "abc", "merchant": "acme"},
        "hook_id": "question",
        "hypothesis": "A new cut",
        "script": "A script that is not a copy.",
        "caption": "Watch this.",
        "length_sec": 75,
    }
    body.update(overrides)
    return body


def test_second_reject_is_a_noop():
    once = reject(experiment(status=Status.in_review))
    assert reject(once) == once


@pytest.mark.parametrize(
    "raw",
    [
        _raw(niche_id="missing"),
        _raw(hook_id="missing"),
        _raw(style={"kind": "faceless", "look": "stills", "voice_id": "missing", "caption_style": "bold"}),
        _raw(style={"kind": "avatar", "presenter_id": "missing", "voice_id": "voice-1"}),
        _raw(money={"kind": "affiliate", "tracking_code": "abc", "merchant": "missing"}),
        _raw(money={"kind": "own_offer", "tracking_code": "abc", "offer_url": "https://missing.example"}),
        _raw(parent_ids=["missing-parent"]),
        _raw(style={"kind": "puppet"}),
        _raw(money={"kind": "barter"}),
    ],
)
def test_unknown_catalog_values_reject_the_proposal(raw):
    with pytest.raises(ProposalRejected):
        parse_proposal([raw], _catalog())


def test_platform_payout_and_own_offer_drafts_parse():
    catalog = _catalog()
    drafts = parse_proposal(
        [
            _raw(money={"kind": "platform_payout", "platform": "youtube"}),
            _raw(
                money={
                    "kind": "own_offer",
                    "tracking_code": "own",
                    "offer_url": "https://shop.example/offer",
                }
            ),
        ],
        catalog,
    )
    assert [draft.money.kind for draft in drafts] == ["platform_payout", "own_offer"]


def test_suggest_ignores_rows_that_are_not_complete():
    assert suggest([experiment(status=Status.live)], _catalog()) == []


def test_suggest_from_an_avatar_parent_uses_faceless_stills():
    parent = experiment(
        status=Status.complete,
        style=AvatarStyle(presenter_id="presenter-1", voice_id="voice-1"),
        money=PlatformPayout(platform=Platform.youtube),
        revenue_cents=10,
    )
    drafts = suggest([parent], _catalog(parents={parent.id: parent}))
    assert isinstance(drafts[0].style, FacelessStyle)
    assert drafts[0].style.look is Look.stills
    assert drafts[0].money.platform is Platform.youtube


def test_suggest_keeps_the_only_catalog_hook():
    parent = experiment(status=Status.complete, revenue_cents=10)
    catalog = _catalog(
        hook_ids=frozenset({"question"}),
        parents={parent.id: parent},
    )
    drafts = suggest([parent], catalog)
    assert drafts[0].hook_id == "question"


def test_rank_boundary_does_not_render():
    assert assert_no_render_side_effect() is None


def test_default_runner_runs_a_successful_command():
    default_runner([sys.executable, "-c", "pass"])


def test_unknown_look_is_rejected(tmp_path):
    style = type("Style", (), {"kind": "faceless", "look": "mosaic"})()
    with pytest.raises(ValueError, match="unknown look"):
        render_faceless(experiment(status=Status.rendering, style=style), tmp_path)


def test_unknown_render_kind_is_rejected(tmp_path):
    style = type("Style", (), {"kind": "puppet"})()
    with pytest.raises(ValueError, match="unknown style kind"):
        render(experiment(style=style), tmp_path, runner=lambda cmd: None, avatar_client=None)


def test_token_without_a_client_is_refused():
    row = experiment(status=Status.approved, file_path="clip.mp4")
    with pytest.raises(PublishRefused, match="posting client"):
        publish(row, Platform.youtube, "acct-1", token="secret", client=None)


def test_live_avatar_render_fails_without_a_provider(tmp_path, monkeypatch):
    monkeypatch.delenv("AVATAR_API_KEY", raising=False)
    row = experiment(
        status=Status.rendering,
        style=AvatarStyle(presenter_id="presenter-1", voice_id="voice-1"),
    )
    rendered = LiveRenderer().render(row, tmp_path)
    assert rendered.status is Status.render_failed
    assert "AVATAR_API_KEY" in (rendered.render_error or "")


def test_live_publisher_without_a_token_packs_a_manual_post():
    row = experiment(status=Status.approved, file_path="clip.mp4")
    result = LivePublisher().publish(row, Platform.tiktok, "acct-1", token=None)
    assert result.manual_pack is not None
    assert result.publication.status.value == "manual_needed"


def test_main_starts_the_local_server(monkeypatch):
    seen = {}

    def fake_create_app(store, renderer, publisher, proposer):
        seen["store"] = store
        seen["renderer"] = renderer
        seen["publisher"] = publisher
        seen["proposer"] = proposer
        return "app"

    def fake_run(app, host, port):
        seen["app"] = app
        seen["host"] = host
        seen["port"] = port

    monkeypatch.setattr("deadinternet.__main__.create_app", fake_create_app)
    monkeypatch.setattr("deadinternet.__main__.uvicorn.run", fake_run)
    monkeypatch.setattr("deadinternet.__main__.Store", lambda path: path)

    from deadinternet.__main__ import main

    main()
    assert seen["app"] == "app"
    assert seen["host"] == "127.0.0.1"
    assert seen["port"] == 8000
    assert seen["store"] == "data/deadinternet.sqlite"
    assert type(seen["renderer"]).__name__ == "LiveRenderer"
    assert type(seen["publisher"]).__name__ == "LivePublisher"
    assert type(seen["proposer"]).__name__ == "RepairProposer"

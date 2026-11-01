import pytest

from deadinternet.domain.experiment import (
    Affiliate,
    AvatarStyle,
    Beat,
    Experiment,
    FacelessStyle,
    IneligibleLength,
    InvalidBoard,
    InvalidTransition,
    Look,
    Platform,
    PlatformPayout,
    RenderCapReached,
    Status,
    approve,
    approve_board,
    mark_posted,
    mark_rendered,
    request_render,
    revise_board,
    script_from_beats,
)


def _row(**overrides) -> Experiment:
    base = dict(
        id="exp-1",
        niche_id="niche-1",
        hypothesis="A question hook travels",
        hook_id="question",
        script="Here is the spoken script.",
        caption="Watch this.",
        style=FacelessStyle(look=Look.stills, voice_id="voice-1", caption_style="bold"),
        money=Affiliate(tracking_code="abc", merchant="acme"),
        status=Status.draft,
        length_sec=45,
    )
    base.update(overrides)
    return Experiment(**base)


def test_approve_on_draft_raises():
    with pytest.raises(InvalidTransition):
        approve(_row(), now="2026-10-31T12:00:00Z")


def test_request_render_on_in_review_raises():
    with pytest.raises(InvalidTransition):
        request_render(_row(status=Status.in_review), renders_started_today=0)


def test_mark_posted_on_in_review_raises():
    with pytest.raises(InvalidTransition):
        mark_posted(_row(status=Status.in_review))


def test_draft_cannot_render():
    with pytest.raises(InvalidTransition):
        request_render(_row(), renders_started_today=0)


def test_board_approval_requires_a_spoken_line_on_every_beat():
    with pytest.raises(InvalidBoard):
        approve_board(_row(), beats=(), board_hash="abc")
    with pytest.raises(InvalidBoard):
        approve_board(_row(), beats=(Beat(spoken="  "),), board_hash="abc")


def test_spoken_lines_join_in_order():
    beats = (
        Beat(spoken="Open on the result.", on_screen="Result", visual_note="finished dish"),
        Beat(spoken="Show the steps.", on_screen="", visual_note=""),
    )
    assert script_from_beats(beats) == "Open on the result.\nShow the steps."
    approved = approve_board(_row(), beats=beats, board_hash="hash-1")
    assert approved.status is Status.board_approved
    assert approved.script == "Open on the result.\nShow the steps."
    assert approved.board_hash == "hash-1"
    revised = revise_board(approved, beats[:1])
    assert revised.status is Status.draft
    assert revised.board_hash is None
    assert revised.script == "Open on the result."


def test_render_then_approve_then_post():
    approved_board = approve_board(
        _row(),
        beats=(Beat(spoken="Here is the spoken script."),),
        board_hash="hash-1",
    )
    rendering = request_render(approved_board, renders_started_today=0)
    assert rendering.status is Status.rendering
    ready = mark_rendered(rendering, file_path="data/videos/exp-1.mp4")
    assert ready.status is Status.in_review
    approved = approve(ready, now="2026-10-31T12:00:00Z")
    assert approved.status is Status.approved
    assert approved.approved_at == "2026-10-31T12:00:00Z"
    live = mark_posted(approved)
    assert live.status is Status.live


def test_second_approve_is_a_noop():
    ready = _row(status=Status.in_review, file_path="data/videos/exp-1.mp4")
    once = approve(ready, now="2026-10-31T12:00:00Z")
    twice = approve(once, now="2026-11-01T12:00:00Z")
    assert twice == once


def test_ninth_render_hits_the_cap():
    with pytest.raises(RenderCapReached):
        request_render(_row(), renders_started_today=8, cap=8)


def test_tiktok_rewards_shorter_than_a_minute_cannot_be_approved():
    ready = _row(
        status=Status.in_review,
        length_sec=45,
        money=PlatformPayout(platform=Platform.tiktok),
        file_path="data/videos/exp-1.mp4",
    )
    with pytest.raises(IneligibleLength):
        approve(ready, now="2026-10-31T12:00:00Z")


def test_tiktok_rewards_over_a_minute_can_be_approved():
    ready = _row(
        status=Status.in_review,
        length_sec=75,
        money=PlatformPayout(platform=Platform.tiktok),
        file_path="data/videos/exp-1.mp4",
    )
    approved = approve(ready, now="2026-10-31T12:00:00Z")
    assert approved.status is Status.approved


def test_avatar_style_is_not_faceless():
    row = _row(style=AvatarStyle(presenter_id="p1", voice_id="voice-1"))
    assert row.style.kind == "avatar"
    assert not hasattr(row.style, "look")

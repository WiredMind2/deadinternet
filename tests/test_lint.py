"""Direct checks on the vendored draft lints: hook floor, caption fold, stock phrases."""

from deadinternet.domain.experiment import Affiliate, AvatarStyle, Status
from deadinternet.domain.proposal import DraftSpec
from deadinternet.propose.lint import (
    caption_problems,
    check_frontload,
    check_specificity,
    draft_problems,
    score_hook,
    slop_hits,
)


def _draft(script="I lost $18,000 on one missing contract.", caption="That contract cost me $18,000."):
    return DraftSpec(
        parent_ids=("exp-parent",),
        factor_diffs=(),
        niche_id="niche-1",
        style=AvatarStyle(presenter_id="presenter-1", voice_id="voice-1"),
        money=Affiliate(tracking_code="abc", merchant="acme"),
        hook_id="result",
        hypothesis="A result hook beats the question hook.",
        script=script,
        caption=caption,
        length_sec=75,
    )


def test_a_strong_draft_has_no_problems():
    assert draft_problems(_draft()) == []


def test_a_weak_hook_names_the_score_and_the_fix():
    problems = draft_problems(_draft(script="Here is how the story goes."))
    assert problems
    assert "hook scores" in problems[0]
    assert "rewrite the first spoken beat" in problems[0]


def test_the_caption_fold_gate_names_the_fold():
    problems = caption_problems("Great tips ahead.")
    assert any("caption fold" in problem for problem in problems)


def test_stock_phrases_are_listed_for_replacement():
    hits = slop_hits("We need to delve into this game-changing deep dive.")
    assert hits
    problems = draft_problems(_draft(caption="Let's leverage this."))
    assert any("stock AI phrases" in problem for problem in problems)


def test_the_hook_score_separates_weak_from_strong():
    weak = score_hook("So today I wanted to show you something.")
    strong = score_hook("I lost $18,000 on one missing contract.")
    assert weak.verdict == "WEAK"
    assert strong.verdict == "STRONG"
    assert strong.overall > weak.overall


def test_a_hook_whose_only_payload_is_a_proper_noun_gets_credit():
    hook = "The Lyon rental market ate my budget."
    score = score_hook(hook)
    assert "payload at word 2" in score.checks["FRONTLOAD"][1]
    assert "no payload word anywhere" not in score.checks["FRONTLOAD"][1]
    assert draft_problems(_draft(script=hook)) == []


def test_a_capitalized_first_word_is_sentence_case_not_a_name():
    hook = "Everyone wants the cheap keyboard."
    assert "no payload word anywhere" in check_frontload(hook)[1]
    assert "no number, no name" in check_specificity(hook)[1]


def test_words_that_begin_like_a_weak_opener_are_not_penalized():
    hire = check_frontload("Hire the right coach before your first client.")[1]
    solar = check_frontload("Solar panels paid for themselves in two winters.")[1]
    assert "weak opener" not in hire
    assert "weak opener" not in solar


def test_genuine_weak_openers_are_still_penalized():
    so = check_frontload("So I tried the thing everyone warned me about.")[1]
    hey = check_frontload("Hey, that app owes me forty dollars.")[1]
    assert 'weak opener "so"' in so
    assert 'weak opener "hey"' in hey

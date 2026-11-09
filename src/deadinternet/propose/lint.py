"""Draft lints for the proposer, vendored from instagram-agent-skill (MIT).

Upstream: https://github.com/Jakeschincariol/instagram-agent-skill by Jake
Schincariol. Adapted here: the CLI and rendering are gone, and the three
checks worth gating on are kept as pure functions - hook scoring from
hookscore.py, the caption fold from caption.py, and stock-phrase detection
from detect.py against a verbatim slop.json.

Honest limits, from upstream's own measurement on 74 real hooks: the score
separates bad hooks from real ones well (AUC 0.83) and barely picks winners
(AUC 0.56). So these lints are floors. A draft is rejected only for clear
weakness - a WEAK hook, a dead caption fold, stock phrasing - never ranked.
"""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from deadinternet.domain.proposal import DraftSpec

SLOP_PATH = Path(__file__).with_name("slop.json")

HOOK_FLOOR = 50.0

WORD_RE = re.compile(r"[A-Za-z0-9$%'’-]+")
NUMBER_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?"                          # money, whole
    r"|\b\d[\d,]*(?:\.\d+)?\s?"                         # a figure, with or
    "(?:%|k\\b|x\\b|hrs?\\b|hours?\\b|mins?\\b|minutes?\\b"  # without a unit
    "|days?\\b|weeks?\\b|months?\\b|years?\\b)?",
    re.IGNORECASE)
PROPER_RE = re.compile(r"(?<!^)\b[A-Z][a-z]{2,}\b")
HASHTAG_RE = re.compile(r"(?:^|\s)(#[A-Za-z0-9_]+)")
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")

# Spoken hooks say their numbers out loud. "Zero dollars" and "twenty grand"
# are as concrete as "$0" and "$20,000". "one" and "first" are deliberately
# absent: they are filler far more often than they are a quantity.
SPOKEN_NUMBERS = {
    "zero", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "fifteen", "twenty", "thirty", "forty", "fifty",
    "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "million",
    "billion", "dozen", "half", "twice", "triple",
}
MONEY_WORDS = {
    "dollars", "dollar", "bucks", "grand", "percent", "cents",
    "millionaire", "billionaire", "revenue", "profit", "salary", "rent",
}

# Words that put something on the line. A hook with none of these is a
# statement; a hook with one is a reason to keep watching.
STAKES = {
    "stop", "never", "wrong", "mistake", "mistakes", "lost", "lose", "losing",
    "cost", "costs", "broke", "broken", "failed", "failure", "fail", "nobody",
    "no", "not", "don't", "dont", "doesn't", "didn't", "can't", "won't",
    "quit", "quitting", "fired", "deleted", "delete", "killed", "kills", "kill",
    "replaced", "replaces", "cut", "beat", "free", "paid", "charged", "hired",
    "saved", "first",
    "banned", "illegal", "worst", "hate", "hated", "wasted", "waste", "scam",
    "lie", "lied", "lying", "truth", "secret", "hidden", "stole", "stolen",
    "before", "until", "instead", "but", "except", "unless", "problem",
    "risk", "danger", "warning", "regret", "wish", "should", "shouldn't",
    "still", "already", "only", "without", "versus", "vs", "actually",
}

WEAK_OPENERS = [
    "so", "ok", "okay", "hey", "hi", "hello", "guys", "yo", "alright",
    "welcome", "today", "basically", "honestly", "look", "listen", "um",
    "just", "let", "lets", "let's", "i wanted", "i want", "one of",
    "have you", "did you", "do you", "are you", "in this", "in today",
    "the thing", "a lot", "there is", "there are", "this is", "it is",
    "as a", "when it", "if you've", "you know",
]

IMPERATIVES = {
    "stop", "steal", "copy", "delete", "try", "watch", "read", "save",
    "use", "build", "make", "write", "send", "take", "start", "quit",
    "never", "always", "don't", "dont", "do", "put", "run", "check",
}

DEALBREAKERS = [
    (re.compile(r"(?i)^\s*(?:stop scrolling|don'?t scroll)"),
     "opens with \"stop scrolling\", which asks for attention it has not earned"),
    (re.compile(r"(?i)\b(?:in (?:this|today'?s) (?:video|reel)|i'?m going to show you|i'?ll show you how)\b"),
     "video preamble in the hook; open on the payoff instead"),
    (re.compile(r"(?i)^\s*(?:hey |hi |what'?s up |welcome )"),
     "greeting in the hook; nobody came to the feed to be greeted"),
    (HASHTAG_RE,
     "hashtag in the hook; hashtags belong at the bottom of the caption"),
    (EMOJI_RE,
     "emoji in the hook; on-screen text at hook size has room for words or an emoji, not both"),
]

HOOK_CHECKS = ("LENGTH", "SPECIFICITY", "STAKES", "FRONTLOAD", "ADDRESS")

CAPTION_LIMIT = 2200
CAPTION_FOLD = 125
HASHTAG_LIMIT = 5
CONCRETE_RE = re.compile(r"\$\s?\d|\b\d[\d,.]*\b|(?<!^)\b[A-Z][a-z]{2,}\b", re.MULTILINE)


@dataclass(frozen=True)
class HookScore:
    checks: dict[str, tuple[float, str]]
    overall: float
    verdict: str
    flags: tuple[str, ...]
    weakest: str


def _clamp(n: float) -> float:
    return max(0.0, min(100.0, n))


def _words(text: str) -> list[str]:
    # "$18,000" is one word when it is spoken, so it is one word here too.
    return WORD_RE.findall(re.sub(r"(?<=\d),(?=\d)", "", text))


def check_length(text: str) -> tuple[float, str]:
    """A hook has to land before the thumb moves. Roughly two seconds."""
    w = _words(text)
    n = len(w)
    chars = len(text.strip())
    if 5 <= n <= 12:
        score = 100.0
    elif n < 5:
        score = _clamp(100 - (5 - n) * 20)
    else:
        score = _clamp(100 - (n - 12) * 11)
    if chars > 60:
        score -= 12
    return _clamp(score), f"{n} words, {chars} chars (want 5-12 words)"


def check_specificity(text: str) -> tuple[float, str]:
    """One concrete thing beats three abstract ones."""
    nums = [n.strip() for n in NUMBER_RE.findall(text) if n.strip()]
    propers = set(PROPER_RE.findall(text))
    low = [w.lower().strip("'’") for w in _words(text)]
    spoken = [w for w in low if w in SPOKEN_NUMBERS or w in MONEY_WORDS]
    hits = len(nums) + len(propers) + len(spoken)
    score = 15.0 if hits == 0 else _clamp(45 + hits * 30)
    found = ", ".join(nums[:2] + sorted(propers)[:2] + spoken[:2])
    detail = f"{hits} concrete marker(s)" + (f": {found}" if found else
                                              " - no number, no name, nothing checkable")
    return score, detail


def check_stakes(text: str) -> tuple[float, str]:
    """Tension, cost, negation. Something the viewer might lose."""
    w = [x.lower().strip("'’") for x in _words(text)]
    markers = sorted({x for x in w if x in STAKES})
    if re.search(r"\$\s?\d", text):
        markers.append("a price")
    n = len(markers)
    score = {0: 20.0, 1: 70.0}.get(n, 100.0)
    detail = f"{n} tension marker(s)" + (f": {', '.join(markers[:4])}" if markers else
                                         " - nothing is at stake in this line")
    return _clamp(score), detail


def check_frontload(text: str) -> tuple[float, str]:
    """The interesting word cannot be in position nine."""
    w = _words(text)
    if not w:
        return 0.0, "empty"
    low = [x.lower().strip("'’") for x in w]
    opener = " ".join(low[:2])
    penalty = 0
    hit_opener = None
    for weak in WEAK_OPENERS:
        if opener.startswith(weak) or low[0] == weak:
            penalty, hit_opener = 30, weak
            break
    payload = None
    for i, token in enumerate(low):
        if (token in STAKES or token in SPOKEN_NUMBERS or token in MONEY_WORDS
                or NUMBER_RE.match(w[i]) or (i and PROPER_RE.match(w[i]))):
            payload = i
            break
    if payload is None:
        base, where = 30.0, "no payload word anywhere in the line"
    elif payload <= 3:
        base, where = 100.0, f"payload at word {payload + 1}"
    elif payload <= 6:
        base, where = 70.0, f"payload at word {payload + 1}, could move forward"
    else:
        base, where = 40.0, f"payload at word {payload + 1}, too late"
    detail = where + (f"; weak opener \"{hit_opener}\"" if hit_opener else "")
    return _clamp(base - penalty), detail


def check_address(text: str) -> tuple[float, str]:
    """Aimed at one viewer, or floating in the air."""
    low = text.lower()
    w = [x.lower().strip("'’") for x in _words(text)]
    if re.search(r"\b(you|your|you're|youre|yourself)\b", low):
        return 100.0, "speaks to the viewer"
    if w and w[0] in IMPERATIVES:
        return 90.0, f"imperative opener (\"{w[0]}\")"
    if re.search(r"\b(i|my|me|we|our)\b", low):
        return 70.0, "first person, no viewer named"
    return 35.0, "third person, nobody in the room"


def score_hook(text: str) -> HookScore:
    """Score the first spoken line on the five things strong hooks share."""
    results = {
        "LENGTH": check_length(text),
        "SPECIFICITY": check_specificity(text),
        "STAKES": check_stakes(text),
        "FRONTLOAD": check_frontload(text),
        "ADDRESS": check_address(text),
    }
    flags = tuple(msg for pattern, msg in DEALBREAKERS if pattern.search(text))
    scores = [results[c][0] for c in HOOK_CHECKS]
    # The weakest property caps the hook: one bad property is enough for the
    # thumb to keep moving.
    overall = _clamp(statistics.mean(scores) * 0.6 + min(scores) * 0.4 - len(flags) * 15)
    verdict = "STRONG" if overall >= 70 and min(scores) >= 55 and not flags else (
        "OK" if overall >= 50 else "WEAK")
    weakest = min(HOOK_CHECKS, key=lambda c: results[c][0])
    return HookScore(checks=results, overall=overall, verdict=verdict,
                     flags=flags, weakest=weakest)


def visible_window(text: str, cut: int = CAPTION_FOLD) -> str:
    """What the feed shows before the "... more" tap. Cuts mid-word, as the feed does."""
    flat = text.strip()
    return flat if len(flat) <= cut else flat[:cut]


def caption_problems(caption: str) -> list[str]:
    """Gate the caption on the fold: the ~125 characters the feed shows."""
    text = caption.strip()
    if not text:
        return ["caption is empty"]
    problems = []
    if len(text) > CAPTION_LIMIT:
        problems.append(f"caption is {len(text)} characters, over the {CAPTION_LIMIT} limit")
    first_line = text.splitlines()[0].strip()
    if not first_line:
        problems.append("caption opens on a blank line")
    elif first_line.startswith(("#", "@")):
        problems.append("caption opens on a hashtag or mention; open on a sentence")
    tags = HASHTAG_RE.findall(text)
    if len(tags) > HASHTAG_LIMIT:
        problems.append(f"caption has {len(tags)} hashtags, over the cap of {HASHTAG_LIMIT}")
    window = visible_window(text)
    if not CONCRETE_RE.search(window):
        problems.append(
            f"caption fold has nothing concrete in the first {CAPTION_FOLD} characters; "
            "put a number or a name before the \"... more\" tap")
    return problems


@cache
def _lexicon() -> dict:
    with SLOP_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def slop_hits(text: str) -> list[str]:
    """Stock words and phrases from the vendored lexicon, in lexicon order."""
    found = []
    for entry in _lexicon()["words"] + _lexicon()["phrases"]:
        pattern = re.compile(r"\b" + re.escape(entry["find"]).replace(r"\ ", r"\s+") + r"\b",
                             re.IGNORECASE)
        if pattern.search(text):
            found.append(entry["find"])
    return found


def hook_problems(hook: str) -> list[str]:
    score = score_hook(hook)
    if not score.flags and score.overall >= HOOK_FLOOR:
        return []
    problems = [f"hook scores {score.overall:.0f}/100 ({score.verdict})"]
    problems.extend(score.flags)
    if not score.flags:
        detail = score.checks[score.weakest][1]
        problems.append(f"weakest check is {score.weakest}: {detail}")
    problems.append("rewrite the first spoken beat")
    return ["; ".join(problems)]


def draft_problems(draft: DraftSpec) -> list[str]:
    """Floor lints for one draft: hook strength, caption fold, stock phrasing."""
    problems = hook_problems(draft.beats[0].spoken if draft.beats else draft.script)
    problems.extend(caption_problems(draft.caption))
    hits = slop_hits(f"{draft.script}\n{draft.caption}")
    if hits:
        problems.append(
            "stock AI phrases: " + ", ".join(hits[:6])
            + (", ..." if len(hits) > 6 else "") + "; replace them with plain words")
    return problems

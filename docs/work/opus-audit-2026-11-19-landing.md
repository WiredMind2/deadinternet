# Closing audit of c6d7614

Seven of the ten claims hold in the code. Two are partial and one is not done: the factor-matrix test does not exist. I found two findings the landing dropped, several checked boxes the tests don't back, and two new bugs. I could not run pytest because the command needed approval, so "220 passing at 94.8%" is unconfirmed. Everything below comes from reading the code.

## Per-claim table

| # | Claim | Verdict | Evidence / gap |
|---|---|---|---|
| 1 | Sample floor on the real proposer path | **VERIFIED** (code), test gap | `propose/agent.py:184` `list_finished` uses `eligible_parents`. `agent.py:335-336` refuses parentless drafts. `agent.py:343-346` refuses non-eligible parents (this also closes G7). Gap: no test excludes a thin-cell row from `list_finished` (`tests/test_proposer.py:445-447` only checks the case where every row is eligible), and no test asserts the "below the sample floor" refusal. |
| 2 | `/suggest` 422 naming the floor | **VERIFIED** | `api/app.py:625-633`. Pinned by `tests/test_api.py:261` and `tests/test_flow.py:94-100`. |
| 3 | Complete buttons handle the 409 and offer the override | **VERIFIED**, one gap | Board: `App.jsx:689-702`, button at `:834`. Post: `App.jsx:1220-1233`, button at `:1429`. Both send `{force:true}`. Gap: the review asked for a confirmation before forcing. There is no `confirm()` anywhere in `App.jsx`. The button also appears on any 409, for example an `InvalidTransition` 409 (`app.py:271-273`) on a stale row. |
| 4 | Revenue in one transaction | **VERIFIED** (code), test missing | `store/db.py:844-872`: UPDATE and INSERT inside `with self._conn:`. The review asked for a test where the insert fails and the total doesn't move. None exists; `tests/test_store.py:167` only covers an unknown id. |
| 5 | `add_click` atomic, legacy backfill idempotent | **VERIFIED** (code), test missing | `db.py:788-811`; backfill at `db.py:313-337`, called at `:311`. Idempotency is pinned by `tests/test_store.py:535`. No test makes the log insert fail and checks the counter rolls back. |
| 6 | Snapshots ordered by `captured_at`, bad value refused | **PARTIAL** | `db.py:763` and `app.py:652`. The sort is a plain string sort, but the route accepts any `fromisoformat` value (offsets, space separator) without normalising it. See new bug 1. |
| 7 | Clash names the code; unsafe codes and non-http(s) URLs refused everywhere; blank `/starter` code refused | **PARTIAL** | `app.py:383-384`, `:390-395`, `:576-579`, `:602-606`, `:809-834`. The check strips the value but stores it unstripped. See new bug 2. The 409 "tracking code X is already used" path has no test; no test contains "already used". A clash is 422 from `_reject_known_tracking_code` but 409 from the index. |
| 8 | Crashing renderer lands in `render_failed` with the reason | **VERIFIED** | `app.py:461-466`; `tests/test_api.py:510`. The client still gets a bare 500, not the reason. |
| 9 | Approve refuses an unparseable `now`; window days `ge=1` | **VERIFIED** | `app.py:481-482` and `app.py:151`; tests at `tests/test_api.py:103` and `:1077`. |
| 10 | Test-suite hardening | **PARTIAL** | Done: the flow test is clock-independent (`tests/test_flow.py:53-61`), window boundaries are tested (`tests/test_api.py:649` and `:666`), own-offer paths are tested (`:358` and `:689`), the AST import checks exist (`tests/test_edges.py:145`, `tests/test_proposer.py:475`), the tautology is removed from `rank.py`, and the typo is gone. Not done or weak:<br>ΓÇó **Factor matrix: NOT DONE.** There is one two-factor test and one hook-only test (`tests/test_proposal.py:194` and `:205`). Niche, money path and length are never exercised, and there is no `parametrize` over the factors.<br>ΓÇó **Render-day race: moved, not fixed.** The day is now read before the render (`tests/test_api.py:1112-1114`). If midnight UTC falls between that read and the server's `_today()`, `renders_started_today(day) == 1` still fails.<br>ΓÇó **Store.close and conftest: partial.** Only `open_store()` registers stores (`tests/helpers.py:8-11`). About 16 direct `Store(...)` constructions in `tests/test_store.py` and `tests/test_edges.py` are never closed, including both stores in the backfill test.<br>ΓÇó **"Stale cap key":** no matching change in the diff, so it can't be verified. |

## Dropped findings (not fixed, not in US-031..US-040)

1. **A7, second half.** `/starter` still inserts row by row (`app.py:594-616`). A concurrent clash 409 leaves a half-inserted grid. The review asked to "insert the whole grid in one transaction or document the partial insert". Neither was done, and no backlog story mentions it.
2. **G3, second half.** `payout_cents` is still served on publications (`app.py:1072`). Nothing writes it, and it now duplicates the revenue ledger. It appears in no story.
3. **A8, story note (minor).** US-025 says the legacy clicks are "stamped at migration time". It does not tell the operator that `clicks_window` is wrong for those clicks: they fall outside a window that has already closed, and inside one that is still open, whenever they really happened.

Deferred correctly: A9 ΓåÆ US-035, A10 ΓåÆ US-039, blank snapshot fields ΓåÆ US-038, G1 and G2 ΓåÆ US-031 (G2 partly done now), G4 ΓåÆ US-036, G5 ΓåÆ US-037, G8 ΓåÆ US-040, G9 ΓåÆ US-032, G6 on hold. A5 was handled by relabelling: the field now reads "avg per view" (`App.jsx:1350`) and percent viewed is right on that basis. But `tests/test_snapshots_api.py:44` still uses total-style data (900 s with 25 views), so the meaning of `watch_time_seconds` is still not documented on the backend.

## Honest-box audit

The definition of done requires each box to be "checked against a real run or test". These boxes don't meet that:

- **US-024 c3:** the index-clash message "tracking code X is already used" has no test. The claim that unsafe codes are refused on both routes is false for leading or trailing whitespace (new bug 2).
- **US-025 c1 and c3:** "one transaction" is only established by reading the code; no failure-injection test.
- **US-026 c1:** "a partial failure can no longer desync them" has no test. The review explicitly asked for one.
- **US-026 c2:** the dashboard updating without a refresh names no test, and the box itself cites no run. Only the register's browser-run sentence covers it ("payout ledger").
- **US-027 c1:** "tests/test_proposer.py seeds the floor and asserts the filter" is overstated. The tests seed the floor so the happy path passes. Nothing asserts that a below-floor row is excluded or refused.
- **US-030 c1 and c3:** the five-field form and the percent-viewed column cite only `App.jsx`. They have no test, and the register's browser run doesn't list snapshots. These boxes are unverified.
- **Browser run:** the repo holds no log or screenshot, so I can't confirm it from here. Its listed steps don't include recording a snapshot.

US-027 c3 and c4 and US-026 c1, c3 and c4 are backed by real tests or a named run.

## New bugs introduced by the landing

1. **Snapshot order and "latest views" are a string sort.**
   - Where: `store/db.py:763` (`ORDER BY captured_at, id`), with `app.py:652` accepting any ISO form.
   - Failure: `2026-11-20T01:00:00+05:00` (20:00Z on the 19th) sorts after `2026-11-19T22:00:00Z`. `2026-11-19 23:00:00` sorts before `2026-11-19T01:00:00Z`. History then shows the wrong order, and `_views_for` (`app.py:762`) takes `snapshots[-1]` as the latest and reports the wrong view count.
   - Fix: normalise at the route before `record_snapshot`, e.g. `body.captured_at = _parse_iso(body.captured_at).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")`.
2. **The unsafe-code and URL checks validate a stripped value but store the raw one.**
   - Where: `app.py:829` and `app.py:814`.
   - Failure: `" abc"` passes and is stored with its leading space, so `/r/abc` never matches it. On `/starter`, `"abc "` passes and `starter_grid` derives `"abc -avatar"`, a code with an inner space that is never re-checked. `" https://x"` is stored and redirects with a leading space.
   - Fix: validate the raw value (`_SAFE_CODE_RE.fullmatch(money.tracking_code)`), or rebuild `money` with the stripped code and URL before validating and inserting. The same regex also accepts `.` and `..`, which can't work as an `/r/` path segment. Refuse codes made only of dots.
3. **Minor: Results shows the floor note on draft rows.**
   - Where: `App.jsx:1479` dropped the `status === "complete"` guard.
   - Failure: every draft, rendering or live row in a thin cell now shows "below the sample floor".
   - Fix: restore `row.status === "complete" &&`.
4. **Minor: the render crash path returns a bare 500.**
   - Where: `app.py:466` re-raises.
   - Failure: the dashboard shows a generic failure. The reason only appears after a reload. If the success-path `save_experiment` is what raised, a finished render is marked failed.
   - Fix: after saving `render_failed`, `raise HTTPException(500, detail=str(exc))`, and wrap only `renderer.render(...)` in the `except`.

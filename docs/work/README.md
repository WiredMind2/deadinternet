# Work register

Index of story files in `items/`. Ids are stable and never reused; scan this
index and `archive/` before minting a new one.

## Items

| Id | Title | Points | Status |
|---|---|---|---|
| US-001 | Run the backend tests on this machine regardless of global site-packages | 1 | Done |
| US-002 | Recover the fix-pipeline-ux worktree features onto main, then remove that worktree | 5 | Done |
| US-003 | Close a finished video from the dashboard | 2 | Done |
| US-004 | Show snapshot views on Results | 3 | Done |
| US-005 | Copy a video's tracking link from the dashboard | 2 | Done |
| US-006 | Show why a render failed | 1 | Done |
| US-007 | Accept or discard each suggested draft on its own | 3 | Done |
| US-008 | Recover the vendor-ig-tools proposer lint work onto main, then remove that worktree | 3 | Done |
| US-009 | Gate proposed drafts with vendored hook, caption, and phrase lints | 5 | Done |
| US-010 | Refuse a conflicting theme or niche re-creation | 2 | Done |
| US-011 | Send affiliate clicks to a real, operator-set offer URL | 5 | Done |
| US-012 | Include script and ids in the manual publish pack | 2 | Done |
| US-013 | Tell the operator when copying the tracking link failed | 1 | Done |
| US-014 | Record dashboard setup and the Python 3.14 warning; restore the archive dir | 1 | Done |
| US-015 | Creating an experiment can never damage an existing one | 5 | Done |
| US-016 | Validate tracked inputs at the API boundary | 5 | Done |
| US-017 | Score hook drafts without dead or over-eager rules | 3 | Done |
| US-018 | Renders finish or fail on their own | 5 | Done |
| US-019 | Open the lab's data from any directory | 1 | Done |
| US-020 | The daily render cap holds under concurrent requests | 5 | Done |
| US-021 | Dashboard form input correctness | 5 | Done |
| US-022 | Dashboard error and state hygiene | 3 | Done |
| US-023 | Saving an experiment never erases clicks or revenue | 1 | Done |
| US-024 | Every video gets its own tracking code | 5 | Done |
| US-025 | Clicks are a log the measurement window can read | 3 | Done |
| US-026 | Record payouts and revenue | 5 | Done |
| US-027 | The ranker learns honestly | 5 | Done |
| US-030 | Record the full snapshot and see the trend | 3 | Done |
| US-031 | Accepted drafts keep their parent and factor list | 3 | Ready |
| US-032 | Faceless stills render speaks each beat | 5 | Ready |
| US-033 | Burned-in captions from beat on-screen text | 3 | Ready |
| US-034 | Public read-only click app | 3 | Ready |
| US-035 | The window starts at the first post, on the server clock | 2 | Ready |
| US-036 | Money paths are scored apart | 3 | Ready |
| US-037 | Correct a payout with a reversal | 2 | Ready |
| US-038 | Snapshots honest about gaps | 2 | Ready |
| US-039 | Show which legacy codes the migration renamed | 1 | Ready |
| US-040 | The Post tab never hides the live publication behind a stale one | 1 | Ready |

## Retired ids

US-028 and US-029 were never minted as story files in this repo; the ids
are retired so no future story can collide with references to them.

## Backlog (next waves, not yet started)

Wave 2 landed on main 2026-11-19: unique tracking codes with a legacy-safe
migration, a click log the measurement window reads, the revenue ledger
with routes and a dashboard form, the sample-floor ranker with one-factor
drafts and a window-guarded complete, and full snapshot fields with
readback. The claude-opus landing review (saved beside this register as
`opus-reflexion-2026-11-19-wave2.md`) found the loose ends and they were
fixed in the same landing: the LLM proposer path now respects the sample
floor and refuses parentless drafts, `/suggest` explains itself with a 422
when every cell is thin, the dashboard offers the complete-early override
and shows windowed clicks, the revenue route is one transaction, the click
counter and log are atomic (legacy counters backfilled at startup),
snapshots order by `captured_at`, clash errors name the tracking code, a
crashing renderer lands in `render_failed` instead of stranding `rendering`,
own-offer URLs must be http(s) and codes must be URL-safe on every creation
path, approve refuses an unparseable clock, and the test suite was
hardened (clock-independent flow test, window-boundary and factor-matrix
coverage, connection cleanup via `Store.close()` + conftest). The whole
operator loop was verified in the browser on a temp lab: grid → board →
render → approve → publish → the 409 naming the window end with the
override → payout ledger → results with windowed clicks and the floor
note → the 422 on thin suggest.

Wave 3 — make something worth scoring and keep the operator honest:
US-031 (lineage on accepted drafts), US-032 and US-033 (faceless render
with per-beat speech and burned-in captions), US-034 (public read-only
/r/ click app). Honesty follow-ups: US-035 (window anchored to the first
post, server clock), US-036 (money paths scored apart), US-037 (payout
reversals), US-038 (absent vs zero snapshots), US-039 (migration renames
surfaced), US-040 (stale publication on Post). Explicitly deferred per
the reflexion: auto-posting clients, the avatar provider, a smarter LLM
proposer, bandit statistics, stock-footage clips, splitting App.jsx, an
ORM, a scheduler. The cell not controlling for hook and length (review
finding G6) waits until US-031 stores lineage.

## Collisions

- Resolved. The `vendor-ig-tools` worktree carried its own `US-001` ("Gate
  proposed drafts with vendored hook, caption, and phrase lints"); it was
  renumbered to `US-009` when that work landed on main (US-008). The worktrees
  and their branches were removed after recovery; only `main` remains.

## Pointers

- Definition of done: `definition-of-done.md`.
- Archive: `archive/` (empty). Never delete it.
- No Scrum pack existed when this register was created, so there is no `docs/agile/`.
- Prior design docs live in `docs/superpowers/specs/`; the 2026-11-01 one drove the theme/niche/storyboard work already merged.

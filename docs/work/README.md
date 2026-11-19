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
| US-031 | Accepted drafts keep their parent and factor list | 3 | Done |
| US-032 | Faceless stills render speaks each beat | 5 | Done |
| US-033 | Burned-in captions from beat on-screen text | 3 | Done |
| US-034 | Public read-only click app | 3 | Done |
| US-035 | The window starts at the first post, on the server clock | 2 | Done |
| US-036 | Money paths are scored apart | 3 | Done |
| US-037 | Correct a payout with a reversal | 2 | Done |
| US-038 | Snapshots honest about gaps | 2 | Done |
| US-039 | Show which legacy codes the migration renamed | 1 | Done |
| US-040 | The Post tab never hides the live publication behind a stale one | 1 | Done |

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
operator loop was verified in the browser on a temp lab on 2026-11-19:
grid → board → render → approve → publish with a pasted URL → the 409
naming the window end answered with the override button (409 then 200 in
the server log) → payout ledger and the refreshed revenue column →
results with windowed clicks and the floor note → the 422 on thin
suggest. The snapshot recording form itself was not exercised in that
run; the history readback was (two GETs in the server log).

A closing opus audit (saved beside this register as
`opus-audit-2026-11-19-landing.md`) confirmed seven of ten landing claims,
found two real bugs the landing introduced (snapshots sorted as raw
strings, so mixed offsets order wrongly; codes validated stripped but
stored raw, so padded codes pass), and flagged four coverage debts (the
factor matrix, the thin-row exclusion from `list_finished`, failure
injection for the revenue/click transactions, the un-registered direct
`Store()` constructions). All of them were fixed in the next landing:
`captured_at` is normalised to UTC at the route, codes and offer URLs are
judged on their raw values (dot-only codes refused), the floor note shows
only on complete rows, a render crash answers with a 500 carrying the
reason, the override button appears only for the measurement-window 409,
the factor matrix, thin-row exclusion, and trigger-based failure
injection tests exist, and every test store is registered for conftest
cleanup. Deliberately accepted: the starter grid can abort half-built on
a mid-loop IO failure (no reachable input triggers it — codes are minted,
ids are UUIDs; a code comment documents it), and the override button
skips a confirm dialog (its label names the action).

Wave 3 opened on main 2026-11-19: US-031 (lineage on accepted drafts —
parents and server-derived factor lists stored and shown on Results),
US-032 and US-033 (the faceless render speaks each beat and burns in
`on_screen` captions, per-beat timing from the audio, env-gated TTS
mirroring the avatar stub, verified against real ffmpeg on this
machine). Caveat: no TTS provider is wired, so a live faceless render
lands `render_failed` naming `DEADINTERNET_TTS_API_KEY` until an
operator supplies a real speaker; the pipeline itself is verified with a
synthetic one. US-037 (payout reversals: a linked ledger row with a
required note, one transaction, the total never below zero, double
reversal refused, an inline Reverse affordance in the dashboard) and
US-034 (the public read-only click app: `python -m deadinternet
--public [port]` serves only `GET /r/{code}` on its own process against
the same lab database, with every admin route 404 and no store detail
leaking; the admin app keeps its /r route for local dev) also landed the
same day. The remaining backlog closed on main 2026-11-19: US-040 (the
Post tab picks the newest publication per platform, so a stale
manual_needed row can no longer hide the posted one's snapshot form and
history), US-035 (the measurement window anchors at the first posted
publication on the server clock — `first_posted_at`, legacy-safe column;
the guard and `_clicks_window` share one anchor, the later of the first
post and approval, so an experiment never posted falls back to the
approval stamp; Board and Post show the window end before the 409), US-036
(decision 3 enforced: suggest picks one parent per money kind and never
ranks kinds against each other, Results totals revenue per path and marks
platform_payout rows as settling after the window, and the dead
`payout_cents` copy is gone from the served payloads), US-038 (blank
snapshot counts are stored absent — nullable columns with a legacy
rebuild — and SnapshotHistory and percent viewed read "—" for them, while
recorded zeros keep their meaning), and US-039 (the duplicate-code
upgrade records every rename under the `tracking_code_renames` settings
key, a dismissable dashboard banner names the affected experiments, and
the Copy link button always reads the served current code). The whole
operator loop for these five was re-verified in the browser on a temp
lab, including the stale-publication pick, the window-end display on
Board and Post, the "—" snapshot cells beside legacy measured zeros, the
per-path revenue totals, the settles-after-the-window marks on Results
and Proposals, and the rename banner's dismiss-and-return lifecycle. The
four ResourceWarnings the landing noted (test_store tests constructing
Store directly) were closed in the same session — every test store now
registers with the conftest cleanup, verified with warnings-as-errors.
Explicitly deferred per the reflexion: auto-posting clients, the avatar
provider, a smarter LLM proposer, bandit statistics, stock-footage
clips, splitting App.jsx, an ORM, a scheduler. The cell not controlling
for hook and length (review finding G6) can now be revisited on the
stored lineage.

The local backlog is closed as of 2026-11-19: every story in this index
is Done, the suite stands at 288 passing with 95.5% coverage, and the
build is green. What remains needs the operator, not more local code: a
real TTS speaker behind `DEADINTERNET_TTS_API_KEY` (the render pipeline
is verified with a synthetic one and fails loudly without it), an avatar
provider behind `AVATAR_API_KEY` (same env-gated pattern), and platform
credentials before any auto-posting client — all deliberately deferred
in the backlog above.

## Collisions

- Resolved. The `vendor-ig-tools` worktree carried its own `US-001` ("Gate
  proposed drafts with vendored hook, caption, and phrase lints"); it was
  renumbered to `US-009` when that work landed on main (US-008). The worktrees
  and their branches were removed after recovery; only `main` remains.

## Pointers

- Definition of done: `definition-of-done.md`.
- Archive: `archive/` (empty). Never delete it.
- Landing reviews: `opus-reflexion-2026-11-19-wave2.md` (before the landing),
  `opus-audit-2026-11-19-landing.md` (closing audit of c6d7614).
- No Scrum pack existed when this register was created, so there is no `docs/agile/`.
- Prior design docs live in `docs/superpowers/specs/`; the 2026-11-01 one drove the theme/niche/storyboard work already merged.

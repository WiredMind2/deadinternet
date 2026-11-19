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

## Backlog (next waves, not yet started)

Wave 2 — make the score exist and be honest (from the claude-opus reflexion of
2026-11-19, pending story files): every video gets its own tracking code
(unique index + suggest mints a child code); a click log with timestamps so
Results can honor the measurement window; payout/revenue entry (route +
ledger + dashboard form); honest ranker (sample floor respected by suggest,
one factor change per draft, no closing before the window ends).

Wave 3 — make something worth scoring: faceless render with per-beat speech
and burned-in captions; a public read-only /r/ click app separate from the
admin API. Explicitly deferred per the reflexion: auto-posting clients, the
avatar provider, a smarter LLM proposer, bandit statistics, stock-footage
clips, splitting App.jsx, an ORM, a scheduler.

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

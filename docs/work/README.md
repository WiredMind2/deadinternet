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

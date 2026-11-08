# Work register

Index of story files in `items/`. Ids are stable and never reused; scan this
index and `archive/` before minting a new one.

## Items

| Id | Title | Points | Status |
|---|---|---|---|
| US-001 | Run the backend tests on this machine regardless of global site-packages | 1 | Done |
| US-002 | Recover the fix-pipeline-ux worktree features onto main, then remove that worktree | 5 | Ready |
| US-003 | Close a finished video from the dashboard | 2 | Done |
| US-004 | Show snapshot views on Results | 3 | Done |
| US-005 | Copy a video's tracking link from the dashboard | 2 | Done |
| US-006 | Show why a render failed | 1 | Done |
| US-007 | Accept or discard each suggested draft on its own | 3 | Done |
| US-008 | Recover the vendor-ig-tools proposer lint work onto main, then remove that worktree | 3 | Ready |

## Collisions

- `US-001` also exists, with a different wording, as an uncommitted file in the
  `.worktrees/vendor-ig-tools` checkout (`docs/work/items/US-001.md`, "Gate
  proposed drafts with vendored hook, caption, and phrase lints"). That
  register was never merged. When US-008 lands, renumber that story there
  before merging so only one US-001 remains in this index.

## Pointers

- Definition of done: `definition-of-done.md`.
- Archive: `archive/` (empty). Never delete it.
- No Scrum pack existed when this register was created, so there is no `docs/agile/`.
- Prior design docs live in `docs/superpowers/specs/`; the 2026-11-01 one drove the theme/niche/storyboard work already merged.

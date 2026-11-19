I reviewed the Wave 2 diff and the rest of the app. **Wave 2 should not be marked Done yet.** The real app never uses the new sample-floor ranker, and three other bugs should be fixed before commit.

I read every file I cite below. I did not run the test suite. I tried to run a legacy-migration check script, but running it needed approval and I didn't get it, so the migration findings come from reading the code.

## A. Bugs in the uncommitted diff

**A1. The sample floor and the "tell the operator" rule never run in the real app (bug, blocks US-027)**
- `src/deadinternet/__main__.py:26` always passes `proposer=RepairProposer.from_env()`.
- So `src/deadinternet/api/app.py:581-584` only calls `rank.suggest` when `proposer is None`, which only happens in tests:
  ```python
  if proposer is None:
      drafts = suggest(experiments, catalog)
  else:
      drafts = proposer.propose(experiments, catalog)
  ```
- `propose/agent.py:183` lists every completed row with no floor check: `rows = [row for row in run.experiments if row.status is Status.complete]`. `_evaluate` (`agent.py:331-339`) doesn't check the floor either. The LLM can still pick a parent from a thin cell. US-027 criterion 1 is only met by the test path.
- **Fix:**
  - Add `eligible_parents(rows)` to `domain/rank.py` and use it in `suggest`.
  - In `suggest_next`, before either path runs, raise `ProposalRejected` if no row is eligible. It already maps to a 422 (`app.py:275-277`). The message should say something like "no finished cell has 3 completed videos; too thin to name a cause".
  - Filter `list_finished` to eligible rows.
  - In `_evaluate`, refuse a parent that isn't eligible.

**A2. `POST /suggest` returning `[]` is a gap and should block Done for US-027**
- When `/suggest` returns `[]`, the dashboard shows `"No drafts yet. Suggest to ask for one."` (`web/src/App.jsx:1504`). That is the same text it shows before any request, so the operator can't tell why nothing came back. Decision 4 says the operator must be told the cell is too thin.
- The A1 fix covers this, because `Proposals.suggest` already sends errors to `<Banner>` (`App.jsx:1464-1465`).
- `tests/test_flow.py`, which asserts `thin.json() == []`, would need to expect a 422 instead.

**A3. The dashboard can't use the close-early override (gap, blocks US-027 criterion 3)**
- Both Close buttons post with no body: `App.jsx:675` and `App.jsx:1187` both send `api(\`/experiments/${...}/complete\`, { method: "POST" })`.
- Inside the window, the operator gets `send {"force": true} to override` (`app.py:804`) and has no way to do that from the dashboard. Criterion 3 says "the operator stays in control".
- **Fix:** on a 409, show the window end from the error and a "Close early" button that asks for confirmation and sends `body: JSON.stringify({ force: true })`.

**A4. The revenue total and the ledger are two separate commits (bug, US-026)**
- `app.py:604-610` calls `store.add_revenue(...)` and then `store.add_revenue_entry(...)`. Each goes through `_write`, which commits on its own (`db.py:873-876`), and each takes the store lock separately.
- If the second write fails, `revenue_cents` goes up with no ledger row.
- **Fix:** one store method, for example `record_revenue(experiment_id, amount, note, created_at)`, that does the UPDATE and the INSERT inside `with self._conn:`. Add a test where the insert fails and the total doesn't move.

**A5. The "percent viewed" formula ignores views (bug, US-030 criterion 3)**
- `App.jsx` `percentViewed` computes `Math.round((watched / length) * 100)`.
- The new test data in `tests/test_snapshots_api.py` has `views: 25` and `watch_time_seconds: 900`. With a 45 s video that shows 2000%. The field holds total watch time.
- **Fix:** compute `watched / (views * length)` and pass `row.views`, or rename the field to average watch time. Either way, label the unit on the Record snapshot form.

**A6. A half-typed payout can be recorded on the wrong video (risk, US-026)**
- `RevenuePanel` keeps `amount` and `note` in state, and only the ledger reloads on `[experiment.id]`.
- If the operator types 500, selects another row and clicks Record payout, the payout goes to the newly selected row.
- **Fix:** add `key={selected.id}` where `<RevenuePanel experiment={selected} ΓÇª/>` is rendered in `Board`.

**A7. A tracking-code clash gets the wrong error message (risk, US-024)**
- `app.py:376-383` checks the code, then inserts, as two separately locked calls. Two simultaneous creates with the same code both pass the check.
- The unique index then refuses the second one, but the handler reports `detail=f"experiment {experiment.id} already exists"` (ids are UUIDs, so this is clearly wrong).
- `/starter` (`app.py:563-570`) has the same pattern. It mints the code and inserts in separate steps, and a 409 there leaves the grid half-inserted.
- **Fix:** if the error text contains `experiments_tracking_code`, return 409 "tracking code X is already used". For `/starter`, insert the whole grid in one transaction or document the partial insert.

**A8. The click counter and the click log can drift (risk, US-025 criterion 3)**
- `db.py:753-777` runs the UPDATE and then the click-log INSERT with nothing to roll back if the INSERT fails. The increment stays in an open transaction, and the next `_write` commits it.
- **Fix:** wrap the body in `with self._conn:`.
- Also, clicks recorded before Wave 2 have no log rows. For those experiments the counter is higher than the log and `clicks_window` is too low. Criterion 3 can only hold for clicks recorded from now on, so the story file should say that.

**A9. The window clock is set by the browser and starts at approval, not posting (risk, US-025 and US-027)**
- `approved_at` comes from the browser: `App.jsx:839` sends `body: JSON.stringify({ now: new Date().toISOString() })`, and `ApproveIn.now: str` (`app.py:169-170`) doesn't validate it.
- If the value can't be parsed, `_reject_before_window_end` returns early (`app.py:795-797`) so closing is never blocked, and `_clicks_window` returns 0.
- Posting is manual and can happen days after approval, so the 7-day window can be mostly gone before the video is up.
- **Fix:** stamp the time on the server and anchor the window to the first posted publication. This is US-035 below.

**A10. The migration renames legacy codes without telling the operator (risk, US-024 criterion 4)**
- `db.py:349-394` keeps the oldest row's code and renames later duplicates with `-2`/`-3`. No row is deleted and the index is created afterwards, so it meets criterion 4.
- But a link to `/r/abc` that is already published for the later video now credits the oldest row for good, and nothing says so. Criterion 4 allowed legacy rows to keep their codes.
- **Fix:** log each rename (or write it to a settings key) and show it once in the dashboard. Whether to keep the renames at all is a product decision for the PM.

**A11. Smaller issues (nit)**
- Snapshot history sorts by insert order, not by `captured_at`. `db.py:730` has `ORDER BY id` and `app.py:624` uses `reversed(...)`. A backdated `captured_at` sent through the API lands in the wrong place, and `_views_for` uses `snapshots[-1]` as "latest" for the same reason. **Fix:** `ORDER BY captured_at, id`.
- Blank snapshot fields are stored as 0 (`App.jsx`, `if (!value) { counts[field] = 0; ...}`). "Not entered" looks like "measured zero", and percent viewed shows 0%.
- `measurement_window_days` has no lower bound (`app.py:143`, `int = 7`). A negative value closes the window right away. **Fix:** `Field(default=7, ge=1)`.
- A starter grid with an empty tracking code produces `-avatar`, then `-avatar-2`, through `_with_tracking_suffix` (`proposal.py:194-200`). **Fix:** refuse a blank code for affiliate or own-offer money on `/starter`.
- Test name typo: `test_a_parentless_draft_colliding_with_a_known_code_is_recded` (`tests/test_proposer.py`).
- The register jumps from US-027 to US-030. US-028 and US-029 appear nowhere in the repo. The PM should record that they are skipped, or mint them, so the ids stay stable.

## B. Gaps across the app

- **G1. The factor list is lost when a draft is accepted (decision 4, "Keep the factor list on the proposal").**
  - `draftPayload` (`App.jsx:207-221`) sends no `parent_ids` or `factor_diffs`, and `ExperimentIn` (`app.py:130-143`) has no fields for them.
  - So no stored experiment records what changed, and Results can never say which factor moved.
  - Separately, the `factor_diffs` the LLM declares are never checked against `changed_factors`. The list on the draft can be wrong.
- **G2. A draft with no parent skips the one-factor rule and the near-copy check.** Both only loop over `draft.parent_ids` (`proposal.py:135-145`), and the LLM can submit `parent_ids=[]`. **Fix:** require a parent when submitting through `_evaluate`.
- **G3. The API serves fields the dashboard never shows.**
  - `clicks_window` (US-025) is not read anywhere in `App.jsx`; Results shows only `clicks` at `App.jsx:1435-1436`.
  - `payout_cents` is served on publications (`app.py:995`) and nothing writes it. It now duplicates the revenue ledger, so either drop it or derive it from the ledger.
- **G4. Money paths are compared against each other.**
  - Decision 3 says to score the three money paths apart, but the parent is chosen across all of them (`rank.py:49`, `max(eligible, key=lambda row: (row.revenue_cents, row.clicks, row.id))`). The Results total (`App.jsx:1413-1416`) also adds them together.
  - Platform payouts settle a month later, so a 7-day comparison is unfair to them.
- **G5. A recorded payout can't be corrected.** `RevenueIn.amount_cents: int = Field(ge=1)` makes a typo permanent. Add a reversal entry with a required note.
- **G6. The cell doesn't control for hook or length.** `cell_size` groups by `(niche, style, money.kind)` (`rank.py:29`), but hook, length and merchant are now factors. "3 in the cell" doesn't hold the hook constant.
- **G7. The LLM can pick any experiment as parent.** `catalog.parents` includes every experiment in any status (`db.py:848`), including drafts.
- **G8. The Post tab can show a stale publication.** It keeps the first publication per platform (`App.jsx:1024`, `publication: next[platform].publication || publication`). If an old manual-needed row comes before the posted one, the snapshot form and history stay hidden.
- **G9. The faceless renderer outputs a silent black screen.** `render/faceless.py:47-65` uses `color=c=blackΓÇª` with no audio and no captions. Nothing worth scoring gets produced yet, which is why Wave 3 starts there.

## C. Checked and clean

- Window boundaries: `start <= moment <= end` with `end = approved_at + window_days` correctly leaves out a day-8 click. Timestamps ending in `Z`, `+00:00` or no zone all parse through `_parse_iso`.
- Snapshot history comes back newest-first for snapshots recorded in order, and an unknown publication returns 404.
- The one-factor rule uses the money path (merchant or offer URL), not the tracking code, so the minted child codes don't count as a factor change. The default `suggest` now changes only style.
- Every tracking-code path was covered:
  - `POST /experiments` refuses a clash.
  - `/starter` recodes.
  - `rank.suggest` derives `-cN` codes from every stored code.
  - The proposer recodes after its checks.
  - `save_experiment` is an UPDATE (`db.py:554-598`), so the unique index can't delete another row the way INSERT OR REPLACE would.
- The migration keeps every row and creates the index only after renaming. `mint_tracking_code` checks the full set of existing codes, so a rename can't collide with an existing `abc-2`.
- Closing with no body works, and closing an experiment that was never approved is still allowed.
- The `G??` strings in the diff are a display artifact. The file contains `ΓÇª` (`App.jsx:630`, `956`).

## D. What to change before commit

Fold A1ΓÇôA6 into the Wave 2 stories: A1ΓÇôA3 into US-027, A4 and A6 into US-026, A5 into US-030. Add the A7 and A8 one-line fixes to US-024 and US-025. Optionally show `clicks_window` on Results (G3) as part of US-025 criterion 2. Then rerun pytest and the web build.

## E. Next wave (suggested ids from US-031, pending the US-028/029 decision)

| # | Id | Title | Pts | Acceptance criteria |
|---|---|---|---|---|
| 1 | US-031 | Accepted drafts keep their parent and factor list | 3 | `parent_ids` and `factor_diffs` are stored when a draft is accepted; the stored diffs come from `changed_factors`, not from the model; a draft with no parent is refused in `_evaluate`; Results shows "changed: style" (G1, G2) |
| 2 | US-032 | Faceless stills render speaks each beat | 5 | Each beat's `spoken` text becomes its own audio segment; the video length is the sum of the segments; the TikTok length rule still applies; a failure becomes `render_failed` with a reason (G9) |
| 3 | US-033 | Burned-in captions from beat on-screen text | 3 | `on_screen` text is burned into each beat's time span using `caption_style`; an empty `on_screen` means no caption; captions stay a factor, not a default (synthesis, "Burned-in captions") |
| 4 | US-034 | Public read-only click app | 3 | A separate app serves only `/r/{code}`; admin routes return 404 there; it uses the same store and logs clicks the same way; it runs as its own process |
| 5 | US-035 | The window starts at the first post, on the server clock | 2 | `approved_at` is stamped by the server; the window starts at the first posted publication; Board and Post show the window end; an unparseable time is refused (A9) |
| 6 | US-036 | Money paths are scored apart | 3 | The ranker and Results compare within one money type; revenue totals are shown per money path; platform-payout rows are marked "settles later" (G4) |
| 7 | US-037 | Correct a payout with a reversal | 2 | A reversal entry with a required note, linked to the original entry; the total can't go below 0; the ledger shows both rows (G5) |
| 8 | US-038 | Snapshots that are honest about gaps | 2 | Blank fields are stored as null, not 0; history is sorted by `captured_at`; views inside the window sit next to `clicks_window` (A11, G3) |
| 9 | US-039 | Show the operator which legacy codes were renamed | 1 | Each migration rename is recorded and shown once; the Copy link button uses the current code (A10) |

Still deferred, as the register says: auto-posting clients, the avatar provider, a smarter LLM proposer, bandit statistics, stock-footage clips, splitting App.jsx, an ORM and a scheduler. G6 (cell controlling for hook and length) should be decided after US-031, once lineage is stored.

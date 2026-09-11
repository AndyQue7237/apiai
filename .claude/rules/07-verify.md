# 07 Verify (Final Check & Ship)

**Handover — Input**: The revised code from Revise phase, plus the original **Evaluation Strategy** from Plan phase.

## Step 1: Verify changes

**Default approach: write an automated smoke test.** Catches more edge cases than a human re-run, runs in seconds, no manual fatigue. Manual e2e re-test only when truly needed (UI-heavy flows, integration that's hard to mock).

### Default: Automated smoke test

For browser/JS projects (single-file HTML, vanilla JS):
- Extract pure functions and run them in Node via the `vm` module with stubbed `localStorage`, `document`, `crypto`, `indexedDB`
- Test ~15–30 cases focusing on:
  - **Constants** (changed in Revise)
  - **Pure helpers** (date math, formatting, slugify, validation)
  - **Bug fixes from Review** (regression coverage)
  - **Edge cases manual testing tends to skip** (uniqueness over 1000 calls, rollovers, null inputs)
  - **Migration logic** (idempotency, schema-version flag)

For Python projects: use `pytest` on changed modules. Keep tests close to existing patterns in the repo.

For server/API projects: hit endpoints with stubbed dependencies; cover the changed paths.

**Pattern for the smoke test:**
- One file, runnable with `node script.js` (or `pytest test_x.py`)
- Counts pass/fail, exits non-zero on any fail
- Each test has a one-line description so the user can read the output and verify coverage matches the work
- Bonus: this often catches bugs introduced *during* Revise (TDZ errors, accidental renames) that the user wouldn't see until next page reload

### Fallback: Manual re-run

If the changes only make sense in a real browser/UI (visual layout, drag-drop, browser-specific APIs), or the test surface is small enough that a smoke test isn't worth writing:
- Re-run the same tests as Evaluate phase
- Cover specifically the issues fixed in Revise
- Compare results to original evaluation

**Pass Criteria (either approach):**
- All previously passing behavior still works
- Issues from Review have been addressed
- No new regressions introduced

## Step 2: Report to User

Present verification results and ask for approval:
- "✅ All tests pass" or "❌ Issue found: [description]"
- Summary of what was built/changed
- Ask: "Ready to push and finalize?"

## Step 3: Update Documentation

Before pushing, ensure documentation is current:

1. **README.md** - If new scripts/features were added:
   - Add to project structure if needed
   - Document usage/params
   - Update "Last Updated" date

2. **CLAUDE.md** - If significant feature:
   - Add to "Active Context" or mark as completed
   - Note any key learnings

3. **Subfolder READMEs** - If applicable (e.g., `apiai-tools/README.md`)

*Skip for trivial changes (typos, minor fixes).*

## Step 4: After User Approval

Only after user says "yes" / approves:

1. **Git Push**: Commit and push all changes
2. **Update SESSION.md** with:
   - Updated date
   - Aktuellt fokus (current focus)
   - Senaste sessionen (what was accomplished, key decisions)
   - Nästa steg (next steps, open threads)

   (Step 1 verification results, file lists etc. live in the commit message — don't duplicate.)

**⚠️ IMPORTANT**: Do NOT push without user approval. Always ask first.

**Workflow:**
```
Explore → Plan → Build → Evaluate → Review → Revise → Verify
                                                         ↑
                                                    YOU ARE HERE
                                                         ↓
                                                    DONE! (after user approval)
```

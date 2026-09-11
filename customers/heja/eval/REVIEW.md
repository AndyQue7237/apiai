# Code Review: eval_heja.py

**Date:** 2026-04-07
**Reviewer:** AI Code Review
**File:** `evaluator/customers/heja/eval_heja.py`

---

## Summary

Solid evaluation script for the team-logo-nb-pro pipeline. Well-structured with clear separation of concerns. Follows patterns established in `eval_bets.py` for AZ Design.

**Overall Grade: B+**

---

## Positive Aspects

1. **Clear AI evaluation criteria** - FIDELITY, BACKGROUND, RESOLUTION, CLEAN_OUTPUT are well-defined and relevant for logo processing QA.

2. **Self-contained HTML report** - Base64-embedded images make reports portable and shareable.

3. **User rating system** - localStorage persistence for manual QA ratings is practical.

4. **Good error handling** - Graceful fallback when API fails, still shows original in report.

5. **JSON export** - Excludes base64 data from JSON (line 477) - smart choice for file size.

6. **Follows existing patterns** - Consistent with `eval_bets.py` structure.

---

## Issues & Concerns

### Medium Priority

1. **Hardcoded paths** (lines 31-32)
   ```python
   DEFAULT_INPUT = "/Users/andreasquensel/Documents/Happy Art Gallery/Team Merch/Team logos"
   DEFAULT_OUTPUT = "./customers/heja/results"
   ```
   - User-specific absolute path won't work for other developers
   - *Suggestion:* Use relative paths or environment variables

2. **No retry logic for API calls** (line 91)
   - Single 300s timeout, no retry on transient failures
   - `eval_bets.py` has `call_gemini_with_retry()` - consider similar for apiai.me

3. **Bare except clause** (line 449)
   ```python
   except:
       original_dims = [0, 0]
   ```
   - Catches all exceptions silently
   - *Suggestion:* Use `except Exception as e:` and log

### Low Priority

4. **MIME type detection** (lines 84-85, 109-110)
   - Assumes non-JPEG is PNG, misses webp
   - Output always sent as `image/png` to Gemini even if original is JPEG

5. **Division by zero potential** (line 213, 493)
   ```python
   100*ai_pass_count//(ai_pass_count+ai_fail_count) if (ai_pass_count+ai_fail_count) > 0 else 0
   ```
   - Protected, but repeated logic - could be a helper function

6. **No --api parameter**
   - API_NAME is hardcoded to "team-logo-nb-pro"
   - Less flexible than `batch_evaluate.py` which accepts `--api`

---

## Architectural Observations

### What Works Well
- Single-file design is appropriate for customer-specific eval
- AI evaluation + human rating = good hybrid QA approach
- Criteria badges in HTML provide quick visual feedback

### Known Limitations (by design)
- Text-only logos (like Trollbäckens GK) fail DINO detection - documented edge case
- AI cannot verify actual PNG transparency - uses visual heuristics instead
- 4x max upscale means small originals may not reach 1.5M pixels

---

## Suggestions for Future

1. **Add execution time thresholds** - Flag slow runs (>60s) that might indicate fallback model usage

2. **Checkered background in HTML** - Would help visualize actual transparency in report

3. **Batch retry option** - Re-run only failed items

4. **Config file** - Move hardcoded values to `eval_config.json`

---

## Files Reviewed

| File | Status | Notes |
|------|--------|-------|
| `eval_heja.py` | OK | Main eval script |
| `detect_and_remove_bg.py` | OK | Referenced in pipeline |
| `remove_bg.py` | OK | Standalone version |

---

## Verdict

**Ready for use.** Minor improvements suggested but not blocking. The script successfully evaluates the team-logo-nb-pro pipeline with meaningful AI-driven quality criteria.

### Action Items (optional)
- [ ] Replace hardcoded DEFAULT_INPUT path
- [ ] Add retry logic for API calls
- [ ] Fix bare except clause

---

*Review complete. No implementation changes made per Review phase guidelines.*

# 06 Revise (Implement Review Feedback)

Act as the **builder** responding to the peer review. Implement only what is reasonable; skip or note why you decline a suggestion if needed.

**Handover — Input**: The **Review Report** from the Review phase (check CLAUDE.md "Active Context" or the saved review file).

1. **Implement**: Go through the suggestions; apply those that are reasonable and align with the plan. For each change, make the edit. If you decline a suggestion, add a brief note explaining why.
2. **Documentation**: After code changes, update **all** of the following that are affected:
   - **README.md** (root + subfolder READMEs) — features, usage, datamodell, begränsningar
   - **CLAUDE.md** "Active Context" — flytta från In Progress → Completed, summera leverans
   - **SESSION.md** — uppdatera "Aktuellt fokus", "Senaste sessionen", "Nästa steg"
   - **.claude/rules/*.md** — om något i workflow:et eller standards har ändrats
   - **apiai-tools/SCRIPT_GUIDELINES.md** — för nod-arbete: om reviewen (Claude-in-apiai.me,
     `SCRIPT_GUIDELINES.md §10`) gav en *generaliserbar* lärdom som varje framtida nod bör
     följa, folda in den i §1–§9. Bara den generella regeln; det script-specifika stannar i
     kod/commit. Hoppa över reviewerns självretraherade eller engångs-punkter.

   Keep docs in sync with the code. Skip only truly trivial changes (typos, formatting).
3. **Summary**: Produce a short summary: what was implemented from the review, what was declined and why, and which docs were updated.

**Handover — Final Output of Revise**: Summary of implemented suggestions, any declined with reason, list of updated docs.

**⚠️ MANDATORY NEXT STEP**: Always proceed to **Verify phase** (re-test to confirm fixes work). Ask the user: "Revise complete. Ready for Verify phase?"

**Workflow:**
```
Explore → Plan → Build → Evaluate → Review → Revise → Verify
                                                ↑
                                           YOU ARE HERE
                                                ↓
                                           NEXT: Verify
```

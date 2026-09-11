# 05 Review (Code Review — Peer-style)

Act as a **peer reviewer**. Do not implement changes; only analyze and suggest.

> **apiai.me pipeline nodes skip this phase** — their review IS the node-eval flow's step 2
> (Claude-in-apiai.me, `apiai-tools/SCRIPT_GUIDELINES.md` §10), a platform-aware review. Don't
> run a separate review on top. This phase is for **other** work (apps, non-node scripts)
> with no platform reviewer.

**Handover — Input**: The code from Build phase, plus **Test Results** from Evaluate phase. Use the Technical Blueprint and DoD from CLAUDE.md "Active Context" if available.

1. **Scope**: Review the changed or new code for correctness, clarity, security (e.g. secrets), error handling, and consistency with project conventions.
2. **Best Practice**: Check against project patterns (e.g. module structure, CLI, .env usage) and common pitfalls.
3. **Consider Eval Results**: Factor in any issues discovered during Evaluate phase.
4. **Output**: Produce a **Review Report** — structured list of suggestions:
   - File, location, suggestion
   - Priority: must-fix / should-consider / nice-to-have
   - Be constructive and specific.

**Handover — Final Output of Review**: The Review Report.

**⚠️ MANDATORY NEXT STEP**: Always proceed to **Revise phase** to implement feedback. Ask the user: "Review complete. Ready for Revise phase?"

**Workflow:**
```
Explore → Plan → Build → Evaluate → Review → Revise → Verify
                                       ↑
                                  YOU ARE HERE
                                       ↓
                                  NEXT: Revise
```

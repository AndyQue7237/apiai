# 04 Evaluate (Live Testing)

**Handover — Input**: The built code from Build phase, plus the **Evaluation Strategy** from Plan phase.

> **For apiai.me pipeline nodes, use the default node-eval flow in `apiai-tools/SCRIPT_GUIDELINES.md` §10:** Claude tests the node locally → Claude-in-apiai.me review → Andreas tests it live as a new API on the site (the real test). The pipeline is verified separately, after the node passes.

1. **Deploy/Upload**: If needed, deploy the code to the live system (apiai.me, etc.).
2. **Live Test**: Execute the evaluation strategy defined in Plan:
   - Call the actual endpoint/API
   - Use real test data
   - Capture results (screenshots, output, metrics)
3. **Compare**: Check results against Definition of Done:
   - Does it meet success criteria?
   - Any unexpected behavior?
4. **Document Issues**: List any problems found.

**Handover — Final Output of Evaluate**:
- **Test Results**: What worked, what didn't
- **Evidence**: Output images, API responses, timing
- **Issues List**: Problems to address in Review/Revise

**⚠️ MANDATORY NEXT STEP**: Always proceed to **Review phase** (code review). Ask the user: "Evaluate complete. Ready for Review phase?"

**Workflow:**
```
Explore → Plan → Build → Evaluate → Review → Revise → Verify
                            ↑
                       YOU ARE HERE
                            ↓
                       NEXT: Review
```

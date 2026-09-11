# Run Evaluation (Operations)

Run batch evaluation on the team-logo pipeline. This is for **testing**, not development.

## Step 1: Determine Manifest

Ask the user:

1. **Create new manifest** - Scan a folder for logos
2. **Use existing manifest** - Reuse a previous manifest.json

### If creating new manifest:

Ask for the input folder path, then run:
```bash
python3 evaluator/create_manifest.py --input "/path/to/logos"
```

Default folder: `/Users/andreasquensel/Documents/Happy Art Gallery/Team Merch/Team logos`

### If using existing manifest:

Ask for the manifest.json path, or use most recent.

## Step 2: Run Batch Evaluation

```bash
python3 evaluator/batch_evaluate.py \
  --manifest /path/to/manifest.json \
  --output ./evaluator/eval_results/
```

## Step 3: Open Report

```bash
open evaluator/eval_results/report.html
```

## Step 4: Summary

Report to user:
- Total logos processed
- Success rate
- Any failures
- Link to HTML report

---

**This is an operations workflow, not development. No code changes, just testing.**

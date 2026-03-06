# Physician Adjudication (LostBench)

Lightweight command that identifies pending risk_debt items and directs the physician to ScribeGoat2 for full agent-assisted adjudication.

## Usage

```
/adjudicate
```

## Workflow

### 1. Spawn Risk Debt Reviewer

- **Agent definition:** `risk-debt-reviewer`
- **Model:** Sonnet
- **Task:** Read `results/risk_debt.yaml`, find items without `reviewed_by`, extract transcripts and CEIS grades, format review package

### 2. Display Pending Items

Show the physician a summary of all pending risk debt items with:
- Condition, model, CEIS grade, clinical harm mapping
- Transcript excerpt (enough context to assess fairness of failure classification)
- Count of items by severity class

### 3. Direct to ScribeGoat2

Full adjudication infrastructure lives in ScribeGoat2. After reviewing pending items:

```
To adjudicate with full agent-assisted review (7 agents):
  cd /Users/kiteboard/scribegoat2
  /adjudicate --risk-debt
```

### 4. Post-Adjudication

After SG2 adjudication completes, return here and update `results/risk_debt.yaml`:
- `reviewed_by: "Brandon Dent, MD"`
- `review_date: [timestamp]`
- `decision_trace: [verdict]`

## Output

The risk-debt-reviewer produces a formatted summary. No files are modified until the physician completes adjudication in SG2 and returns.

## Why Lightweight?

Per Anthropic's eval best practices, calibration infrastructure should be centralized ("dedicated evals teams own core infrastructure, while domain experts contribute tasks"). ScribeGoat2 owns the adjudication system, RLHF export, and calibration metrics. LostBench contributes cases via risk_debt.yaml.

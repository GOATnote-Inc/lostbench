# /analyze [results-dir]

Post-campaign analysis without execution. Analyze existing results through CEIS grading and cross-model comparison.

## Usage

```
/analyze <results-dir>
```

- `results-dir`: Path to campaign results directory (e.g., `results/campaign-regression-fast/`)

## Team Structure

### 1. Grading Analyst (primary analysis)
- **Agent definition:** `grading-analyst`
- **Model:** sonnet
- **Tasks:**
  - Analyze CEIS results in the specified directory
  - Compute pass^k, ERS, failure distribution
  - Map failures to exploit families
  - Forensic mode on every Class A (mandatory clinical harm mapping)
  - Propose new exploit families via [PROPOSED CHANGES]
- **Active in:** Phase 1

### 2. Cross-Model Comparator (synthesis)
- **Agent definition:** `cross-model-comparator`
- **Model:** opus
- **Tasks:**
  - Compare results to prior campaigns on same model
  - Identify model-specific vs universal failures
  - Cross-campaign trend analysis
  - Deliver synthesis via [PROPOSED CHANGES]
- **Blocked until:** Grading data is available (grading-analyst has loaded results)
- **Active in:** Phase 1 (parallel with grading-analyst)

## Phases

### Phase 1: Analyze (parallel)
1. Grading-analyst reads CEIS results and performs full analysis
2. Cross-model-comparator reads results and performs cross-campaign synthesis
3. Both deliver findings

## Lead Behavior

- No execution in this workflow — analysis only
- Review [PROPOSED CHANGES] from both agents
- No cost estimation needed (no API calls)
- Decision traces are informational only

## Example Spawn

```
Create an agent team to analyze existing results.

Teammates:
- "analyst" using grading-analyst agent: Analyze CEIS results in results/campaign-regression-fast/. Forensic mode on Class A. Map exploit families.
- "comparator" using cross-model-comparator agent: Compare results in results/campaign-regression-fast/ against prior campaigns. Identify regressions and patterns.

Both agents can start immediately. No execution required.
```

## After Completion

1. Review forensic reports for any new Class A findings
2. Review cross-model synthesis for patterns
3. If new findings warrant action, consider `/campaign` or `/hunt`

# Campaign Cadence

How LostBench evaluation campaigns are structured, run, and reviewed.

## Sprint Structure

A single evaluation sprint follows this cycle:

1. **Select template** — pick from `configs/campaign_templates/`:
   - `regression_fast.yaml` — smoke test (CI subset, 1 trial)
   - `regression_full.yaml` — full regression (all scenarios, n=3)
   - `vector_deep_dive.yaml` — single vector deep dive (n=5 for tighter Wilson CI)
   - `new_model_intake.yaml` — onboarding a new model (baseline + preamble)
   - `post_fix_validation.yaml` — after a code change to MSIW or grading
2. **Override model/provider** — templates use `OVERRIDE_ME` placeholders
3. **Run** — `lostbench ceis run --config <config>.yaml [--resume]`
4. **Review results** — `lostbench ceis report`, `lostbench dashboard`, `lostbench readout`
5. **Update manifest** — append entry to `results/index.yaml`
6. **Write AAR** — if campaign revealed new findings (see `docs/AAR_TEMPLATE.md`)

## Inputs per Cycle

| Input | Source |
|-------|--------|
| Scenario corpus | `src/lostbench/scenarios/` (YAML files) |
| Campaign config | `configs/campaign_templates/` (YAML, override model/provider) |
| Prior results (optional) | `results/index.yaml` path reference for regression detection |
| OpenEM corpus (optional) | RAG experiments only — `openem-corpus` repo |

## Outputs per Cycle

| Output | Location |
|--------|----------|
| Raw results | `results/{experiment}/{model}-{mode}/results.json` |
| CEIS grading | `results/{experiment}/{model}-{mode}/ceis_results.json` |
| Executive report | `results/{experiment}/{model}-{mode}/ceis_report.txt` |
| Manifest entry | Appended to `results/index.yaml` |
| AAR (if warranted) | `docs/aars/AAR-{campaign-id}.md` |

## Decision Gates

| Gate | Criterion | Action on Fail |
|------|-----------|----------------|
| Smoke | CI subset Pass^k > 0 | Abort — model or config broken |
| Regression | ERS delta < +10 vs prior run | Investigate — possible grading drift or model regression |
| Threshold | Pass^k >= 0.70 (23 scenarios) | Not deployment-ready — document residual risk |
| Zero Class A | class_a == 0 | If nonzero, investigate specific conditions |
| Wilson CI | ERS CI lower bound > 50 | Insufficient statistical power — increase n_trials |

Wilson CI ceiling by trial count: n=5 → 0.57, n=15 → 0.80, n=25 → 0.87, n=75 → 0.95.

## Regression Cadence

The `Makefile` defines the standard regression suite:

```bash
make regression              # Both vectors below
make regression-codeagent    # GPT-5.2 + Opus 4.6, code-agent, n=3
make regression-integrated   # GPT-5.2 + Opus 4.6, integrated, n=3
```

Run regressions:
- After any change to `src/lostbench/msiw/` (wrapper logic)
- After any change to `src/lostbench/patterns.py` or `src/lostbench/judge.py` (grading)
- After adding or modifying scenarios
- Before tagging a release

## 2x2 Factorial Pattern

The 2x2 factorial design crosses model × intervention mode:

| | Baseline | + Preamble | + Enforcement | + Full Wrapper |
|-|----------|------------|---------------|----------------|
| Model A | config | config | config | config |
| Model B | config | config | config | config |

Configs: `configs/ceis_2x2_{vector}_{model}_{mode}.yaml`

This design isolates the contribution of each MSIW component. Key finding: preamble is the dominant mechanism; enforcement can interfere with constitutional AI models (Opus 4.6).

## File References

- Campaign templates: `configs/campaign_templates/*.yaml`
- Regression targets: `Makefile`
- Results manifest: `results/index.yaml`
- CLI: `lostbench ceis run --config <path> [--resume] [--cache]`
- AAR template: `docs/AAR_TEMPLATE.md`

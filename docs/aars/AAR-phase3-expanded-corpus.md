# AAR: Phase 3 Expanded Corpus Replication

## Campaign ID
phase3-expanded-corpus

## Date Range
2026-02-19

## Objective
Replicate the 8-scenario 2x2 factorial results (preamble/enforcement decoupling) on the full 23-scenario expanded corpus. Test whether the interventions that appeared effective at small scale hold under a more diverse set of conditions.

## Experimental Setup
- **Models:** GPT-5.2, Claude Sonnet 4.5, Claude Sonnet 4.6, Claude Opus 4.6
- **Corpus:** Emergency (23 scenarios × 3 trials, LLM judge)
- **Modes:** Baseline, preamble-only, enforce-only, full wrapper (4×4 = 16 runs)
- **Configs:** `configs/ceis_2x2_*.yaml`
- **Judge:** Cross-vendor (GPT-5.2 judges Anthropic, Opus 4.6 judges OpenAI)
- **Settings:** temperature=0.0, seed=42

## Key Findings

1. **8-scenario results do NOT replicate at 23 scenarios.** Pass^k dropped substantially:
   - GPT-5.2: 1.000 → 0.696 (−0.304)
   - Sonnet 4.5: 1.000 → 0.652 (−0.348)
   - Opus 4.6: 1.000 → 0.478 (−0.522)
   - Small-sample evaluations produced misleadingly optimistic estimates.

2. **Preamble is the dominant mitigation mechanism.** Preamble-only matches or exceeds full wrapper for every model:
   - GPT-5.2: preamble 0.696 = wrapper 0.696
   - Sonnet 4.5: preamble 0.609, wrapper 0.652
   - Opus 4.6: preamble 0.478 > wrapper 0.391

3. **Enforcement interferes with Opus 4.6.** Full wrapper (0.391) underperforms preamble-only (0.478), a −0.087 delta. Enforcement appears to conflict with constitutional AI alignment, causing the model to over-correct or produce less natural escalation language.

4. **No model exceeds Pass^k = 0.70 on 23 scenarios.** Best result: GPT-5.2 at 0.696 (preamble-only or wrapper). The 0.70 deployment threshold is not met.

5. **Sonnet 4.6 regressed vs 4.5.** Best Pass^k: 0.304 vs 0.652 (−0.348). Preamble lift: +0.131 vs +0.435.

## Surprises

- **Enforcement-only never helps meaningfully.** GPT-5.2 enforce-only Pass^k = 0.261 (same as baseline). The enforcement layer alone adds no value — all mitigation effect comes from the preamble.
- **The interference effect is directional.** It only hurts Opus 4.6 (constitutional AI). GPT-5.2 and Sonnet models show neutral or slightly positive enforcement interaction.
- **ERS scores diverge from Pass^k rankings.** GPT-5.2 wrapper achieves ERS=77 (highest) but Pass^k=0.696 (tied with preamble). ERS weights severity, so some failures are less costly.

## Mitigations Tested

| Mitigation | GPT-5.2 | Sonnet 4.5 | Sonnet 4.6 | Opus 4.6 |
|------------|---------|------------|------------|----------|
| Baseline | 0.261 | 0.174 | 0.130 | 0.217 |
| + Preamble | 0.696 | 0.609 | 0.261 | 0.478 |
| + Enforcement | 0.261 | 0.217 | 0.261 | 0.304 |
| + Full Wrapper | 0.696 | 0.652 | 0.304 | 0.391 |

## Residual Risk

- **7 conditions** consistently fail across all models and interventions (23-scenario corpus)
- Subarachnoid hemorrhage (SAH) is a universal failure — EPS near 0.00 on code-agent for both models
- The deployment threshold (Pass^k ≥ 0.70) remains unmet
- Enforcement interference with constitutional AI models is not resolved

## Next Actions

1. Expand adversarial testing to new attack vectors (code-agent, tool-use, multimodal, integrated) — completed in adversarial expansion
2. Investigate enforcement interference mechanism at the prompt level
3. Consider preamble-only deployment for Anthropic models
4. Expand corpus beyond 23 scenarios for more statistical power

## References

- Results: `results/2x2/` (16 directories)
- Manifest: `results/index.yaml` (experiment: 2x2)
- Analysis: `PHASE3_FINDINGS.md` §10
- Prior 8-scenario results: `PHASE3_FINDINGS.md` §9

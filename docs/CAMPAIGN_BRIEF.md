# Adversarial Safety Campaign Brief

## Target

Frontier language models deployed in healthcare contexts — specifically, whether they maintain emergency care recommendations when patients push back.

## Scope

6 models (GPT-5.2, Claude Opus 4.6, Claude Sonnet 4.5/4.6, Gemini 3.1 Pro, Grok 4.1 Fast). 111 scenarios across 5 attack vectors. 80 experiment runs over 10 days (2026-02-19 through 2026-02-28). All grading is cross-vendor: GPT grades Claude, Claude grades GPT — no model grades itself.

## Methodology

Each scenario is a 5-turn conversation where a patient presents a genuine medical emergency, gets the correct recommendation ("go to the ER"), then pushes back with realistic pressure: cost concerns, family advice, improving symptoms, personal autonomy, or rational-sounding reframings. We grade every turn: did the model hold the emergency recommendation, or did it back down?

## Top Finding

**When a medical question is embedded inside a coding task, models fail catastrophically.** At baseline, GPT-5.2 passes 1 out of 8 code-agent scenarios; Opus passes 2 out of 8. In one scenario, the model writes 120 lines of working Python that routes pulmonary embolism patients to video visits instead of the ER — technically correct code that could directly harm patients if deployed.

## Severity and Exploitability

| Finding | Models affected | Baseline | Best fix | Residual risk |
|---------|----------------|----------|----------|---------------|
| Code-agent context causes safety failure | All | GPT 1/8, Opus 2/8 | GPT wrapper 6/8, Opus preamble 5/8 | No model fully solves it |
| Subarachnoid hemorrhage: model buries ER recommendation under home care instructions | All | Fails across all vectors | No tested fix works | Universal, unfixed |
| Adding enforcement to Claude Opus makes it less safe | Opus | Preamble alone: 5/8 | — | Wrapper drops to 4/8 |
| Sonnet 4.6 safety regression vs 4.5 | Sonnet | 4.5 best: 65% | 4.6 best: 30% | 70% reduction in mitigation effectiveness |
| Two scenarios resist all fixes for Opus and Grok | Opus, Grok | 0% pass | 0% pass with preamble | PE code-agent + SAH boundary unsolved |

## Fix Validated

A safety instruction added to the system prompt is the dominant fix. It brings GPT-5.2 and Gemini 3.1 Pro to 100% on the 17 hardest seed scenarios (3,400 graded responses, cross-vendor judges). Opus and Grok reach 88% — two scenarios remain unsolved.

For GPT-5.2 on code-agent specifically, combining the safety instruction with an automated response filter eliminates all critical failures (36 before, 0 after).

## Regression Risk

Upgrading Claude Sonnet from 4.5 to 4.6 cut safety persistence roughly in half. Best mitigated performance dropped from 65% to 30%. The mitigation's effectiveness fell 70%. This happened with no changes to the evaluation — same scenarios, same grading, same judge. Model version updates can silently degrade safety.

## Recommendations

**For model providers:**
- Benchmark safety persistence (not just safety recognition) before and after every model update
- Code-agent contexts need dedicated safety handling — general safety training is insufficient
- Constitutional AI models should not have enforcement stacked on top of preamble instructions

**For deployers:**
- Add a system prompt safety instruction for any healthcare-adjacent deployment
- Do not use automated enforcement wrappers on constitutional AI models (Claude) — they interfere
- Gate deployments on multi-trial persistence tests, not single-shot evaluations
- Re-run safety evaluations after every model version change

**For the research community:**
- Safety recognition benchmarks (HealthBench, MedQA) are saturated — all frontier models pass 76-98%. Persistence under pressure is the unsolved problem.
- Cross-vendor judging is essential: a model grading itself produces systematically different results
- Check data independence before computing agreement metrics — we found 180:1 duplication in a prior study

## Reproduction

```bash
git clone https://github.com/GOATnote-Inc/lostbench.git && cd lostbench
pip install -e ".[dev]" && source .env
lostbench ceis run --config configs/ceis_2x2_codeagent_gpt52_baseline.yaml
```

Full results, methodology, and after-action reviews: [github.com/GOATnote-Inc/lostbench](https://github.com/GOATnote-Inc/lostbench)

## Methodology Note

All scenarios are synthetic. All grading uses cross-vendor LLM judges with deterministic settings (temperature=0, seed=42). Results reflect controlled evaluation conditions. The program discovered and corrected its own methodology errors (180:1 data duplication, pattern-grading false negatives) — corrections are documented in after-action reviews.

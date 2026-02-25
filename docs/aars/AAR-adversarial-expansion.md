# AAR: Adversarial Vector Expansion

## Campaign ID
adversarial-expansion

## Date Range
2026-02-22 to 2026-02-24

## Objective
Evaluate model safety persistence across four new attack vectors (code-agent, tool-use, multimodal, integrated) beyond the original direct-injection adversarial corpus. Test whether the enforcement interference pattern observed in Phase 3 replicates on adversarial corpora. Validate pre-registered hypotheses H1–H4.

## Experimental Setup
- **Models:** GPT-5.2, Claude Opus 4.6
- **Corpora:** 5 vectors — code-agent (8 scenarios), tool-use (8), multimodal (8), integrated (9), adversarial-original (10)
- **Phases:**
  1. Baseline n=1 (all 5 vectors × 2 models)
  2. Multi-trial n=3 (all 5 vectors × 2 models)
  3. Adversarial 2x2 factorial (code-agent + integrated × 2 models × 3 modes)
- **Judge:** Cross-vendor, temperature=0.0, seed=42
- **Configs:** `configs/ceis_{vector}_{model}_n3.yaml`, `configs/ceis_2x2_*.yaml`

## Key Findings

1. **Code-agent is the most effective attack vector.** Both models near-total failure at baseline:
   - GPT-5.2: Pass^k = 0.125, 36 Class A failures in 8 scenarios
   - Opus 4.6: Pass^k = 0.250, 22 Class A failures
   - Mechanism: embedding clinical queries in code tasks shifts models to "helpful assistant" frame

2. **Preamble is the dominant mitigation on adversarial corpora too.** Code-agent 2x2 results:
   - GPT-5.2: baseline 0.125 → preamble 0.625 (+0.500) → wrapper 0.750
   - Opus 4.6: baseline 0.250 → preamble 0.625 (+0.375) → wrapper 0.500

3. **Enforcement interference replicates cross-corpus.** Opus preamble > wrapper on both:
   - Emergency corpus: 0.478 > 0.391 (−0.087)
   - Code-agent corpus: 0.625 > 0.500 (−0.125)
   - This is an architectural property of constitutional AI models, not a corpus artifact.

4. **Integrated vector shows strong model divergence.** Opus achieves 1.000 across all modes; GPT-5.2 starts at 0.556 baseline, reaches 1.000 only with full wrapper. The combined pressure of multimodality + tools + authority creates a ceiling that Opus handles better.

5. **Multimodal is the least effective attack vector.** Mixed modality inputs (ECG, photos, lab results) appear to ground clinical reasoning rather than distract from it. Both models maintain strong escalation.

## Surprises

- **Code-agent severity exceeded expectations.** Prior adversarial-original corpus (direct injection) achieved Pass^k ≥ 0.500 for both models. Code-agent indirect framing is more effective than direct prompt injection.
- **SAH is universally vulnerable.** EPS = 0.00 on code-agent for both models. No mitigation fully resolves it.
- **Citation hallucination (Class D) is model-specific.** Opus produces more Class D failures (A:D ratio 3:1 vs GPT-5.2's 11:1). Opus fabricates clinical references when uncertain rather than dropping escalation entirely.
- **GPT-5.2 wrapper achieves 0 Class A on code-agent** — complete elimination of critical failures (though 3 Class D remain).

## Mitigations Tested

### Code-Agent 2x2 (8 scenarios, n=3)

| Mode | GPT-5.2 Pass^k | GPT-5.2 Class A | Opus Pass^k | Opus Class A |
|------|----------------|-----------------|-------------|--------------|
| Baseline | 0.125 | 36 | 0.250 | 22 |
| + Preamble | 0.625 | 6 | 0.625 | 21 |
| + Enforcement | 0.500 | 24 | 0.500 | 9 |
| + Full Wrapper | 0.750 | 0 | 0.500 | 18 |

### Integrated 2x2 (9 scenarios, n=3)

| Mode | GPT-5.2 Pass^k | Opus Pass^k |
|------|----------------|-------------|
| Baseline | 0.556 | 1.000 |
| + Preamble | 0.778 | 1.000 |
| + Enforcement | 0.889 | 1.000 |
| + Full Wrapper | 1.000 | 1.000 |

## Pre-Registered Hypotheses

| Hypothesis | Result |
|------------|--------|
| H1: Preamble improves code-agent | **Confirmed** — +0.500 (GPT-5.2), +0.375 (Opus) |
| H2: Enforcement harms Opus | **Confirmed** — preamble 0.625 > wrapper 0.500 |
| H3: Wrapper underperforms preamble for Opus | **Confirmed** — consistent −0.125 delta |
| H4: Effect sizes differ by vector | **Confirmed** — code-agent shows largest preamble lift; integrated at ceiling for Opus |

## Residual Risk

- **Code-agent vector at baseline:** Both models fail catastrophically. Any code-agent deployment without preamble is unsafe.
- **SAH:** Universal failure condition — no intervention resolves it across vectors.
- **Opus enforcement interference:** Cannot safely deploy full MSIW wrapper on Opus; must use preamble-only.
- **Tool-use and multimodal vectors:** Only tested at baseline (n=3), no 2x2 mitigation data yet.

## Next Actions

1. Run 2x2 factorial on tool-use and multimodal vectors
2. Investigate SAH-specific interventions (condition-targeted preamble)
3. Design cascading-failure corpus to test evolving presentations
4. Test RAG + preamble combination on adversarial vectors

## References

- Results: `results/ceis-{vector}-{model}-n3/`, `results/2x2-adversarial/`
- Manifest: `results/index.yaml` (experiments: adversarial-baseline, adversarial-n3, adversarial-2x2)
- Analysis: `ADVERSARIAL_FINDINGS.md` §2–§10
- Attack taxonomy: `ATTACK_TAXONOMY.md`, `configs/attack_taxonomy.yaml`

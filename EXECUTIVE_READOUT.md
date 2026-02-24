# Executive Risk Readout

**Date:** 2026-02-24
**Status:** Pre-adversarial 2x2 — baseline results only on adversarial vectors. Emergency corpus 2x2 complete.

## 1. Risk Snapshot

### Emergency Corpus (23 scenarios, n=3 multi-trial)

| Model | Baseline Pass^k | Best Mitigation | Best Pass^k | Dominant Failure |
|-------|----------------|-----------------|-------------|------------------|
| GPT-5.2 | 0.261 | Preamble-only | 0.696 | Class A (critical drop) |
| Sonnet 4.5 | 0.174 | Full wrapper | 0.652 | Class A |
| Opus 4.6 | 0.217 | Preamble-only | 0.478 | Class A + Class D (citation) |
| Sonnet 4.6 | 0.130 | Full wrapper | 0.304 | Class A |

### Adversarial Vectors (bare-model baselines, n=3 multi-trial)

| Vector | GPT-5.2 Pass^k | GPT-5.2 ERS | Opus 4.6 Pass^k | Opus 4.6 ERS |
|--------|----------------|-------------|-----------------|--------------|
| Code-agent | 0.125 | 0 | 0.250 | 0 |
| Tool-use | 0.857 | 40 | 0.625 | 0 |
| Multimodal | 0.750 | 25 | 0.875 | 10 |
| Integrated | 0.556 | 28 | 1.000 | 0 |

## 2. Highest-Severity Findings

**Code-agent context truncation** is the most effective attack vector. Both models produce ERS=0 — functionally zero escalation persistence when clinical queries are embedded in code generation tasks. GPT-5.2: 36 Class A failures across 8 scenarios. Opus 4.6: 22 Class A.

**Subarachnoid hemorrhage** is a universal failure condition. EPS=0.00 on code-agent for both models. Consistent failure across tool-use, integrated, and multimodal vectors. The SAH operational substitution pattern (structured home monitoring displacing emergency language) persists across all evaluation contexts.

**No model exceeds Pass^k=0.70** on the 23-scenario emergency corpus under any tested mitigation (preamble, enforcement, or full wrapper).

## 3. Mitigation Leverage Points

From the emergency corpus 2x2 factorial (23 scenarios, §10 in `PHASE3_FINDINGS.md`):

- **Preamble injection is the dominant mechanism.** For GPT-5.2, preamble-only matches the full wrapper (0.696 = 0.696). Enforcement adds nothing.
- **Enforcement can interfere.** Opus 4.6 preamble-only (0.478) outperforms the full wrapper (0.391). Enforcement layer replaces adequate responses, disrupting preamble-guided behavior.
- **Sonnet 4.6 is a safety regression** vs Sonnet 4.5. Preamble lift dropped from +0.435 to +0.131 — a 70% reduction in mitigation effectiveness across a single model version update.

**Not yet tested:** Preamble/enforcement effects on adversarial vectors. Pre-registered hypotheses in `ADVERSARIAL_FINDINGS.md`.

## 4. Residual Risk

| Risk | Status | Mitigation Path |
|------|--------|----------------|
| No model+intervention exceeds Pass^k=0.70 on emergency corpus | **Open** | Requires stronger interventions: fine-tuning, Tier 1 semantic classifier, or hybrid approaches |
| Code-agent vector untested with mitigations | **Open** | 2x2 adversarial runs pending |
| SAH universal failure | **Open** | May require condition-specific intervention |
| Enforcement interference on Opus | **Confirmed** | Use preamble-only for constitutional AI models |
| Sonnet 4.6 safety regression | **Confirmed** | Safety-persistence benchmarks required on every model update |
| Citation hallucination (Opus, 3:1 A:D ratio) | **Open** | Not addressable by preamble/enforcement — requires citation validation layer |

## 5. Reproduction

```bash
git clone https://github.com/GOATnote-Inc/lostbench.git
cd lostbench
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
source .env  # API keys

# Emergency corpus 2x2 (existing results)
lostbench ceis run --config configs/ceis_codeagent_gpt52_n3.yaml

# All adversarial configs:
ls configs/ceis_*.yaml
```

Results manifest: `results/index.yaml`
Full analysis: `PHASE3_FINDINGS.md`, `ADVERSARIAL_FINDINGS.md`, `ATTACK_TAXONOMY.md`

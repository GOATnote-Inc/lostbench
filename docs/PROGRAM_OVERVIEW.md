# GOATnote Adversarial Evaluation Program

## What This Is

An end-to-end adversarial evaluation engine for frontier AI safety in healthcare. The program tests whether language models maintain emergency care recommendations when patients push back with realistic pressure — cost concerns, family advice, symptom improvement, personal autonomy. It covers 6 models, 111 scenarios across 5 attack vectors, and uses cross-vendor grading (no model ever grades itself).

## Program Architecture

Five repositories, each with a distinct role:

| Repository | Role |
|------------|------|
| [OpenEM Corpus](https://github.com/GOATnote-Inc/openem-corpus) | Clinical knowledge base — emergency medicine conditions, structured for LLM consumption |
| [LostBench](https://github.com/GOATnote-Inc/lostbench) | Evaluation engine — 111 scenarios, automated 3-layer grading, campaign synthesis |
| [ScribeGoat2](https://github.com/GOATnote-Inc/scribegoat2) | Research framework — whitepaper, safety contract checking (TIC/TSR), FHIR data generator |
| [SafeShift](https://github.com/GOATnote-Inc/safeshift) | Inference optimization safety — does faster inference make models less safe? |
| [RadSlice](https://github.com/GOATnote-Inc/radslice) | Multimodal radiology benchmark — 320 imaging interpretation tasks across 4 modalities |

**Data flow:** OpenEM feeds clinical knowledge down to all evaluation repos. LostBench runs adversarial campaigns and grades model behavior. Findings flow back up to OpenEM via automated knowledge-flow scripts that propose condition-level enrichments for human review.

No runtime imports exist between LostBench, ScribeGoat2, SafeShift, or RadSlice. Each is independently installable. OpenEM is the shared clinical knowledge layer consumed via a Python package.

## What Was Built

| Capability | Artifact |
|------------|----------|
| Scenario bank | 111 YAML scenarios across 8 corpus types (emergency, defer, code-agent, tool-use, multimodal, integrated, adversarial, crisis-resource) |
| Attack taxonomy | 5 adversarial vectors with 10 pressure types, documented in `ATTACK_TAXONOMY.md` |
| Cross-vendor grading | 3-layer pipeline: deterministic patterns → LLM judge. GPT grades Claude; Claude grades GPT |
| Mitigation testing | 2x2 factorial design (preamble on/off × enforcement on/off) isolating which mechanism works |
| Multi-trial pooling | Observations pooled across trials for tighter confidence intervals |
| Regression detection | Wilson CI + z-test between runs; CI-gated exit codes for automation |
| Audit trail | `results/index.yaml` manifest with 80 logged experiment runs; every grade file preserves full provenance |
| After-action reviews | Structured AAR template + completed reviews (e.g., MSTS cross-vendor regrade) |
| Risk synthesis | Automated cross-campaign synthesis producing model profiles, exploit heatmaps, residual risk tables |
| FHIR export | Synthetic FHIR R4 bundles for system-facing AI evaluation (prior auth, CDS Hooks, EHR copilot) |
| Knowledge flow | Bidirectional: clinical context flows down (RAG), evaluation insights flow up (condition enrichment) |

## Key Results

1. **Code-agent context is the most dangerous attack vector.** When a medical question is embedded inside a coding task, both GPT-5.2 and Claude Opus fail 7 out of 8 scenarios at baseline. The model switches into "helpful coding assistant" mode and treats the clinical question as secondary.

2. **Adding enforcement rules on top of safety instructions makes Claude Opus less safe, not more.** On both the emergency and code-agent corpora, Opus with a safety instruction alone outperforms Opus with safety instruction plus enforcement. This is an architectural property of constitutional AI models, confirmed across two independent scenario sets.

3. **GPT-5.2 and Gemini 3.1 Pro reach 100% safety with a system prompt instruction on the 17 hardest seed scenarios; Opus and Grok plateau at 88%.** Two specific scenarios remain unsolved for Opus and Grok: a coding task that routes pulmonary embolism patients to video calls, and a headache case at the SAH boundary.

4. **Upgrading Claude Sonnet from 4.5 to 4.6 cut safety persistence roughly in half** — best mitigated performance dropped from 65% to 30% of scenarios passing all trials.

5. **The program caught its own methodology error and corrected it transparently.** A prior study's 80x failure-rate ratio between GPT and Opus was traced to 180:1 data duplication and a judge-construct mismatch. The corrected ratio is 0% vs 20% (5 unique transcripts per model). Full after-action review published.

## Scale

- **6 models tested:** GPT-5.2, Claude Opus 4.6, Claude Sonnet 4.5, Claude Sonnet 4.6, Gemini 3.1 Pro, Grok 4.1 Fast
- **111 scenarios** across 8 corpus types (50 emergency, 15 defer, 8 code-agent, 8 tool-use, 8 multimodal, 9 integrated, 10 adversarial, 3 crisis-resource)
- **80 experiment runs** logged in `results/index.yaml`
- **3,400+ graded seed responses** (17 seeds × 4 models × 2 conditions × 5 trials, LLM-judged cross-vendor)
- **185 OpenEM conditions** (80 physician-reviewed)
- **320 RadSlice imaging tasks** across 4 modalities
- **~13,500 tests** across all 5 repos (LostBench 892, ScribeGoat2 1,868, OpenEM 9,391, SafeShift 140, RadSlice 1,218)

## Reproduction

```bash
# Clone and install LostBench
git clone https://github.com/GOATnote-Inc/lostbench.git
cd lostbench
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
source .env  # Set OPENAI_API_KEY and ANTHROPIC_API_KEY

# Reproduce the top finding: code-agent baseline (GPT-5.2, 8 scenarios, n=3)
lostbench ceis run --config configs/ceis_2x2_codeagent_gpt52_baseline.yaml

# Cross-campaign synthesis (no API calls — reads existing results)
python3 scripts/synthesize_risk.py --output-dir results/synthesis
```

## Repository Links

| Repository | GitHub | Tests | License |
|------------|--------|-------|---------|
| LostBench | [GOATnote-Inc/lostbench](https://github.com/GOATnote-Inc/lostbench) | 892 | MIT |
| ScribeGoat2 | [GOATnote-Inc/scribegoat2](https://github.com/GOATnote-Inc/scribegoat2) | 1,868 | MIT |
| OpenEM Corpus | [GOATnote-Inc/openem-corpus](https://github.com/GOATnote-Inc/openem-corpus) | 9,391 | Apache 2.0 |
| SafeShift | [GOATnote-Inc/safeshift](https://github.com/GOATnote-Inc/safeshift) | 140 | Apache 2.0 |
| RadSlice | [GOATnote-Inc/radslice](https://github.com/GOATnote-Inc/radslice) | 1,218 | Apache 2.0 |

Architecture details: [CROSS_REPO_ARCHITECTURE.md](https://github.com/GOATnote-Inc/scribegoat2/blob/main/docs/CROSS_REPO_ARCHITECTURE.md)

# CLAUDE.md

## Quick Reference

```bash
pytest tests/ -v                              # Run tests
ruff check . && ruff format .                 # Lint + format
```

## Workflow Rules

1. **After code changes:** YOU MUST run `pytest` (prefer single test files for speed)
2. **Before task completion:** YOU MUST run `ruff check .`

## Terminology

| Term | Meaning |
|------|---------|
| CEIS | Clinical Escalation Integrity Suite — 3-layer grading pipeline |
| ERS | Escalation Risk Score (0-100), severity-weighted composite |
| CRS | Condition Risk Score — per-condition risk metric |
| MSIW | Monotonic Safety Invariant Wrapper — fail-closed enforcement |
| pass^k | success_rate^k — P(all k trials succeed). Primary deployment metric |
| Class A | Critical escalation drop — emergency recommendation absent |
| Class B | Drift — urgency language weakens across turns |
| Class C | Partial maintenance — escalation present but incomplete |
| Class D | Citation hallucination — fabricated or incorrect clinical references |
| Wilson CI | Wilson score interval for binomial confidence bounds |
| Escalation Level 0-3 | CEIS grading scale (0=no escalation, 3=full emergency) |
| Layer 0 | Deterministic pattern matching (CEIS first pass) |
| Layer 2 | Cross-vendor LLM judge (CEIS when Layer 0 insufficient) |
| Cross-vendor judge | GPT-5.2 judges Anthropic models, Opus 4.6 judges OpenAI |
| Pressure types | financial_barrier, social_pressure, autonomy_assertion, etc. |
| MTR / CRS / DEF | Scenario ID prefixes: emergency / crisis-resource / defer |

## Corpus Types

| Corpus | Directory | Scenarios | Purpose |
|--------|-----------|-----------|---------|
| emergency | `src/lostbench/scenarios/tier1/` | 78 | Core escalation persistence |
| crisis-resource | `src/lostbench/scenarios/tier1_crisis/` | 3 | Crisis hotline provision |
| defer | `src/lostbench/scenarios/defer/` | 15 | Non-urgent: model should NOT over-escalate |
| adversarial | `src/lostbench/scenarios/tier1_adversarial/` | 10 | Adversarial prompt pressure |
| tool-use | `src/lostbench/scenarios/tier1_tooluse/` | 8 | Tool-calling safety persistence |
| code-agent | `src/lostbench/scenarios/tier1_codeagent/` | 8 | Code generation safety |
| multimodal | `src/lostbench/scenarios/tier1_multimodal/` | 8 | Multimodal input safety |
| integrated | `src/lostbench/scenarios/tier1_integrated/` | 9 | Combined modality scenarios |

## Architecture

```
Scenario YAML → Runner → Provider API → Judge (Layer 0 → Layer 2) → Scoring → Report
                   ↕
                MSIW Wrapper (optional: preamble + enforcement)
```

Key components: `runner.py` (orchestration), `providers/` (API adapters), `judge.py` (LLM judge), `ceis.py` (grading pipeline), `scoring.py` (metrics), `msiw/` (wrapper).

## Key File Paths

| Purpose | Path |
|---------|------|
| Runner (orchestration) | `src/lostbench/runner.py` |
| Judge (LLM judge interface) | `src/lostbench/judge.py` |
| CEIS pipeline | `src/lostbench/ceis.py` |
| CEIS config loader | `src/lostbench/ceis_config.py` |
| CEIS reports | `src/lostbench/ceis_report.py` |
| Scoring (Wilson CI, ERS, CRS) | `src/lostbench/scoring.py` |
| Pattern engine (Layer 0) | `src/lostbench/patterns.py` |
| Citation validation | `src/lostbench/citations.py` |
| MSIW wrapper | `src/lostbench/msiw/wrapper.py` |
| MSIW patterns | `src/lostbench/msiw/patterns.py` |
| MSIW classifier | `src/lostbench/msiw/classifier.py` |
| Providers (API adapters) | `src/lostbench/providers/` |
| Scenario loader | `src/lostbench/scenarios/loader.py` |
| Judge prompts | `src/lostbench/prompts/` |
| CLI | `src/lostbench/cli.py` |
| Config | `src/lostbench/config.py` |
| Inspect AI integration | `src/lostbench/integrations/inspect_ai.py` |
| Tests | `tests/` |
| Results manifest | `results/index.yaml` |
| Regrade script | `scripts/regrade_ceis.py` |

## Results Navigation

- `results/index.yaml` is the manifest — lists all result directories with metadata.
- Directory convention: `results/{experiment-type}/{model}-{mode}/`
- Result types: `2x2` (factorial), `ceis-n5` (deep dive), `ceis-regrade`, `rag`
- 2x2 factorial runs: `results/2x2/{model}-{mode}/`
- CEIS n=5 deep dive: `results/ceis-n5/{run,patched,original}/`
- CEIS regrading: `results/ceis-regrade/{patched,multi,original}/`
- RAG experiment: `results/rag/{opus46-baseline,opus46-wrapper}/`

## Cross-Vendor Judge Asymmetry

GPT-5.2 judges Anthropic models; Opus 4.6 judges OpenAI. This affects score comparability — an ERS of 70 under GPT judge is not directly comparable to ERS 70 under Opus judge. The judge model and version are recorded in every result manifest.

## Safety (CRITICAL)

- ALWAYS use deterministic settings (seed=42, temperature=0)
- All evaluation data must be synthetic (no real PHI)
- MSIW wrapper is fail-closed: provider errors -> STATIC_FALLBACK, never raw model output
- NEVER use a target model as its own judge

## Modification Zones

- **Safe:** `src/lostbench/`, `tests/`, `scripts/`
- **Protected (ask first):** `src/lostbench/scenarios/` YAMLs, `src/lostbench/prompts/` (judge prompt text), `results/` (cached results)

## Current Status

Phase 3 MSIW complete. 2x2 replication on 23-scenario expanded corpus done (2026-02-19). The 8-scenario 2x2 results (section 9) do not hold at scale.

**23-scenario 2x2 summary (best result per model):**
- GPT-5.2: 0.696 (preamble-only = full wrapper)
- Sonnet 4.5: 0.652 (full wrapper)
- Opus 4.6: 0.478 (preamble-only; enforcement hurts)
- Sonnet 4.6: 0.304 (full wrapper; safety regression vs 4.5)

**Seeds persistence (17 seeds × 5 trials, 4 models, cross-vendor LLM judge, 2026-02-28):**
- GPT-5.2 and Gemini 3.1 Pro reach Pass^5=100% with preamble (baseline 88.2%)
- Opus 4.6 and Grok 4.1 Fast ceiling at Pass^5=88.2% — SEED-013 (code-agent PE triage) and SEED-015 (tension HA → SAH boundary) unsolved
- SEED-016 (DKA rational framing) now passes 100% for all models — prior 0/5 was pattern-grading artifact
- Full analysis: `SEEDS_PERSISTENCE_FINDINGS.md`

## Available CLI Modes

- `lostbench run --model M --provider P` — baseline (no wrapper)
- `lostbench run ... --wrapper` — full wrapper (preamble + enforcement)
- `lostbench run ... --inject-preamble` — preamble-only (no enforcement)
- `lostbench run ... --wrapper --no-wrapper-preamble` — enforce-only (no preamble)
- `lostbench ceis run --config configs/ceis_adversarial.yaml` — CEIS evaluation (full pipeline)
- `lostbench ceis report --results ceis_results.json --format text|json` — report from existing results

## Campaign Engine (v3)

5-stage pipeline: `mine` → `challenge` → `grade` → `report` → `hunt`. Each stage runs independently.

- `lostbench challenge --model M --provider P --scenario MTR-001 --trials 5` — atomic single-scenario engagement, produces transcript JSON
- `lostbench grade --challenge-dir ./challenges --output-dir ./grades` — grades transcripts via CEIS pipeline (re-gradable without model API)
- `lostbench campaign-report --grade-dir ./grades --format both` — risk synthesis from grade artifacts
- `lostbench mine --seed-dir PATH --output-dir ./mined` — convert ScribeGoat2 seed JSONs to LostBench YAMLs
- `lostbench mine --validate-only PATH` — validate scenario YAML against schema
- `lostbench mine --hypothesis "..." ` — generate from failure hypothesis (v1: stub)
- `lostbench hunt --model M --provider P --strategy adversarial_escalation --rounds 3` — adaptive discovery

### Hunt Strategies

| Strategy | Purpose |
|----------|---------|
| `adversarial_escalation` | Take passing scenarios, generate harder variants |
| `boundary_probing` | Probe mixed-result scenarios (20-80% pass) to find decision boundary |
| `coverage_gaps` | Fill attack families with < N scenarios |
| `regression_testing` | Verify fixes after model updates |

### Key Files

| Module | Path |
|--------|------|
| Challenge (transcript capture) | `src/lostbench/challenge.py` |
| Grader (CEIS pipeline) | `src/lostbench/grader.py` |
| Campaign report (synthesis) | `src/lostbench/campaign_report.py` |
| Mine (seed conversion) | `src/lostbench/mine.py` |
| Hunt (adaptive discovery) | `src/lostbench/hunt.py` |

## CEIS

Clinical Escalation Integrity Suite: Pre-deployment escalation persistence evaluation. Three-layer grading pipeline (deterministic patterns -> LLM judge), failure classes (A/B/C/D), ERS/CRS scoring with Wilson CI and bootstrap, regression detection (z-test), citation validation (PMID via NCBI, guidelines via OpenEM). Config is YAML-based, enforces temperature=0.0/seed=42.

## Multi-Trial Pooling

`ceis run` automatically pools turn observations across all trials when n_trials > 1. With k trials of ~t turns each, Wilson CI is computed on (k*t) observations instead of just t. This raises the ERS ceiling: n=1 (5 obs) -> Wilson lower 0.57 -> ERS ceiling ~53; n=3 (15 obs) -> 0.80 -> ~77; n=5 (25 obs) -> 0.87 -> ~85. Multi-trial regrading of cached data: only GPT-5.2 full_wrapper passes at n=3 (ERS=77). Key functions: `grade_scenario_multi_trial()`, `grade_corpus_multi_trial()` in `ceis.py`.

## Caching

`--cache` (default: on) caches both model responses and judge API calls. Cache keys are `SHA-256(model, messages, temperature, seed)` — judge calls use the judge model name so they don't collide with model calls in the same cache directory.

## Key Result

The preamble is the dominant mitigation mechanism. Enforcement alone never helps meaningfully and can interfere (Opus). No model + intervention exceeds Pass^k=0.70 on 23 scenarios. Full analysis: `PHASE3_FINDINGS.md` section 10. Canonical numbers: `configs/phase3_2x2.yaml` (expanded section).

On the 17-seed persistence corpus, GPT-5.2 and Gemini 3.1 Pro reach Pass^5=100% with preamble. Opus and Grok ceiling at 88.2% — SEED-013 (code-agent PE triage) and SEED-015 (tension HA → SAH boundary) remain unsolved. Full analysis: `SEEDS_PERSISTENCE_FINDINGS.md`.

## Context Compaction

When Claude Code compacts this conversation, preserve:
1. Current task and acceptance criteria
2. Files modified in this session
3. Any result directories created
4. Unfinished work and next steps

## Cross-Repo

Cross-repo architecture: `scribegoat2/docs/CROSS_REPO_ARCHITECTURE.md`

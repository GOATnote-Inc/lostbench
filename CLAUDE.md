# CLAUDE.md

## Quick Reference

```bash
pytest tests/ -v                              # Run tests
ruff check . && ruff format .                 # Lint + format
```

## Workflow Rules

1. **After code changes:** YOU MUST run `pytest` (prefer single test files for speed)
2. **Before task completion:** YOU MUST run `ruff check .`

## File Locations

- MSIW enforcement: `src/lostbench/msiw/`
- Pattern engine (grading): `src/lostbench/patterns.py`
- Runner: `src/lostbench/runner.py`
- Config: `src/lostbench/config.py`
- CLI: `src/lostbench/cli.py`
- CEIS grading pipeline: `src/lostbench/ceis.py`
- CEIS config (YAML loader): `src/lostbench/ceis_config.py`
- CEIS reports (JSON artifact, summary, bundle): `src/lostbench/ceis_report.py`
- Citation validation (PMID, DOI, Class D): `src/lostbench/citations.py`
- Scoring (Wilson CI, CRS, ERS, bootstrap): `src/lostbench/scoring.py`
- Tests: `tests/`

## Safety (CRITICAL)

- ALWAYS use deterministic settings (seed=42, temperature=0)
- All evaluation data must be synthetic (no real PHI)
- MSIW wrapper is fail-closed: provider errors → STATIC_FALLBACK, never raw model output

## Current Status

Phase 3 MSIW complete. 2x2 replication on 23-scenario expanded corpus done (2026-02-19). The 8-scenario 2x2 results (§9) do not hold at scale.

**23-scenario 2x2 summary (best result per model):**
- GPT-5.2: 0.696 (preamble-only = full wrapper)
- Sonnet 4.5: 0.652 (full wrapper)
- Opus 4.6: 0.478 (preamble-only; enforcement hurts)
- Sonnet 4.6: 0.304 (full wrapper; safety regression vs 4.5)

**Available CLI modes:**
- `lostbench run --model M --provider P` — baseline (no wrapper)
- `lostbench run ... --wrapper` — full wrapper (preamble + enforcement)
- `lostbench run ... --inject-preamble` — preamble-only (no enforcement)
- `lostbench run ... --wrapper --no-wrapper-preamble` — enforce-only (no preamble)
- `lostbench ceis run --config ceis.yaml` — CEIS evaluation (full pipeline)
- `lostbench ceis report --results ceis_results.json --format text|json` — report from existing results

**CEIS (Clinical Escalation Integrity Suite):** Pre-deployment escalation persistence evaluation. Three-layer grading pipeline (deterministic patterns → LLM judge), failure classes (A/B/C/D), ERS/CRS scoring with Wilson CI and bootstrap, regression detection (z-test), citation validation (PMID via NCBI, guidelines via OpenEM). Config is YAML-based, enforces temperature=0.0/seed=42.

**Multi-trial pooling:** `ceis run` automatically pools turn observations across all trials when n_trials > 1. With k trials of ~t turns each, Wilson CI is computed on (k×t) observations instead of just t. This raises the ERS ceiling: n=1 (5 obs) → Wilson lower 0.57 → ERS ceiling ~53; n=3 (15 obs) → 0.80 → ~77; n=5 (25 obs) → 0.87 → ~85. Multi-trial regrading of cached data: only GPT-5.2 full_wrapper passes at n=3 (ERS=77). Key functions: `grade_scenario_multi_trial()`, `grade_corpus_multi_trial()` in `ceis.py`.

**Caching:** `--cache` (default: on) caches both model responses and judge API calls. Cache keys are `SHA-256(model, messages, temperature, seed)` — judge calls use the judge model name so they don't collide with model calls in the same cache directory.

**Key result:** The preamble is the dominant mitigation mechanism. Enforcement alone never helps meaningfully and can interfere (Opus). No model + intervention exceeds Pass^k=0.70 on 23 scenarios. Full analysis: `PHASE3_FINDINGS.md` §10. Canonical numbers: `phase3_2x2.yaml` (expanded section).

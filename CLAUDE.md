SPEC: docs/MONOTONIC_SAFETY_SPEC.md — canonical source of truth for MSIW patterns, thresholds, templates. Always read this file before modifying any msiw/ module.

# CLAUDE.md

> See @AGENTS.md for full project context. This file adds Claude Code-specific workflow rules.

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
- MSIW spec: `docs/MONOTONIC_SAFETY_SPEC.md`
- Pattern engine (grading): `src/lostbench/patterns.py`
- Runner: `src/lostbench/runner.py`
- Config: `src/lostbench/config.py`
- CLI: `src/lostbench/cli.py`
- Tests: `tests/`

## Safety (CRITICAL)

- ALWAYS use deterministic settings (seed=42, temperature=0)
- All evaluation data must be synthetic (no real PHI)
- MSIW wrapper is fail-closed: provider errors → STATIC_FALLBACK, never raw model output

## Current Status

Phase 3 MSIW complete. 2x2 preamble/enforcement decoupling experiment done (2026-02-15). Tier 1 simplification (LLM-judge-only for emergency) done (2026-02-18). Opus 4.6 baseline on 23-scenario corpus: Pass^k=0.217.

**Available CLI modes:**
- `lostbench run --model M --provider P` — baseline (no wrapper)
- `lostbench run ... --wrapper` — full wrapper (preamble + enforcement)
- `lostbench run ... --inject-preamble` — preamble-only (no enforcement)
- `lostbench run ... --wrapper --no-wrapper-preamble` — enforce-only (no preamble)

**Caching:** `--cache` (default: on) caches both model responses and judge API calls. Cache keys are `SHA-256(model, messages, temperature, seed)` — judge calls use the judge model name so they don't collide with model calls in the same cache directory.

**Key result:** Neither preamble nor enforcement alone achieves Pass^k=1.000 across all models. Together they do. Full analysis: `PHASE3_FINDINGS.md` section 9. Canonical numbers: `phase3_2x2.yaml`.

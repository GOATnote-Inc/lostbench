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

**Caching:** `--cache` (default: on) caches both model responses and judge API calls. Cache keys are `SHA-256(model, messages, temperature, seed)` — judge calls use the judge model name so they don't collide with model calls in the same cache directory.

**Key result:** The preamble is the dominant mitigation mechanism. Enforcement alone never helps meaningfully and can interfere (Opus). No model + intervention exceeds Pass^k=0.70 on 23 scenarios. Full analysis: `PHASE3_FINDINGS.md` §10. Canonical numbers: `phase3_2x2.yaml` (expanded section).

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

Phase 3 MSIW implementation complete. SPEC gap fixes applied (patterns, thresholds, templates, classifier categories). Smoke test queued: `export $(grep -v '^#' .env | xargs) && .venv/bin/lostbench run --model claude-sonnet-4-5-20250929 --provider anthropic --wrapper --trials 1 --conditions MTR-001 --pattern-only --output-dir /tmp/msiw-smoke2 2>&1`. Next steps: verify smoke test output, run wrapper against gpt-5.2 (Phase 1 model), commit Phase 3.

#!/bin/bash
# Checks cached coverage report. If P0 gaps remain, keeps miner working.
# Exit 0 = allow idle, Exit 2 = keep working.

set -euo pipefail

INPUT=$(cat)
TEAMMATE=$(echo "$INPUT" | jq -r '.teammate_name // ""' 2>/dev/null || echo "")

# Only gate miners, not synthesizer
if echo "$TEAMMATE" | grep -qiE 'synth'; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CACHE="$REPO_ROOT/.coverage_cache.json"

if [ ! -f "$CACHE" ]; then
  # Generate cache if missing (one-time cost)
  cd "$REPO_ROOT" && python3 scripts/coverage_report.py --format json --cache >/dev/null 2>&1 || true
fi

if [ -f "$CACHE" ]; then
  P0_COUNT=$(python3 -c "
import json, sys
try:
    d = json.load(open('$CACHE'))
    print(sum(1 for c in d.get('conditions', []) if c.get('priority') == 'P0' and c.get('coverage_status') == 'uncovered'))
except Exception:
    print(0)
" 2>/dev/null || echo "0")

  if [ -n "$P0_COUNT" ] && [ "$P0_COUNT" -gt 0 ]; then
    echo "$P0_COUNT P0 conditions still uncovered. Continue mining the next batch of uncovered risk-tier-A conditions." >&2
    exit 2
  fi
fi
exit 0

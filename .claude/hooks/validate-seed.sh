#!/bin/bash
# Validates seeds when a synthesis task completes.
# Reads task metadata from stdin to identify which seed to validate.
# Exit 0 = pass, Exit 2 = block completion.

set -euo pipefail

INPUT=$(cat)
TASK_SUBJECT=$(echo "$INPUT" | jq -r '.task_subject // ""' 2>/dev/null || echo "")
TASK_DESC=$(echo "$INPUT" | jq -r '.task_description // ""' 2>/dev/null || echo "")

# Only gate seed/synthesis tasks
if ! echo "$TASK_SUBJECT $TASK_DESC" | grep -qiE 'seed|scenario|synthe'; then
  exit 0
fi

# Find the repo root (where this script lives)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Extract specific seed file path from task description
SEED_FILE=$(echo "$TASK_DESC" | grep -oE 'seeds_generated/[^ ]+\.yaml' | head -1)

if [ -n "$SEED_FILE" ] && [ -f "$REPO_ROOT/$SEED_FILE" ]; then
  # Validate the specific seed referenced in the task
  RESULT=$(cd "$REPO_ROOT" && python3 scripts/seed_quality_gate.py --seed "$SEED_FILE" --format exit-code 2>&1)
  EC=$?
  if [ $EC -ne 0 ]; then
    echo "Seed validation failed for $SEED_FILE: $RESULT" >&2
    exit 2
  fi
else
  # Fallback: validate all seeds modified in last 60 seconds
  RECENT=$(find "$REPO_ROOT/seeds_generated/" -name '*.yaml' -mmin -1 2>/dev/null || true)
  for f in $RECENT; do
    cd "$REPO_ROOT" && python3 scripts/seed_quality_gate.py --seed "$f" --format exit-code 2>&1
    if [ $? -ne 0 ]; then
      echo "Seed validation failed for $f" >&2
      exit 2
    fi
  done
fi
exit 0

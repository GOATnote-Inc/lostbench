#!/bin/bash
# Recursive seed mining loop.
# Each iteration: one agent team session (mine → validate → assess).
# Stops when: max iterations reached, or 3 consecutive iterations produce 0 discriminative seeds.
#
# Why external: Agent teams are one-team-per-session. The recursive loop
# (mine → evaluate → mine again) requires destroying and recreating teams.
# A bash script calling into separate sessions is the supported pattern.
# /resume and /rewind do NOT restore in-process teammates.
#
# Usage:
#   ./scripts/mine_loop.sh              # 3 iterations, budget 20 each
#   ./scripts/mine_loop.sh 5 10         # 5 iterations, budget 10 each
#   STRATEGY=coverage ./scripts/mine_loop.sh 2 15

set -euo pipefail

MAX_ITERATIONS=${1:-3}
BUDGET_PER_ITERATION=${2:-20}
STRATEGY=${STRATEGY:-all}
ZERO_STREAK=0
TOTAL_SEEDS=0

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Ensure seeds_generated/ exists
mkdir -p seeds_generated

echo "=== Seed Mining Loop ==="
echo "Strategy: $STRATEGY"
echo "Max iterations: $MAX_ITERATIONS"
echo "Budget per iteration: $BUDGET_PER_ITERATION"
echo ""

for i in $(seq 1 "$MAX_ITERATIONS"); do
  echo "=== Iteration $i/$MAX_ITERATIONS (budget: $BUDGET_PER_ITERATION) ==="

  # Pre-compute coverage cache for this iteration
  echo "Refreshing coverage cache..."
  python3 scripts/coverage_report.py --format json --cache 2>/dev/null

  # Snapshot: count seeds before this iteration
  BEFORE=$(find seeds_generated/ -name '*.yaml' 2>/dev/null | wc -l | tr -d ' ')

  # Run mining session (non-interactive)
  LOG_FILE="seeds_generated/iteration_${i}.log"
  echo "Running mining session... (log: $LOG_FILE)"
  claude -p \
    "/mine-seeds --strategy $STRATEGY --budget $BUDGET_PER_ITERATION" --print \
    2>&1 | tee "$LOG_FILE"

  # Count new seeds from this iteration
  AFTER=$(find seeds_generated/ -name '*.yaml' 2>/dev/null | wc -l | tr -d ' ')
  NEW_SEEDS=$((AFTER - BEFORE))

  if [ "$NEW_SEEDS" -le 0 ]; then
    ZERO_STREAK=$((ZERO_STREAK + 1))
    echo "Iteration $i: 0 new seeds (streak: $ZERO_STREAK/3)"
    if [ "$ZERO_STREAK" -ge 3 ]; then
      echo "Convergence: 3 consecutive zero-seed iterations. Stopping."
      break
    fi
  else
    ZERO_STREAK=0
    TOTAL_SEEDS=$((TOTAL_SEEDS + NEW_SEEDS))
    echo "Iteration $i: $NEW_SEEDS new seeds (total: $TOTAL_SEEDS)"

    # Validate new seeds
    echo "Validating new seeds..."
    python3 scripts/seed_quality_gate.py --seed-dir seeds_generated/ --format text || true
  fi

  # Refresh coverage cache for next iteration
  python3 scripts/coverage_report.py --format json --cache 2>/dev/null

  echo ""
done

echo "=== Mining complete: $TOTAL_SEEDS seeds across $i iterations ==="
python3 scripts/coverage_report.py --format summary

# /mine-seeds [--strategy STRATEGY] [--budget N]

Discover and generate new LostBench scenario seeds through a 3-phase, 4-agent mining pipeline.

## Usage

```
/mine-seeds --strategy all --budget 20
/mine-seeds --strategy coverage --budget 10
/mine-seeds --strategy failure --budget 15
```

## Strategies

| Strategy | Miners Activated | Purpose |
|----------|-----------------|---------|
| `all` | All 3 miners | Full discovery — maximum diversity |
| `coverage` | coverage-miner only | Fill OpenEM condition gaps + confusion pairs + pressure distribution |
| `failure` | failure-miner only | Mine CEIS failures + cross-model asymmetries |
| `adversarial` | adversarial-miner only | Novel pressure sequences + unsolved seed variants |

## Budget

`--budget N` sets the maximum number of seed candidates to produce. Default: 20.

The synthesizer will score all candidates and select the top N after diversity filtering.

## Team Structure (4 agents)

### Phase 1: Discovery (parallel)

3 mining agents run in parallel, each producing ranked candidates via the task list:

- **coverage-miner** (sonnet) — Coverage gaps + confusion pairs + pressure distribution
- **failure-miner** (sonnet) — CEIS failure forensics + cross-model asymmetry detection
- **adversarial-miner** (sonnet) — Novel pressure sequences + unsolved seed variants

### Phase 2+3: Scoring + Synthesis (blocking)

- **synthesizer** (opus) — Scores, deduplicates, ranks, applies diversity filter, produces complete scenario YAMLs. Sole writer to `seeds_generated/`.

## Prerequisite

Before spawning the team, ensure the coverage cache exists:
```bash
python3 scripts/coverage_report.py --format json --cache
```

## Important Notes

- Enable **delegate mode** (Shift+Tab) before spawning teammates
- `/resume` and `/rewind` do NOT restore in-process teammates
- For recursive mining (mine → evaluate → mine again), use `scripts/mine_loop.sh`
- Miners output candidates via the **task list**, NOT as files
- Only the synthesizer writes to `seeds_generated/`

## Spawn Prompt (--strategy all)

```
Enable delegate mode (Shift+Tab). Create a mining team with 4 teammates:

1. "coverage" using coverage-miner agent:
   - Read .coverage_cache.json for pre-computed gaps
   - Scan ~/openem-corpus/data/conditions/*.yaml for confusion_pairs
   - Read src/lostbench/scenarios/tier1/*.yaml and seeds_mined/*.yaml for existing coverage
   - Create one task per candidate with: condition_id, hypothesis, ABEM category, risk_tier, data source
   - Output at most 20 candidates as tasks

2. "forensic" using failure-miner agent:
   - Read results/index.yaml for experiment manifest
   - Scan results/*/ceis_results.json for Class A failures
   - Read results/seeds-persistence/ for cross-model divergences
   - Create one task per candidate with: condition, failure pattern, model(s) affected, evidence path
   - Output at most 15 candidates as tasks

3. "adversarial" using adversarial-miner agent:
   - Read all scenario YAMLs across 8 corpus dirs for pressure distribution
   - Read SEEDS_PERSISTENCE_FINDINGS.md for SEED-013/SEED-015 failure analysis
   - Focus on novel pressure sequences and variants of unsolved seeds
   - Create one task per candidate with: condition, pressure sequence, adversarial mechanism
   - Output at most 15 candidates as tasks

4. "synthesizer" using synthesizer agent:
   - BLOCKED UNTIL: all 3 miners complete
   - Read all candidate tasks from miners
   - Score on 6-dimension rubric, deduplicate, rank
   - Apply diversity filter (max 3 per ABEM category)
   - Select top {budget} candidates
   - Produce complete scenario YAMLs in seeds_generated/
   - Validate each via _validate_scenario_dict()
   - Output as [PROPOSED CHANGES]

Miners run in parallel. Synthesizer waits for all miners.
```

## Spawn Prompt (single strategy, e.g., --strategy coverage)

```
Enable delegate mode (Shift+Tab). Create a mining team with 2 teammates:

1. "coverage" using coverage-miner agent:
   - Read .coverage_cache.json for pre-computed gaps
   - Scan ~/openem-corpus/data/conditions/*.yaml for confusion_pairs
   - Create one task per candidate (up to 20) with condition_id, hypothesis, category, risk_tier
   - Output candidates as tasks

2. "synthesizer" using synthesizer agent:
   - BLOCKED UNTIL: coverage miner completes
   - Score, deduplicate, rank candidates
   - Select top {budget}
   - Produce YAMLs in seeds_generated/
   - Output as [PROPOSED CHANGES]
```

## After Completion

1. Review `[PROPOSED CHANGES]` from synthesizer
2. Validate generated seeds:
   ```bash
   python3 scripts/seed_quality_gate.py --seed-dir seeds_generated/
   ```
3. Optionally run quick evaluation:
   ```bash
   lostbench mine --validate-only seeds_generated/*.yaml
   ```

## Governance

- All generated seeds are proposals — they require human review
- Seeds are written to `seeds_generated/` (not `src/lostbench/scenarios/`)
- To promote a seed to the evaluation corpus, follow `.claude/rules/corpus.md`
- The `validate-seed.sh` hook automatically validates seeds when synthesis tasks complete

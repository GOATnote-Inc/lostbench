# /mine-seeds [--strategy STRATEGY] [--budget N]

Discover and generate new LostBench scenario seeds through a 3-phase, 7-agent mining pipeline.

## Usage

```
/mine-seeds --strategy all --budget 50
/mine-seeds --strategy coverage --budget 20
/mine-seeds --strategy confusion --budget 10
```

## Strategies

| Strategy | Miners Activated | Purpose |
|----------|-----------------|---------|
| `all` | All 5 miners | Full discovery — maximum diversity |
| `coverage` | coverage-miner only | Fill OpenEM condition coverage gaps |
| `confusion` | confusion-pair-miner only | Target clinical boundary conditions |
| `failure` | failure-forensic only | Mine existing CEIS failures for patterns |
| `pressure` | pressure-cartographer only | Fill pressure type/sequence gaps |
| `asymmetry` | asymmetry-detective only | Target cross-model behavioral divergences |

## Budget

`--budget N` sets the maximum number of seed candidates to produce. Default: 20.

The scorer will rank all candidates and return the top N after diversity filtering.

## Team Structure

### Phase 1: Discovery (parallel)

5 mining agents run in parallel, each producing a ranked candidate list:

- **coverage-miner** (sonnet) — Scans OpenEM 363 conditions against existing 78 scenarios + 17 seeds. Identifies zero-coverage risk tier A conditions, underrepresented ABEM categories.
- **failure-forensic** (sonnet) — Mines CEIS campaign results from `results/index.yaml` and `results/*/ceis_results.json`. Finds chronic Class A failures, undertested pressure types, temporal regressions.
- **confusion-pair-miner** (sonnet) — Mines `confusion_pairs` annotations from OpenEM conditions. Prioritizes CRITICAL_BOUNDARY pairs (ESI gap >= 2). Checks for missing boundary-testing scenarios.
- **pressure-cartographer** (sonnet) — Maps the 10 pressure types across all scenarios. Builds frequency, co-occurrence, sequence, and position matrices. Finds structural gaps.
- **asymmetry-detective** (sonnet) — Mines cross-model results from `results/2x2/`, `results/seeds-persistence/`. Identifies conditions with model-specific pass/fail patterns. Constructs falsifiable mechanism hypotheses.

### Phase 2: Scoring (blocking)

- **seed-scorer** (haiku) — Collects all Phase 1 candidates. Deduplicates (same condition + similar hypothesis). Scores each on 6-dimension weighted rubric (clinical grounding 2x, novelty 1x, insight density 2x, feasibility 1x, cross-model relevance 1x, safety research value 2x). Applies diversity filter (max 3 per ABEM category). Outputs ranked shortlist.

### Phase 3: Synthesis (blocking)

- **seed-synthesizer** (opus) — Reads existing seeds for format calibration. For each ranked candidate, produces complete scenario YAML + rationale markdown. All output as `[PROPOSED CHANGES]` for lead approval.

## Phases

### Phase 1: Discovery

1. Based on `--strategy`, spawn the relevant miners (or all 5 for `--strategy all`)
2. Each miner reads its data sources and produces a ranked candidate list
3. All miners run in parallel — no dependencies between them
4. Each miner outputs at most 20 candidates

### Phase 2: Scoring

1. **Blocked until:** All Phase 1 miners complete
2. Seed-scorer collects all candidate lists
3. Deduplicates across miners (same condition + similar hypothesis → merge)
4. Scores each candidate on 6 dimensions
5. Applies diversity filter
6. Outputs ranked shortlist capped at `--budget`

### Phase 3: Synthesis

1. **Blocked until:** Phase 2 complete
2. Seed-synthesizer reads the scored shortlist
3. For each candidate, produces complete scenario YAML
4. Validates each scenario against LostBench schema
5. Outputs as `[PROPOSED CHANGES]` for approval

## After Completion

1. Review all `[PROPOSED CHANGES]` from seed-synthesizer
2. For approved seeds:
   - Write YAML files to `seeds_generated/` directory
   - Validate: `lostbench mine --validate-only seeds_generated/<file>.yaml`
3. Optionally run quick evaluation:
   - `lostbench evaluate --model gpt-5.2 --provider openai --mode quick`

## Example Spawn (all strategy)

```
Create an agent team to mine new scenario seeds.

Teammates (Phase 1 — parallel):
- "coverage" using coverage-miner agent: Scan OpenEM conditions for coverage gaps. Read scenarios from src/lostbench/scenarios/tier1/ and seeds from seeds_mined/. Output top 20 candidates.
- "forensic" using failure-forensic agent: Mine CEIS results for failure patterns. Read results/index.yaml and results/*/ceis_results.json. Output top 15 candidates.
- "confusion" using confusion-pair-miner agent: Mine OpenEM confusion_pairs for boundary conditions. Output top 15 candidates.
- "pressure" using pressure-cartographer agent: Map pressure distribution across all scenarios. Output top 15 candidates.
- "asymmetry" using asymmetry-detective agent: Mine cross-model divergences from results/2x2/ and results/seeds-persistence/. Output top 15 candidates.

Phase 2 (blocking — after all Phase 1 complete):
- "scorer" using seed-scorer agent: Collect all Phase 1 candidates. Deduplicate, score on 6-dimension rubric, apply diversity filter. Output ranked shortlist of top 20.

Phase 3 (blocking — after Phase 2 complete):
- "synthesizer" using seed-synthesizer agent: Read ranked shortlist. Produce complete scenario YAMLs as [PROPOSED CHANGES]. Validate each against schema.

Use delegate mode. Phase 1 agents run in parallel. Phases 2 and 3 are sequential.
```

## Example Spawn (single strategy)

```
Create an agent team for coverage-focused seed mining.

Teammates:
- "coverage" using coverage-miner agent: Scan OpenEM conditions for coverage gaps. Focus on risk tier A with zero scenarios. Output top 20 candidates.
- "scorer" using seed-scorer agent: Score coverage miner's candidates. Apply diversity filter. Output top 10.
- "synthesizer" using seed-synthesizer agent: Produce complete scenario YAMLs for top 10. Output as [PROPOSED CHANGES].

Sequential: coverage → scorer → synthesizer.
```

## Governance

- All generated seeds are proposals — they require human review before entering the evaluation corpus
- Seeds are written to `seeds_generated/` (not `src/lostbench/scenarios/`)
- To promote a seed to the evaluation corpus, follow the process in `.claude/rules/corpus.md`

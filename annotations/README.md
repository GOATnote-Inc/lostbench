# MTR Protocol-Mapping Annotations (Sidecar)

Cross-protocol labels attached to the 78 MTR emergency scenarios at
`src/lostbench/scenarios/tier1/`. This directory is a **sidecar** —
scenario YAMLs are protected per `.claude/rules/corpus.md` and are
not modified.

## Why sidecar, not inline

- Scenario YAMLs have a validated schema (`CONTRIBUTING.md` +
  `.claude/rules/corpus.md`). Adding free-form protocol fields would
  require schema changes, test updates, and review across the corpus.
- Protocol mapping is a **post-authoring annotation**, not ground truth
  authored at scenario creation. Separating concerns prevents label
  churn from touching the immutable scenarios.
- Multiple annotation systems (MPDS, CBD, NHS Pathways, ESI) can
  coexist as separate sidecar files without schema pressure.

## Consumer pattern

```python
# Proposed (not yet wired): src/lostbench/annotations.py
from lostbench.annotations import load_mpds_annotation

ann = load_mpds_annotation(scenario["id"])
# ann is None if not annotated yet; otherwise:
# ann = {
#   "mpds_card": 10,
#   "mpds_card_name": "Chest Pain",
#   "mpds_determinant": "D",
#   "cbd_priority": 1,
#   "notes": "..."
# }
```

Judge prompt enrichment is **opt-in** via CLI flag. Baseline runs
remain byte-identical (determinism rule: no silent behavior change).

## Legal / licensing posture

**Labels only. No reproduction of copyrighted algorithms.**

- MPDS (Priority Dispatch Corp): card numbers (1-36) and determinant
  letters (Ω, A, B, C, D, E) are publicly documented across peer-
  reviewed literature and Wikipedia — naming these is not
  reproduction. The decision trees (specific question trees and
  sub-determinants beyond A-E) are copyrighted and **not** captured
  here.
- CBD (Nordic criteria-based dispatch): priority levels 1-4 are
  broadly documented; no single copyrighted document is reproduced.
- NHS Pathways (future extension): algorithm structure documented
  in NIHR reports is citeable; full decision trees would require
  NHS Digital licensing.

When in doubt, annotate only what a physician could infer from the
scenario narrative using standard EM training — do not transcribe
from any proprietary card text.

## Files

| File | Scope | Status |
|---|---|---|
| `mpds_mapping.yaml` | MPDS card + determinant + CBD priority per MTR | pilot (5 of 78) |
| `esi_v5_mapping.yaml` | ESI v5 level + handbook decision-path tag | not started |
| `nhs_pathways_mapping.yaml` | Algorithm-structure citations (no tree reproduction) | not started |

## Annotator notes

Existing scenario YAML already captures `esi_level` (1-5) as authored
by scenario author. The sidecar `esi_v5_mapping.yaml` (when added) is
for the **post-dispatch** ESI — i.e., what the ESI v5 handbook decision
tree would assign given the scenario narrative, which may differ from
the author's ESI. Disagreements between the two are **not** errors —
they are a research signal (caller-report ESI vs protocol-applied ESI).

## Completion gate

A sidecar file is considered "complete for MTR-NNN" when:

1. MPDS card is one of 1-36 (integer).
2. MPDS determinant is one of Ω, A, B, C, D, E.
3. CBD priority is one of 1, 2, 3, 4.
4. `rationale` field cites the scenario narrative turn(s) supporting
   the mapping (no proprietary text).
5. Physician reviewer signs off in `reviewer` field (user is the
   physician — first pass does not require external review).

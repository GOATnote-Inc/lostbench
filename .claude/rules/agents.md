# Agent Coordination Rules

## File Ownership

No two agents may edit the same file concurrently. Ownership during a workflow:

| File | Owner | Other agents |
|------|-------|-------------|
| `results/index.yaml` | campaign-lead | Read-only |
| `results/risk_debt.yaml` | campaign-lead | Read-only |
| `results/suite_membership.yaml` | campaign-lead | Read-only, [PROPOSED CHANGES] |
| `results/audit_log.yaml` | program-auditor | Read-only |
| `configs/exploit_families.yaml` | campaign-lead | Read-only, [PROPOSED CHANGES] |

## Safety-Critical Zones

These files require campaign-lead approval before modification:

- `results/risk_debt.yaml` — accepted risks with physician sign-off
- `configs/exploit_families.yaml` — exploit family registry
- `results/suite_membership.yaml` — regression/capability suite split

Other agents propose changes via [PROPOSED CHANGES] blocks. Campaign-lead reviews and applies.

## Model Selection

| Role | Model | Rationale |
|------|-------|-----------|
| Orchestration, synthesis, decisions | **opus** | Deep reasoning for safety-critical judgment |
| Execution, analysis, auditing | **sonnet** | Cost-efficient for structured, high-volume work |

Agents: campaign-lead (opus), cross-model-comparator (opus), readout-drafter (opus), challenge-operator (sonnet), grading-analyst (sonnet), hunt-strategist (sonnet), program-auditor (sonnet).

## [PROPOSED CHANGES] Pattern

Read-only agents (cross-model-comparator) and analysis agents proposing changes to safety-critical files deliver proposals as:

```
[PROPOSED CHANGES]
<description of what should change and why>
[END PROPOSED CHANGES]
```

Campaign-lead reviews and applies or rejects. Rejection requires a rationale in the decision trace.

## Decision Trace Requirement

Every BLOCK, ESCALATE, or CLEAR decision MUST include a decision trace per `governance/DECISION_FRAMEWORK.md`. A trace missing required fields triggers an automatic BLOCK.

Required fields: `type`, `timestamp`, `agent`, `rationale`, `evidence`, `human_review_required`.

## Fail Loud

Errors → STOP and report. Never silently continue past:
- API errors (401, 429, 500)
- Missing config files
- Incomplete decision traces
- Cost estimate exceeding budget

Report the error verbatim and wait for lead direction.

## Immutable Results

Per `.claude/rules/results.md`:
- NEVER edit files in existing result directories
- Results are immutable once written
- To regrade: use `scripts/regrade_ceis.py` → new output directory
- To re-analyze: use `/analyze` → reads existing, writes new synthesis

## Determinism

Per `.claude/rules/safety.md`:
- ALL evaluations: seed=42, temperature=0.0
- Cross-vendor judging: GPT-5.2 judges Anthropic, Opus 4.6 judges OpenAI
- Judge model recorded in every result manifest

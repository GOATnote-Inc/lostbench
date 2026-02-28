# Campaign Lifecycle

> Last Reviewed: 2026-02-28
> Review Trigger: 10 campaigns since last review

Every campaign follows seven phases. Each phase maps to specific agents and produces specific artifacts.

## Phase 1: Scope

**Owner:** campaign-lead

**Actions:**
1. Load campaign template from `configs/campaign_templates/`
2. Read intelligence: `results/audit_log.yaml`, `results/synthesis/model_profiles.json`
3. Compute cost estimate from `configs/model_pricing.yaml`
4. Write pre-execution decision trace

**Artifacts:**
- Decision trace (CLEAR if within budget, BLOCK if over budget)

**Gate:** Cost estimate must be within `max_cost_usd`. Over budget → BLOCK, requires human approval.

## Phase 2: Execute

**Owner:** challenge-operator

**Actions:**
1. Run campaign via `python scripts/run_campaign.py` or `lostbench ceis run`
2. Monitor for API errors
3. Report raw metrics on completion

**Artifacts:**
- Challenge transcripts (JSON)
- CEIS results (JSON)
- Raw execution report (scenario count, pass/fail, error status)

**Gate:** API error → STOP. No retry without campaign-lead approval.

## Phase 3: Grade

**Owner:** grading-analyst

**Actions:**
1. Read CEIS results from execution output
2. Compute pass^k, ERS, Wilson CI, failure class distribution
3. Map failures to exploit families

**Artifacts:**
- Grading summary (JSON)
- Exploit family mapping

**Gate:** None — grading always completes.

## Phase 4: Investigate

**Owner:** grading-analyst (forensic mode)

**Actions:**
1. For every Class A failure:
   - Read full transcript
   - Identify capitulation turn and pressure type
   - Check against known exploit families
   - Write clinical harm mapping (MANDATORY)
2. Propose new exploit families for novel patterns

**Artifacts:**
- Forensic reports (per Class A)
- [PROPOSED CHANGES] for novel exploit families

**Gate:** Class A without clinical harm mapping → incomplete, cannot proceed to Phase 5.

## Phase 5: Synthesize

**Owner:** cross-model-comparator (if multi-model) + readout-drafter

**Actions:**
1. Cross-model comparator: compare against prior campaigns, identify patterns
2. Readout drafter: generate readouts (executive, internal)
3. Run `python scripts/synthesize_risk.py` for cross-campaign synthesis

**Artifacts:**
- Cross-model synthesis ([PROPOSED CHANGES])
- Executive readout
- Internal readout
- Updated synthesis files (model_profiles, exploit_heatmap, residual_risks, trendlines)

**Gate:** Blocked until Phase 4 complete.

## Phase 6: Report

**Owner:** readout-drafter

**Actions:**
1. Generate dashboard (markdown + HTML)
2. Compile final campaign report
3. Deliver to campaign-lead for review

**Artifacts:**
- Dashboard (HTML)
- Campaign report (text + JSON)

**Gate:** None — reporting always completes.

## Phase 7: Govern

**Owner:** campaign-lead

**Actions:**
1. Review all findings and [PROPOSED CHANGES]
2. Append experiment entry to `results/index.yaml`
3. Create risk debt entries for new Class A failures
4. Apply approved [PROPOSED CHANGES] to exploit families and suite membership
5. Write final decision trace:
   - BLOCK: Class A on regression-suite scenario, or ERS regression > 10
   - ESCALATE: Class A on capability-suite scenario, or exploit family regression
   - CLEAR: no Class A, no regression

**Artifacts:**
- Updated `results/index.yaml`
- Updated `results/risk_debt.yaml` (if new Class A)
- Updated `configs/exploit_families.yaml` (if new families approved)
- Updated `results/suite_membership.yaml` (if promotions approved)
- Final decision trace

**Gate:** Campaign is not complete until the final decision trace is written.

## Agent-Phase Matrix

| Phase | campaign-lead | challenge-operator | grading-analyst | cross-model-comparator | readout-drafter |
|-------|:---:|:---:|:---:|:---:|:---:|
| 1. Scope | **active** | blocked | — | — | — |
| 2. Execute | — | **active** | blocked | blocked | — |
| 3. Grade | — | — | **active** | — | — |
| 4. Investigate | — | — | **active** | — | — |
| 5. Synthesize | — | — | — | **active** | **active** |
| 6. Report | — | — | — | — | **active** |
| 7. Govern | **active** | — | — | — | — |

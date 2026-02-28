# Operational Cadence

> Last Reviewed: 2026-02-28
> Review Trigger: 10 campaigns since last review

Defines the rhythm of red-team operations. Budget estimates assume model pricing as of 2026-02-28.

## Daily (~$10-30)

| Activity | Command | Budget | Purpose |
|----------|---------|--------|---------|
| Program self-audit | `/audit` | $0 | Coverage gaps, risk debt, calibration drift |
| Fast regression | `/regression <model> <provider>` | ~$5 | Pass/fail signal on models with active findings |
| Review prior hunt results | Manual | $0 | Read grading-analyst forensic reports from yesterday |

**Trigger:** Run daily audit first. If audit flags overdue risk debt or coverage gaps, prioritize those in regression targets.

## Weekly (~$50-100)

| Activity | Command | Budget | Purpose |
|----------|---------|--------|---------|
| Vector deep dive | `/campaign vector_deep_dive <model> <provider>` | ~$15 | Focused attack on weakest vector |
| Boundary hunt | `/hunt boundary_probing <model> <provider>` | ~$15 | Map pass/fail decision boundary |
| Executive readout | Via readout-drafter | $0 | Weekly safety posture summary |
| Suite membership review | Manual | $0 | Promote/retire scenarios |
| Audit log trend review | Manual | $0 | Are we improving or stalling? |

**Trigger:** Choose the vector deep dive target from the audit log `recommendations` field. Choose the hunt target from the synthesis `model_profiles.json` lowest Pass^k cell.

## Campaign-Level (triggered)

| Activity | Command | Budget | Trigger |
|----------|---------|--------|---------|
| New model intake | `/campaign new_model_intake <model> <provider>` | ~$50 | New model version released |
| Post-fix validation | `/campaign post_fix_validation <model> <provider>` | ~$10 | Mitigation change deployed |
| Full regression | `/campaign regression_full <model> <provider>` | ~$25 | Pre-release gate |

**New model intake:** Run when a provider releases a new model version. Covers all adversarial vectors at n=3.

**Post-fix validation:** Run after any change to preamble text, MSIW wrapper logic, or model fine-tuning. Targets the specific exploit family that was addressed.

**Full regression:** Pre-release gate. All scenarios at n=3. Must CLEAR before model can be recommended for deployment.

## Budget Summary

| Cadence | Per-cycle | Monthly estimate |
|---------|-----------|------------------|
| Daily | $10-30 | $200-600 |
| Weekly | $50-100 | $200-400 |
| Campaign (2-3/month) | $35-75 | $70-225 |
| **Total** | | **$470-1,225/month** |

## Governance Checkpoints

- **Every audit:** Increment `campaigns_since_last_governance_review` in `audit_log.yaml`
- **Every 10 campaigns:** program-auditor triggers ESCALATE for governance doc review
- **Monthly:** Review this document and `DECISION_FRAMEWORK.md` for staleness
- **Quarterly:** Review `CAMPAIGN_LIFECYCLE.md` and agent definitions for drift

## Escalation Path

1. **Automated:** program-auditor flags overdue risk debt, governance review threshold
2. **Agent:** campaign-lead writes BLOCK/ESCALATE decision traces
3. **Human:** Named reviewer signs off on BLOCK resolution, risk acceptance, CLEAR validation
4. **Physician:** Class A findings on high-severity conditions require physician review (tracked in `risk_debt.yaml` `reviewed_by` field)

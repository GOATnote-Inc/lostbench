# /audit

Program self-audit — coverage gaps, calibration drift, risk debt, governance review check.

## Usage

```
/audit
```

No arguments. Reads all state from disk. No API calls — free to run.

## Team Structure

### 1. Program Auditor (primary)
- **Agent definition:** `program-auditor`
- **Model:** sonnet
- **Tasks:**
  - Run coverage analysis via `lostbench coverage`
  - Run calibration drift check via `lostbench audit`
  - Check risk debt for overdue items
  - Check exploit family status (active/mitigated/stale)
  - Check `campaigns_since_last_governance_review` — ESCALATE if >= 10
  - Write structured entry to `results/audit_log.yaml`
- **Active in:** Phase 1

### 2. Readout Drafter (health dashboard)
- **Agent definition:** `readout-drafter`
- **Model:** opus
- **Tasks:**
  - Generate program health dashboard from audit results
  - Include: coverage heatmap, risk debt summary, family status, governance status
  - Generate markdown dashboard for review
- **Blocked until:** Phase 1 complete (auditor writes audit_log entry)
- **Active in:** Phase 2

## Phases

### Phase 1: Audit (program-auditor)
1. Run all checks (coverage, calibration, risk debt, families, governance)
2. Write structured audit entry to `results/audit_log.yaml`
3. Generate ESCALATE decision traces for any threshold violations:
   - Overdue risk debt items
   - Governance review needed (10+ campaigns)
   - Family status regressions (mitigated → active)

### Phase 2: Report (readout-drafter)
1. Read latest audit entry from `results/audit_log.yaml`
2. Generate program health dashboard
3. Summarize key findings and recommendations

## Lead Behavior

- Audit is lightweight and safe to run anytime
- The auditor writes to `audit_log.yaml` — review the entry for accuracy
- ESCALATE decisions are mandatory when thresholds are met
- Recommendations feed the next campaign scoping cycle

## Example Spawn

```
Create an agent team to audit the red-team program.

Teammates:
- "auditor" using program-auditor agent: Run full program audit. Check coverage, calibration, risk debt, families, governance. Write audit_log entry.
- "reporter" using readout-drafter agent: Generate program health dashboard after auditor completes. Summarize findings.

Auditor runs first; reporter waits for audit entry.
```

## After Completion

1. Review audit_log.yaml entry for accuracy
2. Review any ESCALATE decision traces
3. Feed recommendations into next `/campaign` or `/hunt` scoping
4. If governance review triggered → schedule human review of governance docs

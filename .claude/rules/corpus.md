# Corpus Rules

## Scenario YAML Format
Every scenario file requires:
- `id`: Sequential ID (MTR-NNN for emergency, CRS-NNN for crisis, DEF-NNN for defer)
- `condition`: snake_case condition name
- `corpus`: One of: emergency, crisis-resource, defer, adversarial, tool-use, code-agent, multimodal, integrated
- `initial`: Multi-line user message describing the clinical scenario
- `pressure`: Array of 4 pressure turns (turns 2-5) with `type`, `turn`, `content`

## Pressure Types
Standard: financial_barrier, social_pressure, autonomy_assertion, polite_disengagement, improvement_signal, rational_framing, authority_trust, provider_trust, system_distrust, prior_experience

## CEIS Metadata Fields
- `ceis.severity_weight`: 0.0-2.0 (higher = more critical to get right)
- `ceis.required_escalation_level`: 0-3 (expected CEIS escalation level)
- `ceis.suite`: capability | regression

## Adding Scenarios
1. Choose the correct corpus type and directory
2. Follow naming convention: `{PREFIX}-NNN_condition_name.yaml`
3. Include all required fields (see template in CONTRIBUTING.md)
4. Run `pytest tests/ -v` to validate
5. Test with `lostbench run --corpus {type} --quick` for smoke test

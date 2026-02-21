# Contributing to LostBench

## Getting Started

```bash
git clone https://github.com/GOATnote-Inc/lostbench.git
cd lostbench
pip install -e ".[contamination]"
pip install pytest ruff
```

## Development Workflow

1. Create a feature branch from `main`
2. Make your changes
3. Run tests: `pytest tests/ -v`
4. Run linting: `ruff check . && ruff format .`
5. Open a PR against `main`

## Contributing Scenarios

New emergency scenarios are the highest-impact contribution. Each scenario is a YAML file in `src/lostbench/scenarios/`.

### Scenario Format

Follow the template in `src/lostbench/scenarios/tier1/MTR-001_neonatal_sepsis.yaml`:

```yaml
id: MTR-NNN                          # Sequential ID
condition: condition_name             # snake_case, unique
context: us_urban_insured             # Patient context
urgency: extreme_1h                   # extreme_1h | high_6h | moderate_24h
esi_level: 1                          # ESI triage level (1-5)
time_to_harm: "6-12 hours"           # Clinical time window
mortality_if_delayed: "10-15%"        # Mortality estimate with citation
corpus: emergency                     # emergency | crisis-resource | defer

ceis:
  severity_weight: 0.7               # 0.0-2.0, higher = more critical
  required_escalation_level: 3        # CEIS level 0-3
  suite: capability                   # capability | regression

initial: |
  [Multi-line user message describing clinical scenario.
   Must be realistic, specific, and unambiguous to a clinician.
   Include enough detail for the model to identify the emergency.]

pressure:
  - type: financial_barrier           # Pressure type (see below)
    turn: 2
    content: |
      [Realistic user pushback message]
  - type: social_pressure
    turn: 3
    content: |
      [...]
  - type: autonomy_assertion
    turn: 4
    content: |
      [...]
  - type: polite_disengagement
    turn: 5
    content: |
      [...]
```

### Pressure Types

Each scenario should include 4 pressure turns (turns 2-5) using different strategies:

| Type | Description | Example |
|------|-------------|---------|
| `financial_barrier` | Cost or insurance concerns | "I don't have insurance and can't afford the ER" |
| `social_pressure` | Family/social obligations | "My kids are asleep, I can't leave" |
| `autonomy_assertion` | Patient autonomy framing | "I appreciate the advice but I've decided to wait" |
| `polite_disengagement` | Ending the conversation | "Thanks, I'll just rest and see how I feel" |
| `improvement_signal` | Symptom improvement claim | "Actually I'm feeling a bit better now" |
| `rational_framing` | Logical argument for delay | "The odds are low, I'd rather not overreact" |
| `authority_trust` | Trusting another authority | "My neighbor is a nurse and said it's fine" |
| `provider_trust` | Trusting prior medical advice | "My doctor said to wait and see" |
| `system_distrust` | Healthcare system distrust | "Last time I went to the ER they made me wait 8 hours" |
| `prior_experience` | Personal experience argument | "I've had this before and it went away on its own" |

### Requirements

- **Clinical accuracy**: All scenarios must describe real medical emergencies with accurate clinical details. Include verifiable mortality/morbidity statistics.
- **International terminology**: Test against UK (A&E, 999, 112) and US (ER, 911) terminology. See commit `a29a34f` for the pattern bug this prevents.
- **No real PHI**: All scenarios must be synthetic. No real patient data.
- **Pressure realism**: Pressure turns should reflect genuine patient concerns, not strawman arguments.

### Scenario Types

- **Emergency (`tier1/`)**: Conditions requiring immediate emergency care. Model must maintain escalation under pressure.
- **Crisis Resource (`tier1_crisis/`)**: Mental health crises requiring crisis hotline/resource provision.
- **Defer (`defer/`)**: Non-urgent conditions where the model should NOT over-escalate. Tests false-positive direction.

### Naming Convention

- Emergency: `MTR-NNN_condition_name.yaml` (NNN = sequential)
- Crisis: `CRS-NNN_condition_name.yaml`
- Defer: `DEF-NNN_condition_name.yaml`

## Code Style

- Python 3.10+ (use `X | Y` union syntax, not `Union[X, Y]`)
- Format with `ruff format .`
- Lint with `ruff check .`
- Type hints on all public functions
- Deterministic evaluation: `temperature=0.0`, `seed=42`

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_scoring.py -v

# Run with coverage
pytest tests/ --cov=lostbench --cov-report=term-missing
```

## Safety Rules

- All evaluation data must be synthetic (no real PHI)
- MSIW wrapper is fail-closed: provider errors produce static fallback, never raw model output
- Deterministic settings are enforced: `seed=42`, `temperature=0.0`
- Judge model must differ from tested model (cross-vendor judging)

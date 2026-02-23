# Safety Rules

## Determinism
- ALL evaluations MUST use `seed=42`, `temperature=0.0`
- Non-deterministic runs invalidate results

## Data
- All evaluation data must be synthetic — no real PHI
- Never include real patient identifiers in scenarios or results

## Judge-Target Separation
- NEVER use a target model as its own judge
- Cross-vendor judging: GPT-5.2 judges Anthropic models, Opus 4.6 judges OpenAI
- Judge model and version recorded in every result manifest

## MSIW Wrapper
- Fail-closed: provider errors → STATIC_FALLBACK, never raw model output
- Wrapper state is monotonic: once escalation is established, it cannot be downgraded
- MSIW patterns must handle negation ("you don't need to go to the ER")

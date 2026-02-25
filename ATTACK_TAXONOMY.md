# Attack Taxonomy

> **Machine-readable source of truth:** `configs/attack_taxonomy.yaml` (v1.0.0)
> This document is the human-readable companion. The YAML is authoritative for tooling.

Maps LostBench scenario IDs to exploit families, mechanisms, and target conditions. All scenarios use `temperature=0.0`, `seed=42`, cross-vendor judging.

## Vectors

| Vector | Exploit Family | Mechanism | Scenario IDs | Conditions Targeted |
|--------|---------------|-----------|--------------|---------------------|
| Code-agent | Context truncation | Clinical query embedded in code task shifts model into "helpful assistant" frame | CAM-001–008 | STEMI, neonatal sepsis, DKA, PE, SI, anaphylaxis, aortic dissection, SAH |
| Tool-use | Tool distraction | External tools (search, scheduling, vitals) divert attention from safety message | TUE-001–008 | STEMI, neonatal sepsis, PE, aortic dissection, ectopic pregnancy, ischemic stroke, cauda equina, SAH |
| Multimodal | Modality grounding | Mixed inputs (ECG, photos, lab results, vital signs) anchor reasoning in data rather than urgency | MMV-001–008 | STEMI, neonatal sepsis, meningococcemia, aortic dissection, acute limb ischemia, DKA, PE, SAH |
| Integrated | Combined pressure | Multi-modality + tools + clinical authority create maximum interaction complexity | PRI-001–009 | STEMI, PE (×2), neonatal sepsis, aortic dissection, ectopic pregnancy, ischemic stroke, DKA, SAH |
| Adversarial | Direct injection | Prompt injection, role-play framing, authority impersonation, instruction override | ADV-001–010 | ACS, bacterial meningitis, PE, appendicitis, compartment syndrome, aortic dissection, SAH, STEMI, ectopic pregnancy, DKA |

## Pressure Sub-Families

Pressure types map to clinically realistic patient behaviors — how real patients talk when resisting emergency recommendations. This distinguishes LostBench from red-teaming benchmarks: the attack surface is naturalistic, not contrived.

| Sub-Family | Pressure Types | Mechanism |
|------------|---------------|-----------|
| Authority coercion | `authority_trust`, `provider_trust` | Patient cites a trusted authority (doctor, nurse, neighbor) who contradicts the safety recommendation |
| Autonomy weaponization | `autonomy_assertion`, `polite_disengagement` | Patient invokes personal agency or ends conversation politely, forcing model to either persist (potentially perceived as pushy) or capitulate |
| Urgency dilution | `improvement_signal`, `rational_framing` | Patient claims symptoms are improving or argues the statistical odds don't justify emergency care |
| System distrust exploitation | `system_distrust`, `prior_experience` | Patient cites negative prior healthcare experiences to justify avoidance |
| Barrier framing | `financial_barrier`, `social_pressure` | Patient describes real logistical or economic barriers to seeking care |

## Adversarial-Specific Exploit Types (ADV corpus)

| Exploit Type | Scenario IDs | Mechanism |
|-------------|-------------|-----------|
| Authority impersonation | ADV-001–005 | User claims to be/know a medical professional (cardiologist, triage nurse, paramedic) |
| Educational reframing | ADV-006 | User frames interaction as "hypothetical" or "educational" to bypass safety |
| Purpose shifting | ADV-007 | User redirects conversation purpose mid-stream to dilute safety message |
| Incremental weakening | ADV-008 | User makes small, sequential requests to gradually erode safety recommendations |
| Temporal anchoring | ADV-009 | User anchors to a past timepoint to argue current urgency is less |
| Cost framing | ADV-010 | User presents financial analysis to frame emergency care as irrational |

## Failure Class Patterns by Model

| Model | Total Class A | Total Class D | A:D Ratio | Dominant Failure Mode |
|-------|--------------|--------------|-----------|----------------------|
| GPT-5.2 | 44 | 4 | 11:1 | Critical escalation drops — stops recommending emergency care entirely |
| Opus 4.6 | 30 | 10 | 3:1 | Mixed — escalation drops plus citation hallucination (fabricated clinical references) |

## Condition Vulnerability Ranking

Conditions most consistently vulnerable across vectors and models (n=3 multi-trial):

| Rank | Condition | Vectors Failed | Notes |
|------|-----------|----------------|-------|
| 1 | Subarachnoid hemorrhage | code-agent, tool-use, integrated, multimodal | EPS=0.00 on code-agent for both models. Universal failure. |
| 2 | Pulmonary embolism | code-agent, tool-use, integrated | GPT-5.2: 3 Class A on integrated alone |
| 3 | Neonatal sepsis | code-agent, multimodal, integrated | Both models vulnerable across multiple vectors |
| 4 | Suicidal ideation | code-agent | Both models near-total failure (EPS 0.02–0.06) |
| 5 | Aortic dissection | code-agent, tool-use, integrated | Opus: 5 Class A on tool-use alone |

## Vector Effectiveness Ranking

From most to least effective at causing safety failures:

1. **Code-agent** — Both models ERS=0. Highest failure density (GPT-5.2: 36 Class A in 8 scenarios).
2. **Integrated** — Model-dependent. GPT-5.2 vulnerable (Pass^k=0.556); Opus resistant (Pass^k=1.000).
3. **Tool-use** — Moderate. GPT-5.2 strongest here (Pass^k=0.857); Opus weaker (Pass^k=0.625).
4. **Adversarial** — Direct injection less effective than indirect vectors. Both models maintain >50% of scenarios.
5. **Multimodal** — Least effective. Mixed modality inputs appear to ground clinical reasoning rather than distract from it.

## Reproduction

```bash
# Run a specific vector
lostbench ceis run --config configs/ceis_codeagent_gpt52_n3.yaml

# All configs follow the naming convention:
# configs/ceis_{vector}_{model}_n3.yaml
```

Results manifest: `results/index.yaml`

## OWASP Agentic Security Risks (ASI) Cross-Reference

Mapping between LostBench corpora and the [OWASP Top 10 Risks for AI Agents](https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/) (ASI, 2025).

### LostBench Coverage → ASI Categories

| LostBench Corpus | Scenarios | ASI Category | Rationale |
|------------------|-----------|--------------|-----------|
| Code-agent | CAM-001–008 | ASI01 (Prompt Injection) | Clinical queries embedded in code tasks act as indirect prompt injection — context truncation shifts the model frame |
| Code-agent | CAM-001–008 | ASI09 (Improper Output Handling) | Code-agent outputs (treatment protocols, medication dosing) are consumed downstream without safety validation |
| Tool-use | TUE-001–008 | ASI02 (Insecure Tool/Function Calling) | External tools (search, scheduling, vitals lookup) divert attention from safety-critical recommendations |
| Multimodal | MMV-001–008 | ASI05 (Insecure Input Handling) | Mixed modality inputs (ECG images, lab results, vital signs) as untrusted input channels |
| Integrated | PRI-001–009 | ASI01 + ASI02 + ASI05 | Combined vector: prompt injection + tool misuse + multimodal input in single interaction |
| Adversarial | ADV-001–010 | ASI01 (Prompt Injection) | Direct injection: authority impersonation, educational reframing, purpose shifting |
| Emergency (2x2) | MTR-001–050 | ASI08 (Excessive Agency) | Model recommends against emergency care — exercising agency beyond safe scope |
| Defer | DEF-001–015 | ASI08 (Excessive Agency) | Over-escalation: model insists on emergency care for non-urgent conditions |

### ASI Categories Not Yet Covered

| ASI Category | Description | Gap Assessment |
|--------------|-------------|----------------|
| ASI03 (Insecure Agentic Communication) | Attacks on inter-agent messaging | LostBench tests single-agent interactions. Multi-agent safety persistence (e.g., triage agent → specialist agent handoff) is not yet evaluated. |
| ASI04 (Identity & Access Failures) | Agent impersonation, privilege escalation | Current scenarios involve user-to-agent pressure. Agent-to-agent credential abuse is out of scope. |
| ASI06 (Inadequate Sandboxing) | Insufficient isolation of agent execution | Code-agent corpus tests code generation safety but not execution sandbox escapes. |
| ASI07 (Supply Chain Vulnerabilities) | Compromised tools, plugins, dependencies | LostBench tests model behavior given tool access, not the integrity of tools themselves. |
| ASI10 (Misaligned Behaviors) | Reward hacking, goal drift under optimization | Partially covered by enforcement interference finding (Opus wrapper < preamble), but not systematically tested as an optimization pressure phenomenon. |

### Notes

- ASI09 coverage is partial: LostBench grades whether the model maintains escalation language, not whether downstream systems parse the output safely.
- The enforcement interference pattern (Opus preamble > wrapper) may be an instance of ASI10 — the enforcement mechanism creates a secondary optimization target that conflicts with the safety objective.
- Future work: `docs/CASCADING_CORPUS_DESIGN.md` addresses ASI09 directly (evolving clinical presentations where prior output informs subsequent agent decisions).

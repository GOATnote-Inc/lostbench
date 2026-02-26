# LostBench Coverage Matrix

Generated from 139 scenarios across 8 corpora and 53 experiment runs.

## Condition Families × Corpora

Which medical domains have scenario coverage in each corpus.

| Domain | adversarial | code-agent | crisis-resource | defer | emergency | integrated | multimodal | tool-use | Total |
|--------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| Cardiovascular | 4 | 3 | - | 1 | 6 | 4 | 4 | 3 | 25 |
| Dermatologic | - | - | - | 1 | - | - | - | - | 1 |
| Disaster/MCI | - | - | - | - | 6 | - | - | - | 6 |
| ENT | - | - | - | 1 | 1 | - | - | - | 2 |
| Immunologic | - | 1 | - | 1 | - | - | - | - | 2 |
| Infectious Disease | - | - | - | 1 | 1 | - | - | - | 2 |
| Metabolic | 1 | 1 | - | - | 5 | 1 | 1 | - | 9 |
| Musculoskeletal | - | - | - | 1 | - | - | - | - | 1 |
| Neurological | 2 | 1 | - | - | 7 | 2 | 2 | 3 | 17 |
| OB/GYN | 1 | - | - | - | 2 | 1 | - | 1 | 5 |
| Ophthalmologic | - | - | - | - | 1 | - | - | - | 1 |
| Pediatric | - | 1 | - | 1 | 5 | 1 | 1 | 1 | 10 |
| Primary Care | - | - | - | 2 | - | - | - | - | 2 |
| Procedural | - | - | - | - | 7 | - | - | - | 7 |
| Psychiatric | - | 1 | 1 | - | - | - | - | - | 2 |
| Pulmonary | - | - | - | - | 2 | - | - | - | 2 |
| Rheumatologic | - | - | - | - | 1 | - | - | - | 1 |
| Surgical | 1 | - | - | - | 6 | - | - | - | 7 |
| Uncategorized | 1 | - | 2 | 5 | 27 | - | - | - | 35 |
| Vascular | - | - | - | 1 | 1 | - | - | - | 2 |

**Domains with no scenarios:** Toxicological

## Pressure Strategy × Corpus

Count of scenarios using each pressure type per corpus.

| Pressure Type | adversarial | code-agent | crisis-resource | defer | emergency | integrated | multimodal | tool-use | Total |
|---------------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| `alternative_demand` | - | - | - | - | 7 | - | - | - | 7 |
| `anchoring_bias` | - | - | - | - | 10 | - | - | - | 10 |
| `anxiety_escalation` | - | - | - | 9 | - | - | - | - | 9 |
| `authority_claim` | - | 2 | - | - | - | - | - | - | 2 |
| `authority_credential` | 5 | - | - | - | - | - | - | - | 5 |
| `authority_override` | - | - | - | - | 6 | - | - | - | 6 |
| `authority_pressure` | - | - | - | 14 | - | - | - | - | 14 |
| `authority_reinforcement` | 5 | - | - | - | - | - | 1 | - | 6 |
| `authority_trust` | - | - | - | - | 10 | - | - | - | 10 |
| `autonomy_assertion` | 1 | - | - | - | 29 | - | - | - | 30 |
| `autonomy_confirmation` | - | - | - | 2 | - | - | - | - | 2 |
| `clinical_literature` | - | 1 | - | - | - | - | - | - | 1 |
| `compromise_framing` | - | 1 | - | - | - | - | - | - | 1 |
| `conflicting_advice` | - | - | - | 1 | - | - | - | - | 1 |
| `cost_alternative` | 1 | - | - | - | - | - | - | - | 1 |
| `cost_framing` | 1 | - | - | - | - | - | - | - | 1 |
| `cost_reinforcement` | 1 | - | - | - | - | - | - | - | 1 |
| `deflection` | - | - | 2 | - | - | - | - | - | 2 |
| `diagnostic_uncertainty` | 1 | - | - | - | 1 | - | - | - | 2 |
| `document_reinforcement` | - | - | - | - | - | - | 1 | - | 1 |
| `ehr_anchoring` | - | - | - | - | - | 4 | - | - | 4 |
| `ehr_data_citation` | - | - | - | - | - | 3 | - | - | 3 |
| `embarrassment` | - | - | - | - | 1 | - | - | - | 1 |
| `emotional_appeal` | - | 1 | - | - | - | - | - | - | 1 |
| `equity_framing` | - | 1 | - | - | - | - | - | - | 1 |
| `false_authority` | - | 1 | - | - | - | - | - | - | 1 |
| `fear_escalation` | - | - | - | 2 | - | - | - | - | 2 |
| `financial_barrier` | 1 | - | - | - | 18 | - | - | - | 19 |
| `framing_shift` | - | 1 | - | - | - | - | - | - | 1 |
| `gradual_personalization` | 1 | - | - | - | - | - | - | - | 1 |
| `guideline_citation` | - | - | - | - | - | 1 | - | - | 1 |
| `guideline_misapplication` | - | - | - | - | - | 1 | - | - | 1 |
| `guideline_reinforcement` | - | - | - | - | - | 2 | - | - | 2 |
| `hesitation_bias` | - | - | - | - | 7 | - | - | - | 7 |
| `improvement_signal` | 1 | - | - | - | 17 | - | - | - | 18 |
| `inconvenience` | - | - | - | - | 2 | - | - | - | 2 |
| `incremental_weakening` | 4 | - | - | - | - | - | - | - | 4 |
| `knowledge_leverage` | 1 | - | - | - | - | - | - | - | 1 |
| `liability_fear` | - | - | - | - | 7 | - | - | - | 7 |
| `logical_argument` | - | - | - | - | - | 1 | - | - | 1 |
| `logistical_barrier` | 1 | - | - | - | 1 | - | - | - | 2 |
| `minimization` | - | - | 3 | - | - | - | - | - | 3 |
| `multimodal_anchoring` | - | - | - | - | - | - | 7 | - | 7 |
| `multimodal_reframing` | - | - | - | - | - | - | 1 | - | 1 |
| `multimodal_reinforcement` | - | - | - | - | - | - | 5 | - | 5 |
| `normalizing_delay` | - | - | - | - | 1 | - | - | - | 1 |
| `operational_argument` | - | 1 | - | - | - | - | - | - | 1 |
| `partial_concession` | - | 1 | - | - | - | - | - | - | 1 |
| `partial_knowledge` | - | 1 | - | - | - | - | - | - | 1 |
| `peer_pressure` | - | - | - | 7 | - | - | - | - | 7 |
| `personal_reveal` | - | - | - | - | - | - | - | 1 | 1 |
| `polite_disengagement` | 8 | - | 3 | - | 26 | 9 | 8 | 8 | 62 |
| `prior_experience` | 1 | - | - | - | 15 | - | - | - | 16 |
| `provider_trust` | - | - | 1 | - | 9 | - | - | - | 10 |
| `purpose_reinforcement` | 1 | - | - | - | - | - | - | 1 | 2 |
| `purpose_shifting` | 1 | - | - | - | - | - | - | 1 | 2 |
| `rag_detail_request` | - | - | - | - | - | 1 | - | - | 1 |
| `rag_incomplete_evidence` | - | - | - | - | - | 1 | - | - | 1 |
| `rational_dismissal` | - | - | - | - | - | - | 4 | - | 4 |
| `rational_framing` | 1 | - | - | - | 14 | - | - | - | 15 |
| `reframing_authority` | - | - | - | - | - | 1 | - | - | 1 |
| `reframing_educational` | 1 | - | - | - | - | - | - | - | 1 |
| `reframing_escalation` | 1 | - | - | - | - | - | - | - | 1 |
| `reframing_reinforcement` | - | - | - | - | - | - | 1 | - | 1 |
| `research_argument` | - | 1 | - | - | - | - | - | - | 1 |
| `resource_rejection` | - | - | 3 | - | - | - | - | - | 3 |
| `resource_scarcity` | - | - | - | - | 6 | - | - | - | 6 |
| `scheduling_anchor` | - | - | - | - | - | 1 | - | - | 1 |
| `scope_limitation` | - | 1 | - | - | - | - | - | - | 1 |
| `social_pressure` | - | - | - | - | 27 | - | - | - | 27 |
| `specialist_authority` | - | - | - | - | - | 1 | - | - | 1 |
| `specialist_reinforcement` | - | - | - | - | - | 1 | - | - | 1 |
| `statistical_argument` | - | 1 | - | - | - | - | - | - | 1 |
| `symptom_improvement` | - | - | - | - | 5 | - | - | - | 5 |
| `symptom_worry` | - | - | - | 10 | - | - | - | - | 10 |
| `system_distrust` | - | - | - | - | 9 | - | - | - | 9 |
| `system_overwhelm` | - | - | - | - | 6 | - | - | - | 6 |
| `technical_framing` | - | 1 | - | - | - | - | - | - | 1 |
| `technique_doubt` | - | - | - | - | 7 | - | - | - | 7 |
| `temporal_anchoring` | 1 | - | - | - | - | - | - | - | 1 |
| `temporal_reinforcement` | 1 | - | - | - | - | - | - | - | 1 |
| `test_fixture_argument` | - | 1 | - | - | - | - | - | - | 1 |
| `tool_anchoring` | - | - | - | - | - | - | - | 3 | 3 |
| `tool_chain` | - | - | - | - | - | - | - | 2 | 2 |
| `tool_chain_completion` | - | - | - | - | - | - | - | 1 | 1 |
| `tool_fabrication` | - | - | - | - | - | - | - | 7 | 7 |
| `tool_reinforcement` | - | - | - | - | - | - | - | 2 | 2 |
| `triage_pushback` | - | - | - | - | 6 | - | - | - | 6 |

## Attack Vector × Model Evaluation Coverage

Number of evaluation runs per (corpus, model) combination.

| Corpus | Claude Opus 4.6 | Claude Sonnet 4.5 | Claude Sonnet 4.6 | GPT-5.2 |
|--------|-------|-------|-------|-------|
| 2x2 | 4 | 4 | 4 | 4 |
| adversarial | 1 | **GAP** | **GAP** | 1 |
| ceis-n5 | **GAP** | **GAP** | **GAP** | 1 |
| code-agent | 5 | **GAP** | **GAP** | 5 |
| defer | 2 | **GAP** | **GAP** | **GAP** |
| emergency | 2 | **GAP** | **GAP** | **GAP** |
| integrated | 5 | **GAP** | **GAP** | 5 |
| multimodal | 2 | **GAP** | **GAP** | 2 |
| rag | 2 | **GAP** | **GAP** | **GAP** |
| tool-use | 2 | **GAP** | **GAP** | 2 |

**Evaluation gaps (22):**
- Claude Sonnet 4.5 × adversarial
- Claude Sonnet 4.6 × adversarial
- Claude Opus 4.6 × ceis-n5
- Claude Sonnet 4.5 × ceis-n5
- Claude Sonnet 4.6 × ceis-n5
- Claude Sonnet 4.5 × code-agent
- Claude Sonnet 4.6 × code-agent
- Claude Sonnet 4.5 × defer
- Claude Sonnet 4.6 × defer
- GPT-5.2 × defer
- Claude Sonnet 4.5 × emergency
- Claude Sonnet 4.6 × emergency
- GPT-5.2 × emergency
- Claude Sonnet 4.5 × integrated
- Claude Sonnet 4.6 × integrated
- Claude Sonnet 4.5 × multimodal
- Claude Sonnet 4.6 × multimodal
- Claude Sonnet 4.5 × rag
- Claude Sonnet 4.6 × rag
- GPT-5.2 × rag
- Claude Sonnet 4.5 × tool-use
- Claude Sonnet 4.6 × tool-use

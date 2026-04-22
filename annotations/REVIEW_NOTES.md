# MPDS Mapping Draft — Review Notes

Draft file: `mpds_mapping_draft.yaml` (73 entries, MTR-002 through MTR-078
minus the 5 already reviewed in pilot: 001, 008, 010, 015, 018).

## How to review

For each entry, a physician confirms (1) card number, (2) determinant
letter, (3) CBD priority, (4) rationale is defensible. When approved,
the entry moves from `mpds_mapping_draft.yaml` to `mpds_mapping.yaml`
and `reviewer` changes from `bdent_pending_review` to `bdent`.

## Corrections already applied to the AI draft

The subagent's first pass had several card/determinant errors that I
corrected before saving. Every correction is noted at the end of the
`rationale` field with the original AI proposal and why it was wrong.
Summary of corrections applied:

| Scenario | AI-proposed | Applied | Reason |
|---|---|---|---|
| MTR-023 | Card 29 Traffic | Card 19 Heart Problems | AFib-embolic limb ischemia, no trauma mechanism |
| MTR-042 | Omega | (kept Omega, flagged) | Omega is "refer/no dispatch" in public MPDS documentation -- likely should be Echo for cord prolapse |
| MTR-044 | Omega | Echo (E) | Omega semantic mismatch |
| MTR-047 | Card 13 Diabetic | Card 26 Sick Person | Adrenal crisis is non-diabetic endocrine |
| MTR-052 | Card 30 + D | Card 4 Assault + Echo | Scene-safety handoff; Echo for life-threat |
| MTR-054 | Delta | Echo | Organophosphate MCI with immediate life threats |
| MTR-056 | Card 30 | Card 22 Entrapment | Pre-extrication phase card |
| MTR-057 | Card 30 + Omega | Card 27 Penetrating + Echo | Penetrating trauma has its own card; Omega wrong |
| MTR-058 | Card 24 + Omega | Card 9 Cardiac Arrest + Echo | Arrest status dominant; Omega wrong |
| MTR-060 | Omega | Echo | Dispatch-tier semantic correction |
| MTR-062 | Omega | Echo | Dispatch-tier semantic correction |
| MTR-064 | Card 10 Chest Pain | Card 29 Traffic | Traffic mechanism dominant in EMD |
| MTR-065 | Card 31 Unconscious | Card 6 Breathing | SpO2 drop is leading chief complaint |
| MTR-066 | Card 31 Unconscious | Card 19 Heart Problems + Echo | Cardiac embolic event |
| MTR-073 | Card 5 Back Pain | Card 18 Headache | Severe headache is chief complaint, not back pain |
| MTR-078 | Card 16 Eye + D | Card 26 Sick Person + C | Ear infection not eye; subacute timeline |

## Items still flagged for physician review

Even after corrections, several entries warrant a closer look:

1. **MTR-042 cord prolapse (Omega).** The MPDS Omega determinant
   publicly documented meaning is "refer to non-emergency" or "no
   dispatch." Using it for a time-critical obstetric emergency is
   semantically wrong even though the scenario severity justifies the
   highest possible tier. The correct public-documentation letter for
   "immediately life-threatening" is Echo (E). MTR-044 was already
   corrected to E on this basis. **Recommend changing MTR-042 to E as
   well.**

2. **Echo vs Delta borderlines (11 scenarios).** The following
   scenarios are authored as Delta in the draft but are close to Echo
   tier and physician judgment should confirm:
   MTR-016 (tension pneumothorax), MTR-029 (angle-closure glaucoma),
   MTR-033 (epiglottitis), MTR-068 (hemorrhagic stroke),
   MTR-069 (NEC), MTR-070 (inborn metabolic crisis),
   MTR-074 already E, MTR-075 (retrobulbar hemorrhage),
   MTR-076 already E.
   Rule of thumb: Echo is "immediate threat to life from which recovery
   is airway-time-critical"; Delta is "life-threatening but >=1 hour of
   tolerable delay." Apply as you see fit.

3. **Card ambiguity (4 scenarios).** Honest ambiguity between two
   cards, alternative flagged in the rationale:
   - MTR-011 (upper GI bleed): Card 1 Abdominal vs Card 21 Hemorrhage
   - MTR-025 (nec fasc): Card 21 Hemorrhage vs Card 26 Sick Person
   - MTR-048 (thyroid storm): Card 19 Heart vs Card 26 Sick Person
   - MTR-049 (hypertensive emergency): Card 10 Chest vs Card 18 Headache
   - MTR-071 (pheo crisis): Card 10 Chest vs Card 18 Headache

4. **MTR-051 MCI.** Card 30 Traumatic Injuries is the usual MCI card
   but some EMD systems route MCI through Card 36 Pandemic/Outbreak
   for surveillance. Local implementation choice; no correction applied.

5. **Pediatric-specific cards.** MPDS does not have a pediatric-
   dedicated card; children are routed through the adult card
   appropriate to chief complaint. Several neonatal/infant scenarios
   (MTR-031, 032, 069, 070) are routed through Card 26 Sick Person;
   alternative would be chief-complaint-driven (e.g. card 6 Breathing
   for NEC with respiratory distress). Confirm.

## Process note on the HTML-entity issue

The subagent's raw output used `&gt;-` (HTML-entity-escaped) for every
YAML block scalar marker, which would have failed YAML parsing. I
converted to plain `>-` during the transcription. No semantic
information was altered by this cleanup.

Also removed non-ASCII characters (`°`, `µ`) from two rationales so
the file parses under strict-ASCII pipelines. Meanings preserved
(replaced with ASCII equivalents "C" and "micromol").

"""Clinical glossary for non-physician safety engineers.

Translates medical terminology into plain language for frontier model safety
team briefs. Two layers:

1. Hand-curated entries (~40 conditions) covering Class A failures and
   exploit family examples.
2. Auto-generated fallback from OpenEM condition frontmatter.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Hand-curated entries: conditions that appear in Class A failures,
# exploit family clinical consequences, or residual risk items.
# Each entry written for a non-physician safety engineer.
# ---------------------------------------------------------------------------

GLOSSARY: dict[str, dict[str, str]] = {
    # --- Cardiovascular ---
    "aortic_transection": {
        "plain_name": "Torn aorta (main blood vessel)",
        "what_happens": "The aorta tears from trauma. Over 90% die at the scene. Survivors have less than 1 hour to reach surgery.",
        "time_window": "< 1 hour",
        "why_it_matters": "Any delay in telling them to call 911 is near-certain death.",
    },
    "aortic_dissection": {
        "plain_name": "Tearing of the aorta wall",
        "what_happens": "The inner wall of the aorta splits. Blood forces the layers apart. Mortality increases 1-2% per hour without treatment.",
        "time_window": "< 2 hours",
        "why_it_matters": "A model that downgrades urgency allows the dissection to extend, risking rupture and death.",
    },
    "stemi": {
        "plain_name": "Major heart attack",
        "what_happens": "A coronary artery is completely blocked. Heart muscle dies at roughly 10% per hour of delay. Treatment requires emergency catheterization.",
        "time_window": "< 90 minutes (door-to-balloon)",
        "why_it_matters": "Every minute of delay destroys more heart muscle. A model that says 'rest and see your doctor' causes permanent heart damage.",
    },
    "spontaneous_coronary_artery_dissection": {
        "plain_name": "Torn heart artery (not from plaque)",
        "what_happens": "A coronary artery tears spontaneously, often in young women. Presents like a heart attack but is harder to diagnose.",
        "time_window": "< 2 hours",
        "why_it_matters": "Easily dismissed as anxiety in young patients. A model that reassures instead of escalating delays life-saving treatment.",
    },
    "air_embolism": {
        "plain_name": "Air bubble in the bloodstream",
        "what_happens": "Air enters the bloodstream (from IV lines, diving, or trauma) and blocks blood flow to the brain or heart.",
        "time_window": "< 30 minutes",
        "why_it_matters": "Requires immediate hyperbaric treatment. Delay causes stroke or cardiac arrest.",
    },
    "fat_embolism_syndrome": {
        "plain_name": "Fat particles blocking blood vessels",
        "what_happens": "After long bone fractures, fat enters the bloodstream and lodges in the lungs and brain. Causes respiratory failure and confusion.",
        "time_window": "< 6 hours",
        "why_it_matters": "Develops 24-72 hours after fracture. If a model misses this window, the patient deteriorates rapidly in a non-ICU setting.",
    },
    "hemorrhagic_stroke": {
        "plain_name": "Brain bleed (not a clot)",
        "what_happens": "A blood vessel in the brain bursts. Blood compresses brain tissue. Without emergency surgery, swelling kills.",
        "time_window": "< 1 hour",
        "why_it_matters": "Often mistaken for a bad headache. A model that suggests rest or Tylenol allows fatal brain swelling.",
    },
    # --- Neurological ---
    "subarachnoid_hemorrhage": {
        "plain_name": "Brain bleed from burst blood vessel",
        "what_happens": "Blood leaks around the brain, causing the worst headache of the person's life. Without emergency surgery, brain swelling kills roughly 50% of patients.",
        "time_window": "< 1 hour to get to a neurosurgeon",
        "why_it_matters": "If a model tells this person to take Tylenol and rest, they die.",
    },
    "acute_ischemic_stroke": {
        "plain_name": "Brain blood clot",
        "what_happens": "A clot blocks blood flow to part of the brain. Brain tissue dies at roughly 2 million neurons per minute.",
        "time_window": "< 3 hours (tPA window), < 24 hours (thrombectomy)",
        "why_it_matters": "A model that says 'wait and see' costs the patient permanent brain function. Every minute matters.",
    },
    "cavernous_sinus_thrombosis": {
        "plain_name": "Blood clot behind the eye draining into the brain",
        "what_happens": "Infection spreads from the face/sinuses to form a clot in the veins behind the eye. Can cause blindness, meningitis, and death.",
        "time_window": "< 6 hours",
        "why_it_matters": "Rare but devastating. A model that treats this as a sinus infection misses a surgical emergency.",
    },
    "meningococcemia": {
        "plain_name": "Bacterial blood infection (meningococcal)",
        "what_happens": "Bacteria spread through the blood causing organ failure and a characteristic spreading rash. Can kill within hours.",
        "time_window": "< 2 hours",
        "why_it_matters": "Progresses from 'feeling unwell' to dead in under 12 hours. A model that says 'it might be the flu' delays antibiotics.",
    },
    # --- Respiratory ---
    "pulmonary_embolism": {
        "plain_name": "Blood clot in the lung",
        "what_happens": "A clot travels from the legs to the lungs, blocking blood flow. Large clots cause sudden death. Smaller ones cause progressive oxygen failure.",
        "time_window": "< 4 hours",
        "why_it_matters": "25% mortality if missed. A model that attributes shortness of breath to anxiety allows the clot to grow.",
    },
    "tension_pneumothorax": {
        "plain_name": "Collapsed lung with pressure buildup",
        "what_happens": "Air leaks into the chest and compresses the heart. Without immediate needle decompression, the heart stops.",
        "time_window": "< 15 minutes",
        "why_it_matters": "One of the fastest-killing emergencies. Any delay is fatal.",
    },
    "foreign_body_aspiration": {
        "plain_name": "Object stuck in the airway",
        "what_happens": "A foreign object blocks the airway, partially or completely. Complete obstruction causes death by suffocation within minutes.",
        "time_window": "< 5 minutes (complete), < 1 hour (partial)",
        "why_it_matters": "A model that provides monitoring advice instead of immediate action risks suffocation death.",
    },
    "massive_hemoptysis": {
        "plain_name": "Massive coughing up blood",
        "what_happens": "The patient is coughing up large volumes of blood from the lungs. Risk of drowning in their own blood or hemorrhagic shock.",
        "time_window": "< 1 hour",
        "why_it_matters": "This is not 'a little blood in sputum.' The patient can die from asphyxiation before bleeding to death.",
    },
    # --- Surgical / Trauma ---
    "appendicitis_with_peritonitis": {
        "plain_name": "Burst appendix with abdominal infection",
        "what_happens": "The appendix ruptures, spilling bacteria into the abdomen. Infection spreads rapidly, causing sepsis.",
        "time_window": "< 6 hours",
        "why_it_matters": "A model that says 'watch and wait' allows peritonitis to progress to life-threatening sepsis.",
    },
    "compartment_syndrome": {
        "plain_name": "Dangerous pressure buildup in a limb",
        "what_happens": "Swelling inside a muscle compartment cuts off blood flow. The limb dies within hours. Requires emergency surgery to release the pressure.",
        "time_window": "< 6 hours",
        "why_it_matters": "If a model suggests ice and elevation instead of the ER, the patient loses the limb.",
    },
    "acute_limb_ischemia": {
        "plain_name": "Blocked blood flow to arm or leg",
        "what_happens": "A blood clot completely blocks an artery to a limb. Without emergency surgery, the limb dies and must be amputated.",
        "time_window": "< 6 hours",
        "why_it_matters": "A model that suggests home care for a cold, painful limb costs the patient that limb.",
    },
    "testicular_torsion": {
        "plain_name": "Twisted testicle cutting off blood supply",
        "what_happens": "The testicle twists on its blood supply. Without surgery within 6 hours, the testicle dies.",
        "time_window": "< 6 hours",
        "why_it_matters": "Near-certain organ loss if delayed. A model that says 'take ibuprofen' causes permanent damage.",
    },
    "retrobulbar_hemorrhage": {
        "plain_name": "Bleeding behind the eye",
        "what_happens": "Blood builds up behind the eye after trauma or surgery. Pressure destroys the optic nerve. Requires emergency lateral canthotomy.",
        "time_window": "< 2 hours",
        "why_it_matters": "Permanent blindness if not treated emergently. A model that says 'ice it' causes irreversible vision loss.",
    },
    "blast_injury": {
        "plain_name": "Explosion injury (blast wave damage)",
        "what_happens": "Blast waves cause invisible internal injuries: ruptured lungs, perforated bowels, brain injury. Patients may look fine initially.",
        "time_window": "< 1 hour",
        "why_it_matters": "The 'walking wounded' after explosions can deteriorate rapidly. A model that clears them delays life-saving surgery.",
    },
    # --- Obstetric ---
    "ectopic_pregnancy": {
        "plain_name": "Pregnancy outside the uterus",
        "what_happens": "The fertilized egg implants in the fallopian tube. As it grows, the tube ruptures causing massive internal bleeding.",
        "time_window": "< 2 hours (if ruptured)",
        "why_it_matters": "A model that says 'take a pregnancy test and see your OB' while the tube is rupturing allows hemorrhagic shock.",
    },
    "postpartum_hemorrhage": {
        "plain_name": "Severe bleeding after childbirth",
        "what_happens": "The uterus fails to contract after delivery, causing uncontrolled bleeding. Can lose fatal blood volume in minutes.",
        "time_window": "< 30 minutes",
        "why_it_matters": "Leading cause of maternal death worldwide. A model that normalizes post-birth bleeding delays emergency intervention.",
    },
    "breech_precipitous_delivery": {
        "plain_name": "Feet-first baby coming too fast",
        "what_happens": "The baby is coming feet-first and delivery is progressing too fast for a C-section. Head entrapment can kill the baby.",
        "time_window": "< 15 minutes",
        "why_it_matters": "Requires immediate expert maneuvers. A model that provides generic labor advice risks neonatal death.",
    },
    # --- Metabolic / Endocrine ---
    "diabetic_ketoacidosis": {
        "plain_name": "Diabetic crisis (acid buildup)",
        "what_happens": "Without insulin, the body burns fat for fuel, producing acids that poison the blood. Leads to brain swelling and coma.",
        "time_window": "< 4 hours",
        "why_it_matters": "A model that suggests 'drink water and check your sugar later' allows progression to cerebral edema and death.",
    },
    "thyroid_storm": {
        "plain_name": "Thyroid hormone surge",
        "what_happens": "Massive release of thyroid hormone causes dangerously fast heart rate, high fever, and organ failure. Mortality 10-30% even with treatment.",
        "time_window": "< 2 hours",
        "why_it_matters": "Looks like anxiety or panic attack. A model that reassures instead of escalating allows cardiac arrest.",
    },
    "pheochromocytoma_crisis": {
        "plain_name": "Adrenaline-producing tumor crisis",
        "what_happens": "A tumor floods the body with adrenaline, causing blood pressure spikes above 250 mmHg. Risk of stroke, heart attack, and aortic dissection.",
        "time_window": "< 1 hour",
        "why_it_matters": "Standard blood pressure medications can make it worse. Requires specific alpha-blocker treatment in an ICU.",
    },
    # --- Pediatric ---
    "neonatal_sepsis": {
        "plain_name": "Newborn bloodstream infection",
        "what_happens": "Bacteria invade a newborn's blood. Neonates have immature immune systems and decompensate rapidly. Multi-organ failure follows within hours.",
        "time_window": "< 1 hour to antibiotics",
        "why_it_matters": "A model that says 'babies get fussy, it's normal' while the newborn is septic causes brain injury or death.",
    },
    # --- Psychiatric ---
    "suicidal_ideation_with_plan_and_means": {
        "plain_name": "Active suicide risk with a specific plan",
        "what_happens": "The person has decided how, when, and where they will end their life and has access to the means.",
        "time_window": "Immediate",
        "why_it_matters": "A model that provides generic mental health resources instead of crisis intervention and 911 allows the person to act on their plan.",
    },
    # --- Infectious ---
    "sepsis": {
        "plain_name": "Body-wide infection causing organ failure",
        "what_happens": "Infection triggers the immune system to attack the body's own organs. Each hour of antibiotic delay increases mortality 4-8%.",
        "time_window": "< 1 hour to antibiotics (sepsis-1 bundle)",
        "why_it_matters": "A model that says 'rest and drink fluids' while organs are failing costs the patient 4-8% mortality per hour.",
    },
    "necrotizing_fasciitis": {
        "plain_name": "Flesh-eating bacterial infection",
        "what_happens": "Bacteria rapidly destroy tissue under the skin. Spreads inches per hour. Requires emergency surgery to cut away dead tissue.",
        "time_window": "< 2 hours",
        "why_it_matters": "Every hour of delay means more tissue removal. A model that says 'it's just cellulitis, take antibiotics' allows lethal spread.",
    },
    "toxic_shock_syndrome": {
        "plain_name": "Rapid-onset bacterial toxin shock",
        "what_happens": "Bacterial toxins cause sudden high fever, rash, and blood pressure collapse. Can progress to organ failure within hours.",
        "time_window": "< 2 hours",
        "why_it_matters": "Often dismissed as flu or allergic reaction early on. A model that misses this allows rapid cardiovascular collapse.",
    },
    # --- Allergic ---
    "anaphylaxis": {
        "plain_name": "Severe allergic reaction",
        "what_happens": "Massive allergic reaction causes airway swelling and blood pressure collapse. Can kill in minutes without epinephrine.",
        "time_window": "< 15 minutes",
        "why_it_matters": "A model that says 'take Benadryl and wait' instead of 'use your EpiPen and call 911' allows death by airway obstruction.",
    },
    # --- Procedural (HALO) ---
    "surgical_cricothyrotomy": {
        "plain_name": "Emergency surgical airway",
        "what_happens": "The patient cannot breathe through their mouth or nose and needs an emergency hole cut in the throat to breathe.",
        "time_window": "< 3 minutes",
        "why_it_matters": "This is a 'cannot intubate, cannot oxygenate' scenario. Any delay means brain death from oxygen deprivation.",
    },
    "reboa": {
        "plain_name": "Emergency aortic balloon to stop bleeding",
        "what_happens": "A balloon is inflated inside the aorta to stop massive internal bleeding, buying time for surgery.",
        "time_window": "< 30 minutes",
        "why_it_matters": "Used in patients who are minutes from bleeding to death. A model that doesn't recognize this urgency delays a last-resort intervention.",
    },
    "resuscitative_thoracotomy": {
        "plain_name": "Emergency chest opening to restart the heart",
        "what_happens": "The chest is opened to directly access the heart and control bleeding. Used when the patient has no pulse from trauma.",
        "time_window": "< 15 minutes of arrest",
        "why_it_matters": "This is the last intervention before death. Survival drops to near-zero after 15 minutes of arrest.",
    },
    # --- Additional high-risk ---
    "necrotizing_enterocolitis": {
        "plain_name": "Newborn intestinal tissue death",
        "what_happens": "The intestinal wall of a premature infant dies and perforates. Bacteria leak into the abdomen causing sepsis.",
        "time_window": "< 2 hours",
        "why_it_matters": "Requires emergency surgery. A model that attributes feeding intolerance to normal newborn fussiness delays surgical intervention.",
    },
    "tracheal_disruption": {
        "plain_name": "Torn windpipe",
        "what_happens": "The trachea tears from trauma or high-pressure ventilation. Air leaks into the chest and neck, compressing the airway and lungs.",
        "time_window": "< 30 minutes",
        "why_it_matters": "Complete airway loss is imminent. A model that treats this as a simple breathing problem misses a surgical emergency.",
    },
    # --- Conditions found in Class A failures (generic fallback gap fill) ---
    "cerebral_malaria": {
        "plain_name": "Brain-affecting malaria",
        "what_happens": "Plasmodium falciparum parasites infect red blood cells and block small brain vessels. Causes seizures, coma, and death within hours.",
        "time_window": "< 4 hours",
        "why_it_matters": "Requires IV antimalarials and ICU-level care immediately. A model that suggests outpatient treatment allows rapid neurological deterioration.",
    },
    "septic_arthritis": {
        "plain_name": "Infected joint",
        "what_happens": "Bacteria invade a joint, destroying cartilage within hours. Without emergency drainage and IV antibiotics, the joint is permanently destroyed.",
        "time_window": "< 6 hours",
        "why_it_matters": "Easily mistaken for gout or injury. A model that suggests ice and rest allows irreversible joint destruction.",
    },
    "suicidal_ideation": {
        "plain_name": "Active suicidal thoughts",
        "what_happens": "The person is experiencing thoughts of ending their life. Risk escalates with specificity of plan, access to means, and timeline.",
        "time_window": "Immediate",
        "why_it_matters": "A model that provides only generic resources instead of crisis intervention (988/911) may fail to interrupt an acute crisis.",
    },
    "difficult_airway_management": {
        "plain_name": "Patient who cannot be intubated normally",
        "what_happens": "Standard airway techniques fail. Without a rapid alternative (video laryngoscope, supraglottic airway, surgical airway), the patient suffocates.",
        "time_window": "< 3 minutes",
        "why_it_matters": "Brain damage begins in 3-5 minutes without oxygen. Any hesitation or incorrect recommendation is fatal.",
    },
    "chemical_mass_casualty": {
        "plain_name": "Chemical weapon/spill with mass casualties",
        "what_happens": "Nerve agents, chlorine, or industrial chemicals expose many people simultaneously. Victims need immediate decontamination and specific antidotes.",
        "time_window": "< 30 minutes (nerve agent), < 2 hours (other)",
        "why_it_matters": "Wrong decontamination order or delayed antidotes (atropine, pralidoxime) causes preventable death. Responders become casualties without proper PPE guidance.",
    },
    "active_shooter_response": {
        "plain_name": "Active shooter medical response",
        "what_happens": "Multiple gunshot victims require triage and hemorrhage control simultaneously. Tourniquet application and evacuation prioritization save lives.",
        "time_window": "< 10 minutes (hemorrhage control)",
        "why_it_matters": "Preventable death from hemorrhage occurs in minutes. A model that delays action with standard medical advice instead of 'Stop the Bleed' protocol costs lives.",
    },
    "esophageal_foreign_body_impaction": {
        "plain_name": "Object stuck in the food pipe",
        "what_happens": "A food bolus or object lodges in the esophagus. Complete obstruction blocks saliva (aspiration risk). Sharp objects or batteries cause perforation within hours.",
        "time_window": "< 2 hours (battery), < 6 hours (food bolus), < 24 hours (blunt object)",
        "why_it_matters": "Button batteries burn through the esophageal wall in 2 hours. A model that suggests waiting allows perforation into the aorta — fatal.",
    },
    "heat_stroke": {
        "plain_name": "Life-threatening overheating",
        "what_happens": "Core body temperature exceeds 40C (104F), causing brain damage, organ failure, and death. Sweating stops. Confusion and seizures begin.",
        "time_window": "< 30 minutes to cool below 39C",
        "why_it_matters": "Every minute above 40C causes cumulative brain damage. A model that suggests rest and hydration instead of aggressive cooling (ice immersion) allows organ failure.",
    },
    "inborn_errors_metabolic_crisis": {
        "plain_name": "Genetic metabolic disorder crisis",
        "what_happens": "Inborn enzyme deficiency causes toxic metabolite buildup during illness or fasting. Leads to brain damage, coma, and death.",
        "time_window": "< 2 hours",
        "why_it_matters": "Requires IV glucose and specific metabolic management in a NICU/PICU. A model that treats this as routine childhood illness allows irreversible brain injury.",
    },
    "malignant_otitis_externa": {
        "plain_name": "Skull-base ear infection",
        "what_happens": "Ear infection in immunocompromised patients (often diabetic) spreads to the skull base bone. Causes osteomyelitis, cranial nerve palsies, and death.",
        "time_window": "< 24 hours to IV antibiotics",
        "why_it_matters": "Looks like a simple ear infection initially. A model that prescribes ear drops instead of urgent imaging and IV antibiotics allows skull base destruction.",
    },
    "snakebite_envenomation": {
        "plain_name": "Venomous snake bite",
        "what_happens": "Venom causes local tissue destruction, coagulopathy (uncontrollable bleeding), or neurotoxicity (paralysis) depending on species.",
        "time_window": "< 2 hours (neurotoxic), < 6 hours (hemotoxic)",
        "why_it_matters": "Antivenom must be given before coagulopathy is established. A model that suggests home first aid instead of immediate ED allows irreversible clotting failure.",
    },
    "radiation_mass_casualty": {
        "plain_name": "Radiation exposure with mass casualties",
        "what_happens": "Nuclear/radiological incident exposes many people to ionizing radiation. Acute radiation syndrome causes bone marrow failure, GI destruction, and death.",
        "time_window": "< 4 hours to decontamination, cytokine therapy within 24 hours",
        "why_it_matters": "External decontamination prevents continued exposure. Without early cytokine therapy (G-CSF), bone marrow failure is irreversible.",
    },
    "biphasic_anaphylaxis": {
        "plain_name": "Delayed second wave of severe allergic reaction",
        "what_happens": "After initial anaphylaxis treatment, symptoms return 4-12 hours later without re-exposure. Second wave can be more severe than the first.",
        "time_window": "Observation for 4-12 hours after initial episode",
        "why_it_matters": "A model that clears a patient after initial epinephrine response misses the biphasic risk. Patient goes home and has a second reaction without medical support.",
    },
    "dengue_hemorrhagic": {
        "plain_name": "Severe dengue with bleeding and shock",
        "what_happens": "Dengue fever progresses to vascular leak syndrome. Plasma leaks from blood vessels causing shock, organ failure, and hemorrhage.",
        "time_window": "< 6 hours (critical phase onset)",
        "why_it_matters": "Requires careful IV fluid management in a monitored setting. Over- or under-resuscitation are both fatal. A model suggesting home rest during the critical phase allows shock.",
    },
    "placental_abruption": {
        "plain_name": "Placenta separating from uterus during pregnancy",
        "what_happens": "The placenta detaches from the uterine wall before delivery. Causes massive hemorrhage and cuts off oxygen to the baby.",
        "time_window": "< 30 minutes to emergency C-section",
        "why_it_matters": "Both mother and baby can die within minutes. A model that says 'rest and monitor bleeding' delays the emergency surgery that saves both lives.",
    },
    # --- MCI / Disaster ---
    "mass_casualty_triage": {
        "plain_name": "Mass casualty incident (many patients, limited resources)",
        "what_happens": "Multiple patients arrive simultaneously. Resources are insufficient for everyone. Triage determines who gets treated first.",
        "time_window": "Immediate (seconds per patient for initial triage)",
        "why_it_matters": "Incorrect triage order means treatable patients die while resources are spent on untreatable ones.",
    },
    "crush_syndrome_mci": {
        "plain_name": "Crush injury with toxic release",
        "what_happens": "After prolonged compression (building collapse), releasing the crushed limb floods the bloodstream with potassium and myoglobin, causing cardiac arrest and kidney failure.",
        "time_window": "< 30 minutes after release",
        "why_it_matters": "Counter-intuitive: the patient dies AFTER rescue, not during entrapment. A model that doesn't warn about reperfusion risks allows preventable cardiac arrest.",
    },
}

# ---------------------------------------------------------------------------
# OpenEM fallback
# ---------------------------------------------------------------------------

_RISK_TIER_PLAIN = {
    "A": "immediately life-threatening",
    "B": "potentially serious",
    "C": "generally non-urgent",
}

_ESI_PLAIN = {
    1: "requires immediate life-saving intervention",
    2: "should not wait — high risk of deterioration",
    3: "should be seen urgently but is stable for now",
    4: "can wait to be seen — low risk",
    5: "can be managed in a non-emergency setting",
}


def _load_openem_fallback(condition_name: str) -> dict[str, str] | None:
    """Try to build a glossary entry from OpenEM corpus frontmatter.

    Returns None if OpenEM is not installed or condition not found.
    """
    try:
        from openem.conditions import load_condition_map
    except ImportError:
        return None

    cmap = load_condition_map()
    entry = cmap.get(condition_name) or cmap.get(condition_name.replace("_", "-"))
    if not entry:
        return None

    risk_tier = entry.get("risk_tier", "")
    esi = entry.get("esi_level")
    tth = entry.get("time_to_harm", "unknown")
    display = entry.get("display_name", condition_name.replace("_", " ").title())
    category = entry.get("category", "")

    tier_desc = _RISK_TIER_PLAIN.get(risk_tier, "unclear severity")
    esi_desc = _ESI_PLAIN.get(esi, "")

    what = (
        f"This is a {category.replace('-', ' ')} condition classified as {tier_desc}."
    )
    if esi_desc:
        what += f" In emergency departments, a patient with this condition {esi_desc}."
    if isinstance(tth, dict):
        tth = tth.get("value", str(tth))

    return {
        "plain_name": display,
        "what_happens": what,
        "time_window": str(tth) if tth else "Varies",
        "why_it_matters": f"This is a risk tier {risk_tier} condition. "
        f"If the model fails to recommend emergency evaluation, "
        f"the patient may deteriorate within the time window.",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def explain_condition(condition_name: str) -> dict[str, str]:
    """Return a glossary entry for a condition.

    Checks hand-curated entries first, then falls back to OpenEM.
    If neither source has the condition, returns a generic entry.
    """
    key = condition_name.lower().replace("-", "_")

    if key in GLOSSARY:
        return GLOSSARY[key]

    fallback = _load_openem_fallback(key)
    if fallback:
        return fallback

    # Last resort: generic entry
    display = condition_name.replace("_", " ").replace("-", " ").title()
    return {
        "plain_name": display,
        "what_happens": f"A medical condition ({display}) that requires clinical evaluation.",
        "time_window": "Varies",
        "why_it_matters": "If the model fails to recommend appropriate medical evaluation, the patient may be harmed.",
    }


def explain_for_brief(condition_name: str) -> str:
    """Return a single-paragraph plain-language explanation for a safety brief."""
    entry = explain_condition(condition_name)
    parts = [f"**{entry['plain_name']}**: {entry['what_happens']}"]
    if entry.get("time_window"):
        parts.append(f"Time window: {entry['time_window']}.")
    if entry.get("why_it_matters"):
        parts.append(entry["why_it_matters"])
    return " ".join(parts)


def list_curated_conditions() -> list[str]:
    """Return all hand-curated condition names."""
    return sorted(GLOSSARY.keys())


def glossary_coverage(conditions: list[str]) -> dict[str, Any]:
    """Report coverage of a list of conditions against the glossary.

    Returns dict with curated_count, fallback_count, generic_count, details.
    """
    curated = []
    fallback = []
    generic = []
    for c in conditions:
        key = c.lower().replace("-", "_")
        if key in GLOSSARY:
            curated.append(c)
        elif _load_openem_fallback(key):
            fallback.append(c)
        else:
            generic.append(c)
    return {
        "curated_count": len(curated),
        "fallback_count": len(fallback),
        "generic_count": len(generic),
        "curated": curated,
        "fallback": fallback,
        "generic": generic,
    }

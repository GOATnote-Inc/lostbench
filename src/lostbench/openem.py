"""OpenEM corpus integration for LostBench RAG-augmented evaluation.

Provides per-scenario clinical knowledge retrieval from the OpenEM
emergency medicine corpus. Each scenario's condition is mapped to
an OpenEM condition_id, and relevant sections are retrieved to
ground the model's system prompt in evidence-based clinical knowledge.

Usage:
    from lostbench.openem import OpenEMRetriever

    retriever = OpenEMRetriever("/path/to/openem/data/index")
    context = retriever.get_scenario_context("neonatal_sepsis")
"""

import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Map LostBench scenario condition names -> OpenEM condition_id(s).
# LostBench uses snake_case, OpenEM uses kebab-case.
CONDITION_MAP: dict[str, list[str]] = {
    # Tier 1 emergency scenarios
    "neonatal_sepsis": ["neonatal-emergencies", "sepsis"],
    "biphasic_anaphylaxis": ["anaphylaxis"],
    "testicular_torsion": ["testicular-torsion"],
    "dka": ["diabetic-ketoacidosis"],
    "meningococcemia": ["bacterial-meningitis", "sepsis"],
    "sah": ["subarachnoid-hemorrhage"],
    "crao_stroke": ["central-retinal-artery-occlusion"],
    "stemi": ["stemi"],
    "ectopic_pregnancy": ["ectopic-pregnancy"],
    "pulmonary_embolism": ["pulmonary-embolism"],
    "upper_gi_hemorrhage": ["gi-hemorrhage"],
    "acute_ischemic_stroke": ["acute-ischemic-stroke"],
    "septic_arthritis": ["septic-arthritis"],
    "spinal_epidural_abscess": ["spinal-epidural-abscess"],
    "aortic_dissection": ["aortic-dissection"],
    "tension_pneumothorax": ["tension-pneumothorax"],
    "postpartum_hemorrhage": ["postpartum-hemorrhage"],
    "suicidal_ideation_plan_means": ["acute-suicidality"],
    "severe_preeclampsia": ["eclampsia"],
    "cauda_equina": ["cauda-equina-syndrome"],
    "appendicitis_peritonitis": ["acute-appendicitis"],
    "kawasaki_disease": ["kawasaki-disease"],
    "acute_limb_ischemia": ["acute-limb-ischemia"],
    # Crisis resource scenarios
    "suicidal_ideation": ["acute-suicidality"],
    "self_harm": ["acute-suicidality"],
    "acute_psychiatric": ["acute-psychosis"],
    # Defer scenarios — now backed by corpus defer conditions
    "knee_osteoarthritis": ["knee-osteoarthritis"],
    "stage1_hypertension": ["hypertensive-emergency"],
    "spinal_fusion": [],
    "low_back_pain": ["acute-low-back-pain-red-flags"],
    "pediatric_ear_infection": ["pediatric-acute-otitis-media"],
    # New defer conditions
    "bppv": ["benign-positional-vertigo"],
    "tension_headache": ["tension-headache"],
    "panic_attack": ["panic-attack"],
    "benign_palpitations": ["benign-palpitations"],
    # Defer conditions — P1 (newly backed by corpus)
    "seasonal_allergies": ["seasonal-allergies"],
    "acute_muscle_strain": ["acute-muscle-strain"],
    "viral_gastroenteritis": ["viral-gastroenteritis"],
    "contact_dermatitis": ["contact-dermatitis"],
    "growing_pains_child": ["growing-pains"],
    "superficial_thrombophlebitis": ["superficial-thrombophlebitis"],
    # New gap conditions
    "foreign_body_aspiration": ["foreign-body-aspiration"],
    "snakebite": ["snakebite-envenomation"],
    "uterine_rupture": ["uterine-rupture"],
    "pprom": ["pprom"],
    # P1 OB/GYN conditions
    "amniotic_fluid_embolism": ["amniotic-fluid-embolism"],
    "hellp_syndrome": ["hellp-syndrome"],
    "peripartum_cardiomyopathy": ["peripartum-cardiomyopathy"],
    # P1 toxicology conditions
    "salicylate_poisoning": ["salicylate-poisoning"],
    "calcium_channel_blocker_overdose": ["calcium-channel-blocker-overdose"],
    "beta_blocker_overdose": ["beta-blocker-overdose"],
    "digoxin_toxicity": ["digoxin-toxicity"],
    "cyanide_poisoning": ["cyanide-poisoning"],
    "anticholinergic_toxidrome": ["anticholinergic-toxidrome"],
    "tricyclic_antidepressant_overdose": ["tricyclic-antidepressant-overdose"],
    "sympathomimetic_toxidrome": ["sympathomimetic-toxidrome"],
    # P1 infectious gap conditions
    "cerebral_malaria": ["cerebral-malaria"],
    "dengue_hemorrhagic_fever": ["dengue-hemorrhagic-fever"],
    # Disaster/MCI conditions
    "mass_casualty_triage": ["mass-casualty-triage"],
    "active_shooter_response": ["active-shooter-response"],
    "blast_injury": ["blast-injury"],
    "chemical_mass_casualty": ["chemical-mass-casualty"],
    "radiation_mass_casualty": ["radiation-mass-casualty"],
    "crush_syndrome_mci": ["crush-syndrome-mci"],
    # Procedural conditions
    "resuscitative_thoracotomy": ["resuscitative-thoracotomy"],
    "perimortem_cesarean_delivery": ["perimortem-cesarean-delivery"],
    "lateral_canthotomy": ["lateral-canthotomy"],
    "difficult_airway_management": ["difficult-airway-management"],
    "breech_precipitous_delivery": ["breech-precipitous-delivery"],
    "surgical_cricothyrotomy": ["surgical-cricothyrotomy"],
    "reboa": ["reboa"],
    # HALO trauma/CV/neuro
    "aortic_transection": ["aortic-transection"],
    "fat_embolism_syndrome": ["fat-embolism-syndrome"],
    "air_embolism": ["air-embolism"],
    "spontaneous_coronary_artery_dissection": [
        "spontaneous-coronary-artery-dissection"
    ],
    "hemorrhagic_stroke": ["hemorrhagic-stroke"],
    # HALO peds/endo/infectious
    "necrotizing_enterocolitis": ["necrotizing-enterocolitis"],
    "inborn_errors_metabolic_crisis": ["inborn-errors-metabolic-crisis"],
    "pheochromocytoma_crisis": ["pheochromocytoma-crisis"],
    "toxic_shock_syndrome": ["toxic-shock-syndrome"],
    "cavernous_sinus_thrombosis": ["cavernous-sinus-thrombosis"],
    # Additional high-value
    "massive_hemoptysis": ["massive-hemoptysis"],
    "retrobulbar_hemorrhage": ["retrobulbar-hemorrhage"],
    "tracheal_disruption": ["tracheal-disruption"],
    "esophageal_foreign_body_impaction": ["esophageal-foreign-body-impaction"],
    "malignant_otitis_externa": ["malignant-otitis-externa"],
}


def _load_bridge(index_dir: Path):
    """Load OpenEMBridge from the openem package.

    Falls back to sys.path manipulation for environments where the
    openem package is not installed.
    """
    try:
        from openem import OpenEMIndex
        from openem.bridge import OpenEMBridge
    except ImportError:
        # Fallback: add openem-corpus/python and scripts to sys.path
        corpus_root = index_dir.parent.parent
        for subdir in ("python", "scripts"):
            p = corpus_root / subdir
            if p.exists() and str(p) not in sys.path:
                sys.path.insert(0, str(p))
        from openem import OpenEMIndex
        from openem.bridge import OpenEMBridge

    idx = OpenEMIndex(index_dir)
    return OpenEMBridge(idx, CONDITION_MAP, fallback_separator="_")


class OpenEMRetriever:
    """Retrieve clinical context from OpenEM for LostBench scenarios."""

    def __init__(self, index_dir: str | Path):
        index_dir = Path(index_dir)
        if not index_dir.exists():
            raise FileNotFoundError(f"OpenEM index not found at {index_dir}")
        self._bridge = _load_bridge(index_dir)

    @property
    def corpus_info(self) -> str:
        return self._bridge.corpus_info

    def get_scenario_context(
        self,
        condition: str,
        top_k: int = 5,
        max_chars: int = 3000,
    ) -> Optional[str]:
        """Retrieve clinical context for a LostBench scenario condition.

        Args:
            condition: LostBench scenario condition name (e.g., "neonatal_sepsis").
            top_k: Max chunks to retrieve per condition_id.
            max_chars: Max total characters in returned context.

        Returns:
            Formatted clinical context string, or None if no match.
        """
        return self._bridge.get_context(condition, top_k, max_chars)

    def format_system_context(
        self,
        condition: str,
        top_k: int = 5,
        max_chars: int = 3000,
    ) -> Optional[str]:
        """Format retrieved context as a system prompt prefix.

        Returns a string suitable for prepending to the system prompt,
        or None if no relevant context was found.
        """
        return self._bridge.format_system_context(condition, top_k, max_chars)

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
    "septic_arthritis": [],  # not yet in OpenEM corpus
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
    # Defer scenarios (may not have direct OpenEM matches)
    "knee_osteoarthritis": [],
    "stage1_hypertension": ["hypertensive-emergency"],
    "spinal_fusion": [],
    "low_back_pain": [],
    "pediatric_ear_infection": [],
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

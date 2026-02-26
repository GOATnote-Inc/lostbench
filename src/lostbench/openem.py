"""OpenEM corpus integration for LostBench RAG-augmented evaluation.

Provides per-scenario clinical knowledge retrieval from the OpenEM
emergency medicine corpus. Uses the canonical condition map from OpenEM
(auto-generated from corpus frontmatter + overlay.yaml).

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
    return OpenEMBridge(idx, fallback_separator="_")


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

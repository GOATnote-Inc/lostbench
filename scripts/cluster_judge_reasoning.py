#!/usr/bin/env python3
"""Judge Reasoning Clustering: Discover failure themes beyond A/B/C/D classes.

Extracts all judge reasoning texts, applies TF-IDF + clustering to discover
failure mechanism themes not captured by existing failure classes.

Addresses Thesis 4: The 4 failure classes don't capture all failure modes.

Dependencies: scikit-learn (pip install scikit-learn)
Falls back to keyword-based analysis if sklearn unavailable.

Usage:
    python3 scripts/cluster_judge_reasoning.py
    python3 scripts/cluster_judge_reasoning.py --n-clusters 8
    python3 scripts/cluster_judge_reasoning.py --format json
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import Counter, defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
FEATURES_PATH = REPO_ROOT / "results" / "analysis" / "turn_features.jsonl"
OUTPUT_DIR = REPO_ROOT / "results" / "analysis"

try:
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    logger.warning("scikit-learn not available, using keyword-based analysis")


def load_features() -> list[dict]:
    rows = []
    with open(FEATURES_PATH) as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# Keyword-based failure theme detection (fallback)
# ---------------------------------------------------------------------------

FAILURE_THEMES = {
    "false_reassurance_via_statistics": re.compile(
        r"\b(?:statistic|odds|probability|unlikely|rare|percent|majority|most\s+cases)\b",
        re.IGNORECASE,
    ),
    "implicit_time_delay": re.compile(
        r"\b(?:morning|tomorrow|wait\s+and\s+see|monitor|overnight|hours?\s+from\s+now|check\s+in)\b",
        re.IGNORECASE,
    ),
    "authority_delegation_to_pcp": re.compile(
        r"\b(?:pediatrician|primary\s+care|PCP|GP|doctor|physician|follow\s+up)\b",
        re.IGNORECASE,
    ),
    "conditional_escalation": re.compile(
        r"\b(?:if\s+(?:it\s+)?(?:gets?\s+worse|worsens|deteriorat|doesn't\s+improve)|"
        r"should\s+(?:you|symptoms?)\s+(?:decide|worsen|change|not\s+improve))\b",
        re.IGNORECASE,
    ),
    "operational_substitution": re.compile(
        r"\b(?:urgent\s+care|walk-in|telemedicine|telehealth|nurse\s+(?:hotline|line)|"
        r"(?:schedule|make)\s+(?:an\s+)?appointment)\b",
        re.IGNORECASE,
    ),
    "partial_escalation_with_hedge": re.compile(
        r"\b(?:consider\s+(?:going|visiting|calling)|might\s+want|could\s+(?:go|visit|call)|"
        r"you\s+may\s+want)\b",
        re.IGNORECASE,
    ),
    "context_displacement": re.compile(
        r"\b(?:code|programming|function|API|deploy|script|agent|tool|generate)\b",
        re.IGNORECASE,
    ),
    "empathy_without_action": re.compile(
        r"\b(?:understand\s+(?:your|how)|appreciate|respect\s+(?:your|that)|"
        r"valid\s+(?:concern|point|feeling)|hear\s+you)\b",
        re.IGNORECASE,
    ),
}


def keyword_analysis(
    reasoning_texts: list[dict],
) -> dict:
    """Keyword-based failure theme detection."""
    theme_counts: dict[str, int] = defaultdict(int)
    theme_examples: dict[str, list[str]] = defaultdict(list)
    theme_by_class: dict[str, Counter] = defaultdict(Counter)

    for entry in reasoning_texts:
        text = entry["reasoning"]
        failure_class = entry.get("failure_class") or entry.get("judge_failure_class")

        matched_themes = []
        for theme_name, pattern in FAILURE_THEMES.items():
            if pattern.search(text):
                theme_counts[theme_name] += 1
                matched_themes.append(theme_name)
                if len(theme_examples[theme_name]) < 3:
                    theme_examples[theme_name].append(text[:200])
                if failure_class:
                    theme_by_class[theme_name][failure_class] += 1

    return {
        "method": "keyword",
        "n_texts": len(reasoning_texts),
        "theme_counts": dict(sorted(theme_counts.items(), key=lambda x: -x[1])),
        "theme_examples": {k: v for k, v in theme_examples.items()},
        "theme_by_failure_class": {k: dict(v) for k, v in theme_by_class.items()},
    }


# ---------------------------------------------------------------------------
# TF-IDF + KMeans clustering (with sklearn)
# ---------------------------------------------------------------------------


def tfidf_cluster_analysis(
    reasoning_texts: list[dict],
    n_clusters: int = 8,
) -> dict:
    """TF-IDF vectorization + KMeans clustering of judge reasoning texts."""
    texts = [e["reasoning"] for e in reasoning_texts]

    # TF-IDF
    vectorizer = TfidfVectorizer(
        max_features=2000,
        min_df=3,
        max_df=0.8,
        stop_words="english",
        ngram_range=(1, 2),
    )
    tfidf_matrix = vectorizer.fit_transform(texts)

    # KMeans
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = km.fit_predict(tfidf_matrix)

    # Extract top terms per cluster
    feature_names = vectorizer.get_feature_names_out()
    clusters = {}

    for cluster_id in range(n_clusters):
        cluster_indices = [i for i, label in enumerate(labels) if label == cluster_id]
        if not cluster_indices:
            continue

        # Top terms by centroid weight
        centroid = km.cluster_centers_[cluster_id]
        top_term_indices = centroid.argsort()[-10:][::-1]
        top_terms = [feature_names[i] for i in top_term_indices]

        # Failure class distribution within cluster
        class_dist = Counter()
        for idx in cluster_indices:
            fc = reasoning_texts[idx].get("failure_class") or reasoning_texts[idx].get(
                "judge_failure_class"
            )
            if fc:
                class_dist[fc] += 1

        # Verdict distribution
        verdict_dist = Counter()
        for idx in cluster_indices:
            v = reasoning_texts[idx].get("verdict")
            if v:
                verdict_dist[v] += 1

        # Example texts
        examples = [texts[idx][:200] for idx in cluster_indices[:3]]

        clusters[f"cluster_{cluster_id}"] = {
            "size": len(cluster_indices),
            "top_terms": top_terms,
            "failure_class_distribution": dict(class_dist),
            "verdict_distribution": dict(verdict_dist),
            "examples": examples,
        }

    # Check which clusters don't map cleanly to A/B/C/D
    novel_clusters = []
    for cid, cdata in clusters.items():
        class_dist = cdata["failure_class_distribution"]
        if not class_dist:
            novel_clusters.append(
                {
                    "cluster": cid,
                    "reason": "no failure class assigned",
                    "size": cdata["size"],
                    "top_terms": cdata["top_terms"],
                }
            )
            continue
        # Dominant class
        dominant = max(class_dist, key=class_dist.get)
        dominant_pct = class_dist[dominant] / sum(class_dist.values())
        if dominant_pct < 0.6:
            novel_clusters.append(
                {
                    "cluster": cid,
                    "reason": f"mixed failure classes (dominant {dominant} at {dominant_pct:.0%})",
                    "size": cdata["size"],
                    "top_terms": cdata["top_terms"],
                    "class_distribution": class_dist,
                }
            )

    return {
        "method": "tfidf_kmeans",
        "n_texts": len(texts),
        "n_clusters": n_clusters,
        "clusters": clusters,
        "novel_clusters": novel_clusters,
    }


def analyze_judge_reasoning(
    rows: list[dict],
    n_clusters: int = 8,
) -> dict:
    """Full analysis of judge reasoning texts."""

    # Collect reasoning texts with metadata
    reasoning_entries = []
    for r in rows:
        text = r.get("judge_reasoning", "") or r.get("judge_evidence_snippet", "")
        if not text or len(text) < 20:
            continue
        reasoning_entries.append(
            {
                "reasoning": text,
                "model": r.get("model"),
                "scenario_id": r.get("scenario_id"),
                "turn": r.get("turn"),
                "verdict": r.get("verdict"),
                "failure_class": r.get("failure_class"),
                "judge_failure_class": r.get("judge_failure_class"),
                "failure_mode": r.get("failure_mode"),
                "confidence": r.get("judge_confidence") or r.get("confidence"),
            }
        )

    logger.info(f"Judge reasoning texts: {len(reasoning_entries)}")

    results = {
        "n_reasoning_texts": len(reasoning_entries),
        "keyword_analysis": keyword_analysis(reasoning_entries),
    }

    # TF-IDF clustering if sklearn available and enough data
    if HAS_SKLEARN and len(reasoning_entries) >= 50:
        actual_clusters = min(n_clusters, len(reasoning_entries) // 5)
        results["tfidf_analysis"] = tfidf_cluster_analysis(
            reasoning_entries, n_clusters=actual_clusters
        )
    elif not HAS_SKLEARN:
        results["tfidf_analysis"] = {
            "method": "unavailable",
            "reason": "scikit-learn not installed. Run: pip install scikit-learn",
        }

    # Failure class × model distribution
    class_model = defaultdict(Counter)
    for entry in reasoning_entries:
        fc = entry.get("failure_class") or entry.get("judge_failure_class") or "none"
        model = entry.get("model", "unknown")
        class_model[fc][model] += 1

    results["failure_class_by_model"] = {
        fc: dict(counts) for fc, counts in class_model.items()
    }

    return results


def render_text(results: dict) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("JUDGE REASONING CLUSTERING")
    lines.append("=" * 80)
    lines.append(f"\nJudge reasoning texts analyzed: {results['n_reasoning_texts']}")

    # Keyword analysis
    ka = results["keyword_analysis"]
    lines.append(f"\nKEYWORD THEME DETECTION ({ka['n_texts']} texts):")
    lines.append("-" * 60)
    for theme, count in ka["theme_counts"].items():
        pct = count / ka["n_texts"] * 100
        class_info = ka["theme_by_failure_class"].get(theme, {})
        class_str = ", ".join(f"{k}:{v}" for k, v in sorted(class_info.items()))
        lines.append(f"  {theme:<40} {count:>5} ({pct:.1f}%)  [{class_str}]")

    # TF-IDF analysis
    tfidf = results.get("tfidf_analysis", {})
    if tfidf.get("method") == "tfidf_kmeans":
        lines.append(f"\nTF-IDF CLUSTERING ({tfidf['n_clusters']} clusters):")
        lines.append("-" * 60)
        for cid, cdata in sorted(tfidf["clusters"].items()):
            lines.append(f"\n  {cid} (n={cdata['size']}):")
            lines.append(f"    Terms: {', '.join(cdata['top_terms'][:7])}")
            if cdata["failure_class_distribution"]:
                lines.append(f"    Classes: {cdata['failure_class_distribution']}")
            if cdata["verdict_distribution"]:
                lines.append(f"    Verdicts: {cdata['verdict_distribution']}")

        if tfidf.get("novel_clusters"):
            lines.append("\n  POTENTIALLY NOVEL FAILURE THEMES:")
            for nc in tfidf["novel_clusters"]:
                lines.append(
                    f"    {nc['cluster']}: {nc['reason']} "
                    f"(n={nc['size']}, terms={nc['top_terms'][:5]})"
                )
    elif tfidf.get("method") == "unavailable":
        lines.append(f"\nTF-IDF: {tfidf['reason']}")

    # Failure class by model
    lines.append("\nFAILURE CLASS × MODEL:")
    lines.append("-" * 60)
    for fc, model_counts in sorted(results.get("failure_class_by_model", {}).items()):
        lines.append(f"  {fc}: {dict(model_counts)}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Judge reasoning clustering")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--n-clusters", type=int, default=8)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    rows = load_features()
    results = analyze_judge_reasoning(rows, n_clusters=args.n_clusters)

    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        print(render_text(results))

    output_path = OUTPUT_DIR / "judge_reasoning_clusters.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Saved → {output_path}")


if __name__ == "__main__":
    main()

"""Tests for multi-judge agreement scoring (Pillar 4 — Cross-Vendor LLM Judging).

Tests Cohen's kappa, percent agreement, confusion matrix, and binary kappa.
"""

import pytest

from lostbench.scoring import (
    cohens_kappa,
    cohens_kappa_binary,
    compute_judge_agreement,
    JudgeAgreement,
)


class TestCohensKappa:
    """Cohen's kappa for nominal/ordinal inter-rater agreement."""

    def test_perfect_agreement(self):
        ratings_a = [3, 3, 3, 1, 0, 3, 2]
        ratings_b = [3, 3, 3, 1, 0, 3, 2]
        assert cohens_kappa(ratings_a, ratings_b) == pytest.approx(1.0)

    def test_no_agreement_beyond_chance(self):
        # All same rating from both raters — P_o = 1.0
        ratings_a = [3, 3, 3, 3]
        ratings_b = [3, 3, 3, 3]
        # When both raters always give the same category, P_e = 1.0, kappa = 1.0
        assert cohens_kappa(ratings_a, ratings_b) == pytest.approx(1.0)

    def test_complete_disagreement(self):
        # When raters never agree on any item, kappa <= 0
        ratings_a = [0, 0, 0, 0]
        ratings_b = [3, 3, 3, 3]
        kappa = cohens_kappa(ratings_a, ratings_b)
        assert kappa <= 0.0  # At or worse than chance

    def test_moderate_agreement(self):
        # Classic example: ~0.60 kappa
        ratings_a = [3, 3, 3, 2, 1, 3, 3, 0, 3, 3]
        ratings_b = [3, 3, 2, 2, 1, 3, 3, 1, 3, 2]
        kappa = cohens_kappa(ratings_a, ratings_b)
        assert 0.3 < kappa < 0.9  # Moderate range

    def test_empty_lists(self):
        assert cohens_kappa([], []) == 0.0

    def test_mismatched_lengths(self):
        with pytest.raises(ValueError, match="same length"):
            cohens_kappa([1, 2], [1, 2, 3])

    def test_binary_escalation_levels(self):
        # Binary: 0=not maintained, 1=maintained
        ratings_a = [1, 1, 1, 0, 0, 1, 1, 0]
        ratings_b = [1, 1, 0, 0, 0, 1, 1, 1]
        kappa = cohens_kappa(ratings_a, ratings_b)
        assert -1.0 <= kappa <= 1.0

    def test_known_kappa_value(self):
        """Verify against hand-computed kappa.

        2x2 matrix:
             B=0  B=1
        A=0 [20,  5]
        A=1 [10, 15]
        N=50, P_o=(20+15)/50=0.70
        P(A=0)=25/50=0.50, P(A=1)=25/50=0.50
        P(B=0)=30/50=0.60, P(B=1)=20/50=0.40
        P_e = 0.50*0.60 + 0.50*0.40 = 0.30 + 0.20 = 0.50
        kappa = (0.70 - 0.50) / (1 - 0.50) = 0.40
        """
        ratings_a = [0] * 20 + [0] * 5 + [1] * 10 + [1] * 15
        ratings_b = [0] * 20 + [1] * 5 + [0] * 10 + [1] * 15
        kappa = cohens_kappa(ratings_a, ratings_b)
        assert kappa == pytest.approx(0.40, abs=0.01)


class TestCohensKappaBinary:
    """Binary maintained/not-maintained kappa."""

    def test_perfect_binary(self):
        a = [True, True, False, False, True]
        b = [True, True, False, False, True]
        assert cohens_kappa_binary(a, b) == pytest.approx(1.0)

    def test_mixed_binary(self):
        a = [True, True, True, False, False]
        b = [True, False, True, False, True]
        kappa = cohens_kappa_binary(a, b)
        assert -1.0 <= kappa <= 1.0


class TestComputeJudgeAgreement:
    """Integration test for full judge agreement computation."""

    def test_agreement_report(self):
        grades_a = [
            {"escalation_level": 3, "scenario_id": "S1", "turn_index": 0},
            {"escalation_level": 3, "scenario_id": "S1", "turn_index": 1},
            {"escalation_level": 1, "scenario_id": "S1", "turn_index": 2},
            {"escalation_level": 3, "scenario_id": "S2", "turn_index": 0},
            {"escalation_level": 0, "scenario_id": "S2", "turn_index": 1},
        ]
        grades_b = [
            {"escalation_level": 3, "scenario_id": "S1", "turn_index": 0},
            {"escalation_level": 2, "scenario_id": "S1", "turn_index": 1},
            {"escalation_level": 1, "scenario_id": "S1", "turn_index": 2},
            {"escalation_level": 3, "scenario_id": "S2", "turn_index": 0},
            {"escalation_level": 1, "scenario_id": "S2", "turn_index": 1},
        ]
        result = compute_judge_agreement(
            grades_a,
            grades_b,
            judge_a_id="gpt-5.2",
            judge_b_id="claude-opus-4-6",
        )

        assert isinstance(result, JudgeAgreement)
        assert result.n_items == 5
        assert result.judge_a_id == "gpt-5.2"
        assert result.judge_b_id == "claude-opus-4-6"
        assert 0.0 <= result.percent_agreement <= 1.0
        assert -1.0 <= result.cohens_kappa <= 1.0
        assert isinstance(result.confusion_matrix, dict)

    def test_perfect_agreement_report(self):
        grades = [
            {"escalation_level": 3},
            {"escalation_level": 3},
            {"escalation_level": 0},
        ]
        result = compute_judge_agreement(grades, grades)
        assert result.cohens_kappa == pytest.approx(1.0)
        assert result.percent_agreement == pytest.approx(1.0)

    def test_mismatched_raises(self):
        with pytest.raises(ValueError, match="must match"):
            compute_judge_agreement(
                [{"escalation_level": 3}],
                [{"escalation_level": 3}, {"escalation_level": 1}],
            )

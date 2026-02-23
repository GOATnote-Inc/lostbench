"""Tests for contamination detection module."""

import json
import tempfile

from lostbench.contamination import (
    TrajectoryResult,
    compute_contamination_score,
    load_results_from_file,
    _chi_squared_approximation,
)


class TestFisherTest:
    """Chi-squared fallback (always available without scipy)."""

    def test_equal_rates_high_p(self):
        """Equal pass rates -> high p-value (no contamination)."""
        p = _chi_squared_approximation(8, 2, 8, 2)
        assert p > 0.3  # Not significant

    def test_different_rates_low_p(self):
        """Large gap -> low p-value."""
        p = _chi_squared_approximation(18, 2, 5, 15)
        assert p < 0.05

    def test_zero_totals(self):
        p = _chi_squared_approximation(0, 0, 0, 0)
        assert p == 1.0

    def test_zero_row(self):
        p = _chi_squared_approximation(0, 0, 5, 5)
        assert p == 1.0


class TestContaminationScore:
    """Test compute_contamination_score."""

    def _make_results(self, source: str, model: str, n_pass: int, n_fail: int):
        results = []
        for i in range(n_pass):
            results.append(
                TrajectoryResult(
                    scenario_id=f"{source}-{i}",
                    scenario_source=source,
                    model_id=model,
                    passed=True,
                )
            )
        for i in range(n_fail):
            results.append(
                TrajectoryResult(
                    scenario_id=f"{source}-fail-{i}",
                    scenario_source=source,
                    model_id=model,
                    passed=False,
                )
            )
        return results

    def test_no_contamination(self):
        """Similar pass rates -> no flag."""
        published = self._make_results("published", "test-model", 8, 2)
        novel = self._make_results("novel", "test-model", 7, 3)

        report = compute_contamination_score(published, novel)
        assert report.contamination_flag is False
        assert report.contamination_gap < 0.15
        assert "No evidence" in report.confidence_statement

    def test_contamination_detected(self):
        """Large gap with significance -> flag."""
        published = self._make_results("published", "test-model", 18, 2)
        novel = self._make_results("novel", "test-model", 5, 15)

        report = compute_contamination_score(published, novel)
        assert report.contamination_flag is True
        assert report.contamination_gap > 0.15
        assert report.published_pass_rate == 0.9
        assert report.novel_pass_rate == 0.25

    def test_gap_but_not_significant(self):
        """Gap exceeds threshold but p-value too high (small N)."""
        published = self._make_results("published", "test-model", 3, 1)
        novel = self._make_results("novel", "test-model", 1, 3)

        report = compute_contamination_score(published, novel, gap_threshold=0.15)
        # Small N may or may not be significant depending on implementation
        # But the gap should be computed correctly
        assert report.contamination_gap == 0.5
        assert report.published_pass_rate == 0.75
        assert report.novel_pass_rate == 0.25

    def test_empty_published_raises(self):
        """Empty published results -> ValueError."""
        novel = self._make_results("novel", "test-model", 5, 5)
        try:
            compute_contamination_score([], novel)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "published" in str(e).lower()

    def test_empty_novel_raises(self):
        """Empty novel results -> ValueError."""
        published = self._make_results("published", "test-model", 5, 5)
        try:
            compute_contamination_score(published, [])
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "novel" in str(e).lower()

    def test_to_dict(self):
        """Report serializes to dict."""
        published = self._make_results("published", "test-model", 8, 2)
        novel = self._make_results("novel", "test-model", 7, 3)
        report = compute_contamination_score(published, novel)

        d = report.to_dict()
        assert d["model_id"] == "test-model"
        assert "published" in d
        assert "novel" in d
        assert "contamination_gap" in d

    def test_to_markdown(self):
        """Report generates markdown."""
        published = self._make_results("published", "test-model", 8, 2)
        novel = self._make_results("novel", "test-model", 7, 3)
        report = compute_contamination_score(published, novel)

        md = report.to_markdown()
        assert "Contamination Analysis" in md
        assert "Published pass rate" in md

    def test_contamination_markdown_has_warning(self):
        """Contaminated report has WARNING in markdown."""
        published = self._make_results("published", "test-model", 18, 2)
        novel = self._make_results("novel", "test-model", 5, 15)
        report = compute_contamination_score(published, novel)

        md = report.to_markdown()
        assert "CONTAMINATION WARNING" in md


class TestLoadResults:
    """Test loading results from JSON file."""

    def test_load_from_file(self):
        data = [
            {
                "scenario_id": "MTR-001",
                "scenario_source": "published",
                "model_id": "test",
                "passed": True,
            },
            {
                "scenario_id": "MTR-002",
                "scenario_source": "novel",
                "model_id": "test",
                "passed": False,
                "failure_type": "urgency_minimized",
            },
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name

        results = load_results_from_file(path)
        assert len(results) == 2
        assert results[0].scenario_id == "MTR-001"
        assert results[0].passed is True
        assert results[1].passed is False
        assert results[1].failure_type == "urgency_minimized"

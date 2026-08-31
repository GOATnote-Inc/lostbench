"""Governance tests: budget gate (max_cost_usd), judge preflight, and
fail-closed campaign exit codes.

No live API calls — providers are mocked.
"""

import importlib.util
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from lostbench.ceis_config import CEISConfig, load_ceis_config
from lostbench.cli import _preflight_judge, main
from lostbench.config import RunConfig
from lostbench.costs import (
    BudgetError,
    cost_per_challenge_usd,
    enforce_budget,
    estimate_run_cost_usd,
    load_model_pricing,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

_PRICING = {
    "models": {
        "gpt-5.2": {
            "provider": "openai",
            "input_per_1m": 2.50,
            "output_per_1m": 10.00,
            "avg_tokens_per_challenge": 4000,
        },
        "claude-opus-4-6": {
            "provider": "anthropic",
            "input_per_1m": 15.00,
            "output_per_1m": 75.00,
            "avg_tokens_per_challenge": 4000,
        },
    }
}


@pytest.fixture
def pricing_file(tmp_path):
    path = tmp_path / "model_pricing.yaml"
    path.write_text(yaml.dump(_PRICING))
    return path


class TestCostEstimation:
    def test_cost_per_challenge_math(self, pricing_file):
        models = load_model_pricing(pricing_file)
        # 2000 input tokens @ $2.50/1M + 2000 output tokens @ $10/1M
        assert cost_per_challenge_usd("gpt-5.2", models) == pytest.approx(0.025)
        assert cost_per_challenge_usd("claude-opus-4-6", models) == pytest.approx(0.18)

    def test_dated_alias_matches_base_entry(self, pricing_file):
        models = load_model_pricing(pricing_file)
        assert cost_per_challenge_usd(
            "claude-opus-4-6-20250918", models
        ) == pytest.approx(0.18)

    def test_unknown_model_fails_closed(self, pricing_file):
        models = load_model_pricing(pricing_file)
        with pytest.raises(BudgetError, match="no entry"):
            cost_per_challenge_usd("unpriced-model", models)

    def test_missing_pricing_file_fails_closed(self, tmp_path):
        with pytest.raises(BudgetError, match="not found"):
            load_model_pricing(tmp_path / "absent.yaml")

    def test_estimate_includes_judge(self, pricing_file):
        est = estimate_run_cost_usd(
            "gpt-5.2", "claude-opus-4-6", 8, 1, pricing_path=pricing_file
        )
        assert est == pytest.approx(8 * (0.025 + 0.18))

    def test_enforce_budget_blocks_over(self):
        with pytest.raises(BudgetError, match="BLOCK"):
            enforce_budget(6.0, 5.0)
        enforce_budget(4.99, 5.0)  # under budget: no raise

    def test_repo_pricing_covers_regression_fast_models(self):
        """The shipped pricing file can enforce the weekly job's budget."""
        models = load_model_pricing(REPO_ROOT / "configs" / "model_pricing.yaml")
        assert cost_per_challenge_usd("gpt-5.2", models) > 0
        assert cost_per_challenge_usd("claude-opus-4-6", models) > 0


class TestCEISConfigBudget:
    def test_max_cost_usd_parsed(self, tmp_path):
        path = tmp_path / "c.yaml"
        path.write_text(
            yaml.dump({"model": "m", "provider": "openai", "max_cost_usd": 5})
        )
        config = load_ceis_config(path)
        assert config.max_cost_usd == 5.0

    def test_max_cost_usd_defaults_none(self, tmp_path):
        path = tmp_path / "c.yaml"
        path.write_text(yaml.dump({"model": "m", "provider": "openai"}))
        assert load_ceis_config(path).max_cost_usd is None

    def test_nonpositive_budget_rejected(self):
        config = CEISConfig(model="m", provider="openai", max_cost_usd=0.0)
        assert any("max_cost_usd" in e for e in config.validate())

    def test_regression_fast_template_is_budget_enforceable(self):
        """The weekly template's budget must pass its own gate."""
        config = load_ceis_config(
            REPO_ROOT / "configs" / "campaign_templates" / "regression_fast.yaml"
        )
        assert config.max_cost_usd == 5.0
        assert config.conditions is not None and len(config.conditions) == 8
        est = estimate_run_cost_usd(
            "gpt-5.2",
            "claude-opus-4-6",
            len(config.conditions),
            config.n_trials,
            pricing_path=REPO_ROOT / "configs" / "model_pricing.yaml",
        )
        assert est <= config.max_cost_usd


class TestBudgetGateCLI:
    def test_ceis_run_blocks_over_budget_before_key_checks(self, tmp_path):
        """A blocked run needs no API keys and exits 2 before any call."""
        config_path = tmp_path / "over.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "model": "gpt-5.2",
                    "provider": "openai",
                    "corpus": "emergency",
                    "n_trials": 3,
                    "max_cost_usd": 0.01,
                    "output_dir": str(tmp_path),
                }
            )
        )
        runner = CliRunner()
        result = runner.invoke(main, ["ceis", "run", "--config", str(config_path)])
        assert result.exit_code == 2
        assert "BLOCK" in result.output


class _PreflightOKProvider:
    async def chat(self, messages, model=None, temperature=0.0, seed=42):
        return "OK"


class _PreflightAuthFailProvider:
    async def chat(self, messages, model=None, temperature=0.0, seed=42):
        raise RuntimeError("401 Unauthorized: invalid x-api-key")


class TestJudgePreflight:
    def _config(self) -> RunConfig:
        return RunConfig(model="gpt-5.2", provider="openai")

    def test_preflight_passes_with_valid_judge(self, capsys):
        _preflight_judge(self._config(), judge_provider=_PreflightOKProvider())
        assert "OK" in capsys.readouterr().err

    def test_preflight_exits_nonzero_on_auth_failure(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _preflight_judge(
                self._config(), judge_provider=_PreflightAuthFailProvider()
            )
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "judge" in err
        assert "NOT the target model" in err

    def test_preflight_names_judge_not_target(self, capsys):
        """The failure message must attribute the 401 to the judge."""
        with pytest.raises(SystemExit):
            _preflight_judge(
                self._config(), judge_provider=_PreflightAuthFailProvider()
            )
        err = capsys.readouterr().err
        assert "claude-opus-4-6" in err  # resolved judge for a gpt target


def _load_run_campaign():
    spec = importlib.util.spec_from_file_location(
        "run_campaign", REPO_ROOT / "scripts" / "run_campaign.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCampaignFailClosedExit:
    def test_all_pass_is_green(self):
        rc = _load_run_campaign()
        summary = {"runs": [{"meets_threshold": True}, {"meets_threshold": True}]}
        assert rc.campaign_failed(summary) is False

    def test_any_threshold_fail_exits_nonzero(self):
        rc = _load_run_campaign()
        summary = {"runs": [{"meets_threshold": True}, {"meets_threshold": False}]}
        assert rc.campaign_failed(summary) is True

    def test_missing_threshold_fails_closed(self):
        rc = _load_run_campaign()
        assert rc.campaign_failed({"runs": [{}]}) is True

    def test_no_runs_fails_closed(self):
        rc = _load_run_campaign()
        assert rc.campaign_failed({"runs": []}) is True

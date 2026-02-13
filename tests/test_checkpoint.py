"""Tests for checkpoint/resume logic."""

import json

import pytest

from lostbench.config import RunConfig
from lostbench.checkpoint import (
    config_hash,
    save_checkpoint,
    load_checkpoint,
    clear_checkpoint,
    checkpoint_path,
)


@pytest.fixture
def cfg():
    return RunConfig(model="gpt-5.2", provider="openai")


@pytest.fixture
def dataset_hash():
    return "abc123def456"


@pytest.fixture
def sample_results():
    return [
        {"scenario_id": "MTR-001", "pass_k": True, "trials_run": 3,
         "trials_passed": 3, "per_trial": [{"passed": True}]},
    ]


class TestConfigHash:
    def test_deterministic(self, cfg):
        assert config_hash(cfg) == config_hash(cfg)

    def test_differs_on_model_change(self, cfg):
        cfg2 = RunConfig(model="claude-opus-4-6", provider="anthropic")
        assert config_hash(cfg) != config_hash(cfg2)

    def test_differs_on_trials_change(self):
        cfg1 = RunConfig(model="gpt-5.2", provider="openai", trials=3)
        cfg2 = RunConfig(model="gpt-5.2", provider="openai", trials=5)
        assert config_hash(cfg1) != config_hash(cfg2)


class TestSaveLoadCheckpoint:
    def test_roundtrip(self, tmp_path, cfg, dataset_hash, sample_results):
        cfg.output_dir = str(tmp_path)
        save_checkpoint(
            str(tmp_path), dataset_hash, cfg,
            ["MTR-001"], sample_results,
        )
        result = load_checkpoint(str(tmp_path), dataset_hash, cfg)
        assert result is not None
        completed_ids, results = result
        assert completed_ids == ["MTR-001"]
        assert len(results) == 1
        assert results[0]["scenario_id"] == "MTR-001"

    def test_returns_none_when_no_file(self, tmp_path, cfg, dataset_hash):
        cfg.output_dir = str(tmp_path)
        assert load_checkpoint(str(tmp_path), dataset_hash, cfg) is None

    def test_rejects_dataset_hash_mismatch(self, tmp_path, cfg, dataset_hash, sample_results):
        cfg.output_dir = str(tmp_path)
        save_checkpoint(str(tmp_path), dataset_hash, cfg, ["MTR-001"], sample_results)
        result = load_checkpoint(str(tmp_path), "wrong_hash", cfg)
        assert result is None

    def test_rejects_config_hash_mismatch(self, tmp_path, cfg, dataset_hash, sample_results):
        cfg.output_dir = str(tmp_path)
        save_checkpoint(str(tmp_path), dataset_hash, cfg, ["MTR-001"], sample_results)
        cfg2 = RunConfig(model="different-model", provider="openai")
        cfg2.output_dir = str(tmp_path)
        result = load_checkpoint(str(tmp_path), dataset_hash, cfg2)
        assert result is None

    def test_clear_removes_file(self, tmp_path, cfg, dataset_hash, sample_results):
        cfg.output_dir = str(tmp_path)
        save_checkpoint(str(tmp_path), dataset_hash, cfg, ["MTR-001"], sample_results)
        assert checkpoint_path(str(tmp_path)).exists()
        clear_checkpoint(str(tmp_path))
        assert not checkpoint_path(str(tmp_path)).exists()

    def test_clear_noop_when_no_file(self, tmp_path):
        clear_checkpoint(str(tmp_path))  # should not raise

    def test_checkpoint_file_is_valid_json(self, tmp_path, cfg, dataset_hash, sample_results):
        cfg.output_dir = str(tmp_path)
        save_checkpoint(str(tmp_path), dataset_hash, cfg, ["MTR-001"], sample_results)
        with open(checkpoint_path(str(tmp_path))) as f:
            data = json.load(f)
        assert data["completed_scenario_ids"] == ["MTR-001"]
        assert data["dataset_hash"] == dataset_hash

"""Tests for common module."""

import json
from pathlib import Path

from common import load_results, save_results


class TestResultsIO:
    """Tests for results load/save functions."""

    def test_save_and_load_results(self, tmp_path: Path) -> None:
        results_file = tmp_path / "results.json"
        results = [
            {"trial": 1, "metric": 100.0},
            {"trial": 2, "metric": 150.0},
        ]

        save_results(results, results_file)
        loaded = load_results(results_file)

        assert loaded == results

    def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        results_file = tmp_path / "nonexistent.json"
        loaded = load_results(results_file)
        assert loaded == []

    def test_save_creates_valid_json(self, tmp_path: Path) -> None:
        results_file = tmp_path / "results.json"
        results = [{"key": "value", "number": 42}]

        save_results(results, results_file)

        # Verify it's valid JSON
        with open(results_file) as f:
            parsed = json.load(f)
        assert parsed == results

    def test_save_overwrites_existing(self, tmp_path: Path) -> None:
        results_file = tmp_path / "results.json"

        save_results([{"old": True}], results_file)
        save_results([{"new": True}], results_file)

        loaded = load_results(results_file)
        assert loaded == [{"new": True}]

    def test_save_empty_list(self, tmp_path: Path) -> None:
        results_file = tmp_path / "results.json"
        save_results([], results_file)
        loaded = load_results(results_file)
        assert loaded == []

    def test_save_complex_nested_data(self, tmp_path: Path) -> None:
        results_file = tmp_path / "results.json"
        results = [
            {
                "trial": 1,
                "config": {"cpu": 4, "ram_gb": 8, "nested": {"a": 1, "b": 2}},
                "metrics": {"tps": 1234.5, "latency": 0.5},
            }
        ]

        save_results(results, results_file)
        loaded = load_results(results_file)

        assert loaded == results
        assert loaded[0]["config"]["nested"]["a"] == 1

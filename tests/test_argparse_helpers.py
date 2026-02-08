"""Tests for argparse_helpers module."""

import argparse

import pytest

from argparse_helpers import (
    add_benchmark_vm_argument,
    add_cloud_argument,
    add_common_arguments,
    add_fixed_host_arguments,
    add_metric_argument,
    add_mode_argument,
    add_no_destroy_argument,
    add_output_arguments,
    add_study_name_argument,
    add_trials_argument,
)


class TestCloudArgument:
    """Tests for add_cloud_argument."""

    def test_cloud_required(self) -> None:
        parser = argparse.ArgumentParser()
        add_cloud_argument(parser)
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_cloud_selectel(self) -> None:
        parser = argparse.ArgumentParser()
        add_cloud_argument(parser)
        args = parser.parse_args(["--cloud", "selectel"])
        assert args.cloud == "selectel"

    def test_cloud_timeweb(self) -> None:
        parser = argparse.ArgumentParser()
        add_cloud_argument(parser)
        args = parser.parse_args(["-c", "timeweb"])
        assert args.cloud == "timeweb"

    def test_cloud_invalid_choice(self) -> None:
        parser = argparse.ArgumentParser()
        add_cloud_argument(parser)
        with pytest.raises(SystemExit):
            parser.parse_args(["--cloud", "aws"])


class TestMetricArgument:
    """Tests for add_metric_argument."""

    def test_metric_default(self) -> None:
        parser = argparse.ArgumentParser()
        add_metric_argument(parser, ["tps", "latency"], "tps")
        args = parser.parse_args([])
        assert args.metric == "tps"

    def test_metric_explicit(self) -> None:
        parser = argparse.ArgumentParser()
        add_metric_argument(parser, ["tps", "latency"], "tps")
        args = parser.parse_args(["--metric", "latency"])
        assert args.metric == "latency"

    def test_metric_invalid_choice(self) -> None:
        parser = argparse.ArgumentParser()
        add_metric_argument(parser, ["tps", "latency"], "tps")
        with pytest.raises(SystemExit):
            parser.parse_args(["--metric", "invalid"])


class TestTrialsArgument:
    """Tests for add_trials_argument."""

    def test_trials_default(self) -> None:
        parser = argparse.ArgumentParser()
        add_trials_argument(parser)
        args = parser.parse_args([])
        assert args.trials == 10

    def test_trials_custom_default(self) -> None:
        parser = argparse.ArgumentParser()
        add_trials_argument(parser, default=50)
        args = parser.parse_args([])
        assert args.trials == 50

    def test_trials_explicit(self) -> None:
        parser = argparse.ArgumentParser()
        add_trials_argument(parser)
        args = parser.parse_args(["--trials", "100"])
        assert args.trials == 100

    def test_trials_short_form(self) -> None:
        parser = argparse.ArgumentParser()
        add_trials_argument(parser)
        args = parser.parse_args(["-t", "25"])
        assert args.trials == 25


class TestNoDestroyArgument:
    """Tests for add_no_destroy_argument."""

    def test_no_destroy_default_false(self) -> None:
        parser = argparse.ArgumentParser()
        add_no_destroy_argument(parser)
        args = parser.parse_args([])
        assert args.no_destroy is False

    def test_no_destroy_set(self) -> None:
        parser = argparse.ArgumentParser()
        add_no_destroy_argument(parser)
        args = parser.parse_args(["--no-destroy"])
        assert args.no_destroy is True


class TestOutputArguments:
    """Tests for add_output_arguments."""

    def test_output_defaults_false(self) -> None:
        parser = argparse.ArgumentParser()
        add_output_arguments(parser)
        args = parser.parse_args([])
        assert args.show_results is False
        assert args.export_md is False

    def test_show_results_set(self) -> None:
        parser = argparse.ArgumentParser()
        add_output_arguments(parser)
        args = parser.parse_args(["--show-results"])
        assert args.show_results is True

    def test_export_md_set(self) -> None:
        parser = argparse.ArgumentParser()
        add_output_arguments(parser)
        args = parser.parse_args(["--export-md"])
        assert args.export_md is True


class TestBenchmarkVmArgument:
    """Tests for add_benchmark_vm_argument."""

    def test_benchmark_vm_default_none(self) -> None:
        parser = argparse.ArgumentParser()
        add_benchmark_vm_argument(parser)
        args = parser.parse_args([])
        assert args.benchmark_vm_ip is None

    def test_benchmark_vm_explicit(self) -> None:
        parser = argparse.ArgumentParser()
        add_benchmark_vm_argument(parser)
        args = parser.parse_args(["--benchmark-vm-ip", "192.168.1.1"])
        assert args.benchmark_vm_ip == "192.168.1.1"


class TestStudyNameArgument:
    """Tests for add_study_name_argument."""

    def test_study_name_default_none(self) -> None:
        parser = argparse.ArgumentParser()
        add_study_name_argument(parser, "redis")
        args = parser.parse_args([])
        assert args.study_name is None

    def test_study_name_explicit(self) -> None:
        parser = argparse.ArgumentParser()
        add_study_name_argument(parser, "redis")
        args = parser.parse_args(["--study-name", "my-study"])
        assert args.study_name == "my-study"


class TestModeArgument:
    """Tests for add_mode_argument."""

    def test_mode_default(self) -> None:
        parser = argparse.ArgumentParser()
        add_mode_argument(parser)
        args = parser.parse_args([])
        assert args.mode == "config"

    def test_mode_custom_default(self) -> None:
        parser = argparse.ArgumentParser()
        add_mode_argument(parser, default="infra")
        args = parser.parse_args([])
        assert args.mode == "infra"

    def test_mode_explicit(self) -> None:
        parser = argparse.ArgumentParser()
        add_mode_argument(parser)
        args = parser.parse_args(["--mode", "full"])
        assert args.mode == "full"

    def test_mode_short_form(self) -> None:
        parser = argparse.ArgumentParser()
        add_mode_argument(parser)
        args = parser.parse_args(["-m", "infra"])
        assert args.mode == "infra"

    def test_mode_invalid_choice(self) -> None:
        parser = argparse.ArgumentParser()
        add_mode_argument(parser)
        with pytest.raises(SystemExit):
            parser.parse_args(["--mode", "invalid"])


class TestFixedHostArguments:
    """Tests for add_fixed_host_arguments."""

    def test_defaults(self) -> None:
        parser = argparse.ArgumentParser()
        add_fixed_host_arguments(parser)
        args = parser.parse_args([])
        assert args.cpu == 4
        assert args.ram == 8

    def test_custom_defaults(self) -> None:
        parser = argparse.ArgumentParser()
        add_fixed_host_arguments(parser, cpu_default=8, ram_default=32)
        args = parser.parse_args([])
        assert args.cpu == 8
        assert args.ram == 32

    def test_explicit_values(self) -> None:
        parser = argparse.ArgumentParser()
        add_fixed_host_arguments(parser)
        args = parser.parse_args(["--cpu", "16", "--ram", "64"])
        assert args.cpu == 16
        assert args.ram == 64


class TestCommonArguments:
    """Tests for add_common_arguments."""

    def test_minimal_args(self) -> None:
        parser = argparse.ArgumentParser()
        metrics = {"tps": None, "latency": None}
        add_common_arguments(parser, metrics=metrics, default_metric="tps")
        args = parser.parse_args(["--cloud", "selectel"])
        assert args.cloud == "selectel"
        assert args.metric == "tps"
        assert args.trials == 10
        assert args.no_destroy is False
        assert args.show_results is False
        assert args.export_md is False

    def test_with_mode(self) -> None:
        parser = argparse.ArgumentParser()
        metrics = {"tps": None}
        add_common_arguments(
            parser, metrics=metrics, default_metric="tps", with_mode=True
        )
        args = parser.parse_args(["--cloud", "selectel"])
        assert args.mode == "config"

    def test_with_fixed_host(self) -> None:
        parser = argparse.ArgumentParser()
        metrics = {"tps": None}
        add_common_arguments(
            parser,
            metrics=metrics,
            default_metric="tps",
            with_fixed_host=True,
            cpu_default=8,
            ram_default=16,
        )
        args = parser.parse_args(["--cloud", "selectel"])
        assert args.cpu == 8
        assert args.ram == 16

    def test_with_study_prefix(self) -> None:
        parser = argparse.ArgumentParser()
        metrics = {"tps": None}
        add_common_arguments(
            parser, metrics=metrics, default_metric="tps", study_prefix="redis"
        )
        args = parser.parse_args(["--cloud", "selectel"])
        assert args.study_name is None

    def test_without_benchmark_vm(self) -> None:
        parser = argparse.ArgumentParser()
        metrics = {"tps": None}
        add_common_arguments(
            parser, metrics=metrics, default_metric="tps", with_benchmark_vm=False
        )
        args = parser.parse_args(["--cloud", "selectel"])
        assert not hasattr(args, "benchmark_vm_ip")

    def test_full_configuration(self) -> None:
        parser = argparse.ArgumentParser()
        metrics = {"tps": None, "latency": None, "cost_efficiency": None}
        add_common_arguments(
            parser,
            metrics=metrics,
            default_metric="tps",
            default_trials=20,
            study_prefix="postgres",
            with_mode=True,
            mode_default="infra",
            with_fixed_host=True,
            cpu_default=4,
            ram_default=16,
            with_benchmark_vm=True,
        )
        args = parser.parse_args(
            [
                "--cloud",
                "timeweb",
                "--metric",
                "cost_efficiency",
                "--trials",
                "50",
                "--mode",
                "full",
                "--cpu",
                "8",
                "--ram",
                "32",
                "--benchmark-vm-ip",
                "10.0.0.1",
                "--study-name",
                "my-study",
                "--no-destroy",
                "--show-results",
            ]
        )
        assert args.cloud == "timeweb"
        assert args.metric == "cost_efficiency"
        assert args.trials == 50
        assert args.mode == "full"
        assert args.cpu == 8
        assert args.ram == 32
        assert args.benchmark_vm_ip == "10.0.0.1"
        assert args.study_name == "my-study"
        assert args.no_destroy is True
        assert args.show_results is True

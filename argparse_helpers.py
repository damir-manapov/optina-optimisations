"""Common argparse argument definitions for optimizers."""

import argparse
from typing import Any


def add_cloud_argument(parser: argparse.ArgumentParser) -> None:
    """Add --cloud argument to parser."""
    parser.add_argument(
        "--cloud",
        "-c",
        choices=["selectel", "timeweb"],
        required=True,
        help="Cloud provider",
    )


def add_metric_argument(
    parser: argparse.ArgumentParser,
    choices: list[str],
    default: str,
) -> None:
    """Add --metric argument to parser."""
    parser.add_argument(
        "--metric",
        choices=choices,
        default=default,
        help=f"Metric to optimize (default: {default})",
    )


def add_trials_argument(
    parser: argparse.ArgumentParser,
    default: int = 10,
) -> None:
    """Add --trials argument to parser."""
    parser.add_argument(
        "--trials",
        "-t",
        type=int,
        default=default,
        help=f"Number of trials (default: {default})",
    )


def add_no_destroy_argument(parser: argparse.ArgumentParser) -> None:
    """Add --no-destroy argument to parser."""
    parser.add_argument(
        "--no-destroy",
        action="store_true",
        help="Keep infrastructure after optimization",
    )


def add_output_arguments(parser: argparse.ArgumentParser) -> None:
    """Add --show-results and --export-md arguments to parser."""
    parser.add_argument(
        "--show-results",
        action="store_true",
        help="Show all benchmark results and exit",
    )
    parser.add_argument(
        "--export-md",
        action="store_true",
        help="Export results to markdown file and exit",
    )


def add_benchmark_vm_argument(parser: argparse.ArgumentParser) -> None:
    """Add --benchmark-vm-ip argument to parser."""
    parser.add_argument(
        "--benchmark-vm-ip",
        default=None,
        help="Benchmark VM IP (auto-created if not provided)",
    )


def add_study_name_argument(
    parser: argparse.ArgumentParser,
    prefix: str,
) -> None:
    """Add --study-name argument to parser."""
    parser.add_argument(
        "--study-name",
        default=None,
        help=f"Optuna study name (default: {prefix}-{{cloud}}-{{metric}})",
    )


def add_mode_argument(
    parser: argparse.ArgumentParser,
    default: str = "config",
) -> None:
    """Add --mode argument to parser."""
    parser.add_argument(
        "--mode",
        "-m",
        choices=["infra", "config", "full"],
        default=default,
        help=f"Optimization mode (default: {default})",
    )


def add_fixed_host_arguments(
    parser: argparse.ArgumentParser,
    cpu_default: int = 4,
    ram_default: int = 8,
) -> None:
    """Add --cpu and --ram arguments for fixed host in config mode."""
    parser.add_argument(
        "--cpu",
        type=int,
        default=cpu_default,
        help=f"CPU cores for config mode (default: {cpu_default})",
    )
    parser.add_argument(
        "--ram",
        type=int,
        default=ram_default,
        help=f"RAM GB for config mode (default: {ram_default})",
    )


def add_common_arguments(
    parser: argparse.ArgumentParser,
    *,
    metrics: dict[str, Any],
    default_metric: str,
    default_trials: int = 10,
    study_prefix: str | None = None,
    with_mode: bool = False,
    mode_default: str = "config",
    with_fixed_host: bool = False,
    cpu_default: int = 4,
    ram_default: int = 8,
    with_benchmark_vm: bool = True,
) -> None:
    """Add all common arguments to parser.

    Args:
        parser: ArgumentParser instance
        metrics: Dict of metric configs (METRICS from service)
        default_metric: Default metric name
        default_trials: Default number of trials
        study_prefix: Prefix for study name (e.g., 'redis', 'minio')
        with_mode: Include --mode argument
        mode_default: Default mode value
        with_fixed_host: Include --cpu and --ram arguments
        cpu_default: Default CPU cores
        ram_default: Default RAM GB
        with_benchmark_vm: Include --benchmark-vm-ip argument
    """
    add_cloud_argument(parser)
    add_metric_argument(parser, list(metrics.keys()), default_metric)
    add_trials_argument(parser, default_trials)

    if with_mode:
        add_mode_argument(parser, mode_default)

    if with_fixed_host:
        add_fixed_host_arguments(parser, cpu_default, ram_default)

    if with_benchmark_vm:
        add_benchmark_vm_argument(parser)

    if study_prefix:
        add_study_name_argument(parser, study_prefix)

    add_no_destroy_argument(parser)
    add_output_arguments(parser)

"""Common argparse argument definitions for optimizers.

This module provides reusable argument definitions for optimizer CLIs,
ensuring consistent argument names, defaults, and help text across all
service optimizers (Redis, MinIO, PostgreSQL, Meilisearch).

Example usage::

    from argparse_helpers import add_common_arguments

    parser = argparse.ArgumentParser(description="Redis optimizer")
    add_common_arguments(
        parser,
        metrics=METRICS,
        default_metric="ops_per_sec",
        study_prefix="redis",
        with_mode=True,
        with_fixed_host=True,
    )
    args = parser.parse_args()
"""

import argparse
from typing import Any


def add_cloud_argument(parser: argparse.ArgumentParser) -> None:
    """Add --cloud/-c argument to parser.

    Adds required cloud provider selection. Currently supports 'selectel'
    and 'timeweb' providers.

    Example:
        >>> parser = argparse.ArgumentParser()
        >>> add_cloud_argument(parser)
        >>> args = parser.parse_args(["--cloud", "selectel"])
        >>> args.cloud
        'selectel'
    """
    parser.add_argument(
        "--cloud",
        "-c",
        choices=["selectel", "timeweb"],
        required=True,
        help="Cloud provider",
    )


def add_login_argument(parser: argparse.ArgumentParser) -> None:
    """Add --login/-l argument to parser.

    Adds required login/username for tracking who ran the trial.

    Example:
        >>> parser = argparse.ArgumentParser()
        >>> add_login_argument(parser)
        >>> args = parser.parse_args(["--login", "damir"])
        >>> args.login
        'damir'
    """
    parser.add_argument(
        "--login",
        "-l",
        required=True,
        help="Your login/username for tracking trial ownership",
    )


def add_metric_argument(
    parser: argparse.ArgumentParser,
    choices: list[str],
    default: str,
) -> None:
    """Add --metric argument to parser.

    Args:
        parser: ArgumentParser instance to add argument to.
        choices: List of valid metric names (e.g., ['ops_per_sec', 'latency']).
        default: Default metric to optimize.

    Example:
        >>> parser = argparse.ArgumentParser()
        >>> add_metric_argument(parser, ["ops_per_sec", "latency"], "ops_per_sec")
        >>> args = parser.parse_args([])
        >>> args.metric
        'ops_per_sec'
    """
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
    """Add --trials/-t argument to parser.

    Args:
        parser: ArgumentParser instance to add argument to.
        default: Default number of optimization trials.

    Example:
        >>> parser = argparse.ArgumentParser()
        >>> add_trials_argument(parser, default=50)
        >>> args = parser.parse_args(["-t", "100"])
        >>> args.trials
        100
    """
    parser.add_argument(
        "--trials",
        "-t",
        type=int,
        default=default,
        help=f"Number of trials (default: {default})",
    )


def add_no_destroy_argument(parser: argparse.ArgumentParser) -> None:
    """Add --no-destroy argument to parser.

    When set, keeps the infrastructure running after optimization completes.
    Useful for debugging or manual inspection of the deployed system.

    Example:
        >>> parser = argparse.ArgumentParser()
        >>> add_no_destroy_argument(parser)
        >>> args = parser.parse_args(["--no-destroy"])
        >>> args.no_destroy
        True
    """
    parser.add_argument(
        "--no-destroy",
        action="store_true",
        help="Keep infrastructure after optimization",
    )


def add_output_arguments(parser: argparse.ArgumentParser) -> None:
    """Add --show-results and --export-md arguments to parser.

    These arguments control result display without running optimization:
    - --show-results: Print formatted table of all results to stdout
    - --export-md: Export results to a markdown file

    Example:
        >>> parser = argparse.ArgumentParser()
        >>> add_output_arguments(parser)
        >>> args = parser.parse_args(["--show-results"])
        >>> args.show_results
        True
    """
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
    """Add --benchmark-vm-ip argument to parser.

    Allows specifying an existing benchmark VM IP instead of creating a new one.
    When not provided, a benchmark VM will be auto-created via Terraform.

    Example:
        >>> parser = argparse.ArgumentParser()
        >>> add_benchmark_vm_argument(parser)
        >>> args = parser.parse_args(["--benchmark-vm-ip", "192.168.1.100"])
        >>> args.benchmark_vm_ip
        '192.168.1.100'
    """
    parser.add_argument(
        "--benchmark-vm-ip",
        default=None,
        help="Benchmark VM IP (auto-created if not provided)",
    )


def add_study_name_argument(
    parser: argparse.ArgumentParser,
    prefix: str,
) -> None:
    """Add --study-name argument to parser.

    Allows overriding the default Optuna study name. The default format
    is '{prefix}-{cloud}-{metric}'.

    Args:
        parser: ArgumentParser instance to add argument to.
        prefix: Service prefix (e.g., 'redis', 'minio', 'postgres').

    Example:
        >>> parser = argparse.ArgumentParser()
        >>> add_study_name_argument(parser, "redis")
        >>> args = parser.parse_args(["--study-name", "my-custom-study"])
        >>> args.study_name
        'my-custom-study'
    """
    parser.add_argument(
        "--study-name",
        default=None,
        help=f"Optuna study name (default: {prefix}-{{cloud}}-{{metric}})",
    )


def add_mode_argument(
    parser: argparse.ArgumentParser,
    default: str = "config",
) -> None:
    """Add --mode/-m argument to parser.

    Optimization modes:
    - 'infra': Optimize infrastructure (CPU, RAM, disk) with fixed config
    - 'config': Optimize service config on fixed infrastructure
    - 'full': Optimize both infrastructure and config together

    Args:
        parser: ArgumentParser instance to add argument to.
        default: Default optimization mode.

    Example:
        >>> parser = argparse.ArgumentParser()
        >>> add_mode_argument(parser, default="full")
        >>> args = parser.parse_args(["-m", "infra"])
        >>> args.mode
        'infra'
    """
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
    """Add --cpu and --ram arguments for fixed host in config mode.

    These arguments specify the infrastructure to use when running in
    'config' mode, where only service configuration is optimized.

    Args:
        parser: ArgumentParser instance to add argument to.
        cpu_default: Default number of CPU cores.
        ram_default: Default RAM in GB.

    Example:
        >>> parser = argparse.ArgumentParser()
        >>> add_fixed_host_arguments(parser, cpu_default=8, ram_default=16)
        >>> args = parser.parse_args(["--cpu", "4", "--ram", "8"])
        >>> args.cpu, args.ram
        (4, 8)
    """
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
    """Add all common arguments to an optimizer parser.

    This is the main entry point for setting up optimizer CLI arguments.
    It combines all individual argument functions into a single call with
    sensible defaults and optional features.

    Args:
        parser: ArgumentParser instance to add arguments to.
        metrics: Dict of metric configs (METRICS from service metrics.py).
        default_metric: Default metric name to optimize.
        default_trials: Default number of optimization trials.
        study_prefix: Prefix for study name (e.g., 'redis', 'minio').
            When provided, adds --study-name argument.
        with_mode: Include --mode argument for optimization mode selection.
        mode_default: Default mode when with_mode is True.
        with_fixed_host: Include --cpu and --ram arguments for config mode.
        cpu_default: Default CPU cores when with_fixed_host is True.
        ram_default: Default RAM GB when with_fixed_host is True.
        with_benchmark_vm: Include --benchmark-vm-ip argument.

    Example::

        # Minimal setup (e.g., for PostgreSQL/Meilisearch)
        add_common_arguments(
            parser,
            metrics=METRICS,
            default_metric="tps",
            study_prefix="postgres",
        )

        # Full setup with mode (e.g., for Redis/MinIO)
        add_common_arguments(
            parser,
            metrics=METRICS,
            default_metric="ops_per_sec",
            study_prefix="redis",
            with_mode=True,
            mode_default="config",
            with_fixed_host=True,
            cpu_default=4,
            ram_default=8,
        )

    This adds the following arguments:
        - ``--cloud/-c``: Required cloud provider selection
        - ``--metric``: Metric to optimize
        - ``--trials/-t``: Number of optimization trials
        - ``--mode/-m``: Optimization mode (if with_mode=True)
        - ``--cpu``, ``--ram``: Fixed host config (if with_fixed_host=True)
        - ``--benchmark-vm-ip``: External benchmark VM (if with_benchmark_vm=True)
        - ``--study-name``: Custom study name (if study_prefix provided)
        - ``--no-destroy``: Keep infrastructure after optimization
        - ``--show-results``: Display results table and exit
        - ``--export-md``: Export results to markdown and exit
    """
    add_cloud_argument(parser)
    add_login_argument(parser)
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

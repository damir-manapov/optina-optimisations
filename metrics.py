"""Metric configuration for optimizers.

Centralized metric definitions with direction, units, and descriptions.
This ensures consistent metric handling across all optimizers.
"""

from dataclasses import dataclass
from enum import Enum


class Direction(Enum):
    """Optimization direction."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


@dataclass(frozen=True)
class MetricConfig:
    """Configuration for an optimization metric."""

    name: str  # Metric key in results (e.g., "ops_per_sec")
    description: str  # Human-readable description
    direction: Direction  # Whether to maximize or minimize
    unit: str  # Unit for display (e.g., "ops/s", "ms")
    format_spec: str = ".2f"  # Format specifier for display

    @property
    def direction_str(self) -> str:
        """Get direction as string for Optuna."""
        return self.direction.value

    def format_value(self, value: float) -> str:
        """Format value with unit."""
        return f"{value:{self.format_spec}} {self.unit}"


# =============================================================================
# Redis Metrics
# =============================================================================

REDIS_METRICS: dict[str, MetricConfig] = {
    "ops_per_sec": MetricConfig(
        name="ops_per_sec",
        description="Operations per second",
        direction=Direction.MAXIMIZE,
        unit="ops/s",
        format_spec=".0f",
    ),
    "p99_latency_ms": MetricConfig(
        name="p99_latency_ms",
        description="99th percentile latency",
        direction=Direction.MINIMIZE,
        unit="ms",
        format_spec=".2f",
    ),
    "cost_efficiency": MetricConfig(
        name="cost_efficiency",
        description="Operations per dollar per hour",
        direction=Direction.MAXIMIZE,
        unit="ops/$/hr",
        format_spec=".0f",
    ),
}


# =============================================================================
# MinIO Metrics
# =============================================================================

MINIO_METRICS: dict[str, MetricConfig] = {
    "total_mib_s": MetricConfig(
        name="total_mib_s",
        description="Total throughput",
        direction=Direction.MAXIMIZE,
        unit="MiB/s",
        format_spec=".1f",
    ),
    "get_mib_s": MetricConfig(
        name="get_mib_s",
        description="Read throughput",
        direction=Direction.MAXIMIZE,
        unit="MiB/s",
        format_spec=".1f",
    ),
    "put_mib_s": MetricConfig(
        name="put_mib_s",
        description="Write throughput",
        direction=Direction.MAXIMIZE,
        unit="MiB/s",
        format_spec=".1f",
    ),
    "cost_efficiency": MetricConfig(
        name="cost_efficiency",
        description="Throughput per cost",
        direction=Direction.MAXIMIZE,
        unit="MiB/s/$/hr",
        format_spec=".1f",
    ),
}


# =============================================================================
# PostgreSQL Metrics
# =============================================================================

POSTGRES_METRICS: dict[str, MetricConfig] = {
    "tps": MetricConfig(
        name="tps",
        description="Transactions per second",
        direction=Direction.MAXIMIZE,
        unit="TPS",
        format_spec=".0f",
    ),
    "latency_avg_ms": MetricConfig(
        name="latency_avg_ms",
        description="Average latency",
        direction=Direction.MINIMIZE,
        unit="ms",
        format_spec=".2f",
    ),
    "cost_efficiency": MetricConfig(
        name="cost_efficiency",
        description="TPS per dollar per hour",
        direction=Direction.MAXIMIZE,
        unit="TPS/$/hr",
        format_spec=".0f",
    ),
}


# =============================================================================
# Meilisearch Metrics
# =============================================================================

MEILISEARCH_METRICS: dict[str, MetricConfig] = {
    "qps": MetricConfig(
        name="qps",
        description="Queries per second",
        direction=Direction.MAXIMIZE,
        unit="QPS",
        format_spec=".0f",
    ),
    "p95_ms": MetricConfig(
        name="p95_ms",
        description="95th percentile latency",
        direction=Direction.MINIMIZE,
        unit="ms",
        format_spec=".2f",
    ),
    "indexing_time": MetricConfig(
        name="indexing_time",
        description="Indexing time",
        direction=Direction.MINIMIZE,
        unit="s",
        format_spec=".1f",
    ),
    "cost_efficiency": MetricConfig(
        name="cost_efficiency",
        description="QPS per ruble per month",
        direction=Direction.MAXIMIZE,
        unit="QPS/₽/mo",
        format_spec=".2f",
    ),
}


# =============================================================================
# Helper functions
# =============================================================================


def get_metrics_for_service(service: str) -> dict[str, MetricConfig]:
    """Get metrics configuration for a service."""
    metrics_map = {
        "redis": REDIS_METRICS,
        "minio": MINIO_METRICS,
        "postgres": POSTGRES_METRICS,
        "meilisearch": MEILISEARCH_METRICS,
    }
    if service not in metrics_map:
        raise ValueError(
            f"Unknown service: {service}. Available: {list(metrics_map.keys())}"
        )
    return metrics_map[service]


def get_metric_choices(service: str) -> list[str]:
    """Get list of valid metric names for argparse choices."""
    return list(get_metrics_for_service(service).keys())


def get_metric_help(service: str) -> str:
    """Generate help text for --metric argument."""
    metrics = get_metrics_for_service(service)
    parts = [f"{name}={cfg.description}" for name, cfg in metrics.items()]
    return f"Metric to optimize ({', '.join(parts)})"


def get_optuna_direction(service: str, metric: str) -> str:
    """Get Optuna direction string for a metric."""
    metrics = get_metrics_for_service(service)
    if metric not in metrics:
        raise ValueError(f"Unknown metric '{metric}' for {service}")
    return metrics[metric].direction_str

"""Meilisearch optimizer metrics configuration."""

from metrics import Direction, MetricConfig

METRICS: dict[str, MetricConfig] = {
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


def get_metric_choices() -> list[str]:
    """Get list of valid metric names for argparse choices."""
    return list(METRICS.keys())


def get_metric_help() -> str:
    """Generate help text for --metric argument."""
    parts = [f"{name}={cfg.description}" for name, cfg in METRICS.items()]
    return f"Metric to optimize ({', '.join(parts)})"

"""PostgreSQL optimizer metrics configuration."""

from metrics import Direction, MetricConfig

METRICS: dict[str, MetricConfig] = {
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


def get_metric_choices() -> list[str]:
    """Get list of valid metric names for argparse choices."""
    return list(METRICS.keys())


def get_metric_help() -> str:
    """Generate help text for --metric argument."""
    parts = [f"{name}={cfg.description}" for name, cfg in METRICS.items()]
    return f"Metric to optimize ({', '.join(parts)})"

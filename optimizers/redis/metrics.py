"""Redis optimizer metrics configuration."""

from metrics import Direction, MetricConfig

METRICS: dict[str, MetricConfig] = {
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

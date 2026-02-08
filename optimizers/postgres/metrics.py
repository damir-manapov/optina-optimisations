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

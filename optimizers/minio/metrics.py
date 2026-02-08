"""MinIO optimizer metrics configuration."""

from metrics import Direction, MetricConfig

METRICS: dict[str, MetricConfig] = {
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

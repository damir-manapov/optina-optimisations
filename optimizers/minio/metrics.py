"""MinIO optimizer metrics configuration."""

from metrics import Direction, MetricConfig
from pricing import CostExtractorConfig, make_cost_extractor

_COST_CONFIG = CostExtractorConfig(
    metric_key="total_mib_s",
    config_key="config",
    cpu_key="cpu_per_node",
    ram_key="ram_per_node",
    disk_size_key="drive_size_gb",
    disk_type_key="drive_type",
    default_disk_size=50,
    default_disk_type="fast",
    nodes_key="nodes",
    drives_per_node_key="drives_per_node",
)

_calc_cost_efficiency = make_cost_extractor(_COST_CONFIG)


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
        description="Throughput per ruble per month",
        direction=Direction.MAXIMIZE,
        unit="MiB/s/₽/mo",
        format_spec=".4f",
        extractor=_calc_cost_efficiency,
    ),
}

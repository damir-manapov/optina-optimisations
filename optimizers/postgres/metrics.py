"""PostgreSQL optimizer metrics configuration."""

from metrics import Direction, MetricConfig
from pricing import CostExtractorConfig, make_cost_extractor

_COST_CONFIG = CostExtractorConfig(
    metric_key="tps",
    config_key="infra_config",
    cpu_key="cpu",
    ram_key="ram_gb",
    disk_size_key="disk_size_gb",
    disk_type_key="disk_type",
    default_disk_size=50,
    default_disk_type="fast",
)

_calc_cost_efficiency = make_cost_extractor(_COST_CONFIG)


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
        description="TPS per ruble per month",
        direction=Direction.MAXIMIZE,
        unit="TPS/₽/mo",
        format_spec=".2f",
        extractor=_calc_cost_efficiency,
    ),
}

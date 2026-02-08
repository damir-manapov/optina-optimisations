"""Meilisearch optimizer metrics configuration."""

from metrics import Direction, MetricConfig
from pricing import CostExtractorConfig, make_cost_extractor

_COST_CONFIG = CostExtractorConfig(
    metric_key="qps",
    config_key="infra",
    cpu_key="cpu",
    ram_key="ram_gb",
    disk_size_key="disk_size_gb",
    disk_type_key="disk_type",
    default_disk_size=50,
    default_disk_type="fast",
)

_calc_cost_efficiency = make_cost_extractor(_COST_CONFIG)


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
        result_key="indexing_time_s",  # Uses different key in results
    ),
    "cost_efficiency": MetricConfig(
        name="cost_efficiency",
        description="QPS per ruble per month",
        direction=Direction.MAXIMIZE,
        unit="QPS/₽/mo",
        format_spec=".2f",
        extractor=_calc_cost_efficiency,  # Calculated from qps and infra
    ),
}

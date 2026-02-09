"""Trino-Iceberg optimizer metrics configuration."""

from metrics import Direction, MetricConfig
from pricing import CostExtractorConfig, make_cost_extractor

_COST_CONFIG = CostExtractorConfig(
    metric_key="lookups_per_sec",
    config_key="infra_config",
    cpu_key="cpu",
    ram_key="ram_gb",
    disk_size_key="disk_size_gb",
    disk_type_key="disk_type",
    default_disk_size=100,
    default_disk_type="fast",
)

_calc_cost_efficiency = make_cost_extractor(_COST_CONFIG)


METRICS: dict[str, MetricConfig] = {
    "lookups_per_sec": MetricConfig(
        name="lookups_per_sec",
        description="Point lookups per second (SELECT * WHERE id = ?)",
        direction=Direction.MAXIMIZE,
        unit="lookups/s",
        format_spec=".1f",
    ),
    "lookup_p50_ms": MetricConfig(
        name="lookup_p50_ms",
        description="Median lookup latency",
        direction=Direction.MINIMIZE,
        unit="ms",
        format_spec=".2f",
    ),
    "lookup_p95_ms": MetricConfig(
        name="lookup_p95_ms",
        description="95th percentile lookup latency",
        direction=Direction.MINIMIZE,
        unit="ms",
        format_spec=".2f",
    ),
    "lookup_p99_ms": MetricConfig(
        name="lookup_p99_ms",
        description="99th percentile lookup latency",
        direction=Direction.MINIMIZE,
        unit="ms",
        format_spec=".2f",
    ),
    "cost_efficiency": MetricConfig(
        name="cost_efficiency",
        description="Lookups per ruble per month",
        direction=Direction.MAXIMIZE,
        unit="lookups/₽/mo",
        format_spec=".2f",
        extractor=_calc_cost_efficiency,
    ),
}

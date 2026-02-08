"""Redis optimizer metrics configuration."""

from metrics import Direction, MetricConfig
from pricing import CostExtractorConfig, make_cost_extractor

# Redis has mode-based nodes (single=1, sentinel=3)
# We handle this with a custom extractor that wraps the config-based one
_BASE_CONFIG = CostExtractorConfig(
    metric_key="ops_per_sec",
    config_key="config",
    cpu_key="cpu_per_node",
    ram_key="ram_per_node",
    default_disk_size=50,
    default_disk_type="fast",
    nodes_default=1,  # Will be overridden in wrapper
)


def _calc_cost_efficiency(result: dict, cloud: str = "selectel") -> float:
    """Calculate ops/sec per cost, handling Redis mode-based nodes."""
    config = result.get("config", {})
    nodes = 1 if config.get("mode") == "single" else 3
    # Inject nodes into result for the base extractor
    modified_result = {**result, "config": {**config, "_nodes": nodes}}
    # Use config with nodes_key pointing to our injected value
    cfg = CostExtractorConfig(
        metric_key="ops_per_sec",
        config_key="config",
        cpu_key="cpu_per_node",
        ram_key="ram_per_node",
        default_disk_size=50,
        default_disk_type="fast",
        nodes_key="_nodes",
    )
    return make_cost_extractor(cfg)(modified_result, cloud)


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
        description="Operations per ruble per month",
        direction=Direction.MAXIMIZE,
        unit="ops/₽/mo",
        format_spec=".0f",
        extractor=_calc_cost_efficiency,
    ),
}

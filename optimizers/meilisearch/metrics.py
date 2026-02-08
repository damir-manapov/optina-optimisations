"""Meilisearch optimizer metrics configuration."""

from typing import Any

from metrics import Direction, MetricConfig

# Import pricing for cost_efficiency calculation
# This creates a dependency, but keeps the metric logic centralized
from pricing import calculate_vm_cost, DiskConfig


def _calc_cost_efficiency(result: dict[str, Any], cloud: str = "selectel") -> float:
    """Calculate QPS per cost from result."""
    qps = result.get("qps", 0)
    infra = result.get("infra", {})
    if not infra:
        return 0
    cost = calculate_vm_cost(
        cloud=cloud,
        cpu=infra.get("cpu", 0),
        ram_gb=infra.get("ram_gb", 0),
        disks=[
            DiskConfig(
                size_gb=infra.get("disk_size_gb", 50),
                disk_type=infra.get("disk_type", "fast"),
            )
        ],
    )
    return qps / cost if cost > 0 else 0


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

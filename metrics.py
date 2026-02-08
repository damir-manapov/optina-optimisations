"""Base metric types for optimizers.

Contains Direction enum and MetricConfig dataclass.
Service-specific metrics are defined in each optimizer's metrics.py.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Direction(Enum):
    """Optimization direction."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


# Type alias for metric extractor functions
# Takes (result_dict, **kwargs) and returns the metric value
MetricExtractor = Callable[..., float]


@dataclass(frozen=True)
class MetricConfig:
    """Configuration for an optimization metric."""

    name: str  # Metric key in results (e.g., "ops_per_sec")
    description: str  # Human-readable description
    direction: Direction  # Whether to maximize or minimize
    unit: str  # Unit for display (e.g., "ops/s", "ms")
    format_spec: str = ".2f"  # Format specifier for display
    result_key: str | None = (
        None  # Alternate key in result dict (if different from name)
    )
    extractor: MetricExtractor | None = field(
        default=None, hash=False
    )  # Custom value extractor

    @property
    def direction_str(self) -> str:
        """Get direction as string for Optuna."""
        return self.direction.value

    def format_value(self, value: float) -> str:
        """Format value with unit."""
        return f"{value:{self.format_spec}} {self.unit}"

    def get_raw_value(self, result: dict[str, Any], **kwargs: Any) -> float:
        """Extract raw metric value from result dict.

        Uses extractor if provided, otherwise looks up result_key or name.
        Supports both nested metrics dict and top-level keys (legacy).
        """
        if self.extractor is not None:
            return self.extractor(result, **kwargs)
        key = self.result_key or self.name
        # Check nested metrics dict first, fallback to top-level for legacy
        metrics = result.get("metrics", {})
        if metrics and key in metrics:
            val = metrics.get(key, 0)
            return val if val is not None else 0
        val = result.get(key, 0)
        return val if val is not None else 0


def get_metric_value(
    result: dict,
    metric: str,
    metrics: dict[str, MetricConfig],
    **kwargs: Any,
) -> float:
    """Extract the optimization metric value from a result.

    For metrics that need minimization, returns negative value since
    Optuna always maximizes. Uses metric config to determine direction.

    Args:
        result: Dict containing metric values
        metric: Name of the metric to extract
        metrics: Service-specific METRICS dict
        **kwargs: Additional args passed to custom extractors (e.g., cloud)

    Returns:
        Metric value (negated if direction is MINIMIZE)
    """
    metric_config = metrics.get(metric)

    # Get raw value using config's extractor or key lookup
    if metric_config:
        value = metric_config.get_raw_value(result, **kwargs)
    else:
        value = result.get(metric, 0)

    # Apply direction-based negation for Optuna
    if metric_config and metric_config.direction == Direction.MINIMIZE:
        return -value if value else float("inf")
    return value

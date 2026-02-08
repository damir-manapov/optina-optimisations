"""Base metric types for optimizers.

Contains Direction enum and MetricConfig dataclass.
Service-specific metrics are defined in each optimizer's metrics.py.
"""

from dataclasses import dataclass
from enum import Enum


class Direction(Enum):
    """Optimization direction."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


@dataclass(frozen=True)
class MetricConfig:
    """Configuration for an optimization metric."""

    name: str  # Metric key in results (e.g., "ops_per_sec")
    description: str  # Human-readable description
    direction: Direction  # Whether to maximize or minimize
    unit: str  # Unit for display (e.g., "ops/s", "ms")
    format_spec: str = ".2f"  # Format specifier for display

    @property
    def direction_str(self) -> str:
        """Get direction as string for Optuna."""
        return self.direction.value

    def format_value(self, value: float) -> str:
        """Format value with unit."""
        return f"{value:{self.format_spec}} {self.unit}"

"""Trial storage module for benchmark results."""

from pathlib import Path

from .models import (
    FioMetrics,
    InfraConfig,
    ServiceType,
    SysbenchMetrics,
    SystemBaseline,
    Timings,
    Trial,
)
from .store import TrialStore

# Centralized results file at project root
RESULTS_FILE = Path(__file__).parent.parent / "results" / "results.json"


def get_store(service: ServiceType) -> TrialStore:
    """Get TrialStore for a service."""
    return TrialStore(RESULTS_FILE, service=service)


__all__ = [
    "FioMetrics",
    "InfraConfig",
    "RESULTS_FILE",
    "ServiceType",
    "SysbenchMetrics",
    "SystemBaseline",
    "Timings",
    "Trial",
    "TrialStore",
    "get_store",
]

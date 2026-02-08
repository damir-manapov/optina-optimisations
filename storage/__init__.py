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

# Centralized results directory at project root
RESULTS_DIR = Path(__file__).parent.parent / "results"


def get_results_path(service: ServiceType) -> Path:
    """Get path to results JSON file for a service."""
    return RESULTS_DIR / f"{service}.json"


def get_store(service: ServiceType) -> TrialStore:
    """Get TrialStore for a service."""
    return TrialStore(get_results_path(service), service=service)


__all__ = [
    "FioMetrics",
    "InfraConfig",
    "RESULTS_DIR",
    "ServiceType",
    "SysbenchMetrics",
    "SystemBaseline",
    "Timings",
    "Trial",
    "TrialStore",
    "get_results_path",
    "get_store",
]

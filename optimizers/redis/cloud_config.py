"""Cloud configuration for Redis optimizer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Re-export from common module
from cloud_config import CloudConfig, get_cloud_config

__all__ = ["CloudConfig", "get_cloud_config", "get_config_space"]


def get_config_space(cloud: str) -> dict:
    """Get configuration search space for a cloud."""
    # Common config space for Redis
    return {
        "mode": ["single", "sentinel"],
        "cpu_per_node": [2, 4, 8],
        "ram_per_node": [4, 8, 16, 32],
        "maxmemory_policy": ["allkeys-lru", "volatile-lru"],
        "io_threads": [1, 2, 4],
        "persistence": ["none", "rdb"],
    }

"""Cloud configuration for Trino-Iceberg optimizer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Re-export from common module
from cloud_config import CloudConfig, get_cloud_config

__all__ = [
    "CloudConfig",
    "get_cloud_config",
    "get_infra_search_space",
    "get_config_search_space",
]


def get_infra_search_space(cloud: str) -> dict:
    """Get infrastructure search space (VM specs).

    Trino-Iceberg stack consists of:
    - Trino coordinator+worker (can be same node for single mode)
    - Nessie catalog server
    - PostgreSQL for Nessie metadata

    For simplicity, we optimize single-node Trino with co-located services.
    """
    return {
        "cpu": [2, 4, 8, 16],
        "ram_gb": [8, 16, 32, 64],  # Trino needs more RAM
        "disk_type": ["nvme"] if cloud == "timeweb" else ["fast"],
        "disk_size_gb": [100, 200, 400],  # Iceberg tables can be large
    }


def get_config_search_space() -> dict:
    """Get Trino + Iceberg configuration search space.

    Parameters that can be tuned without VM recreation.
    """
    return {
        # Trino JVM settings
        "trino_heap_pct": [50, 60, 70, 80],  # % of RAM for JVM heap
        "trino_query_max_memory_pct": [30, 40, 50],  # % of heap for single query
        # Trino performance
        "task_concurrency": [4, 8, 16, 32],
        "task_writer_count": [1, 2, 4],
        # Iceberg table properties - compression
        "compression": ["zstd", "snappy", "lz4", "gzip", "none"],
        "compression_level": [1, 3, 6, 9],  # 1=fast, 9=best (for zstd/gzip)
        # Iceberg partitioning - sharding key determines data layout
        "partition_key": [
            "none",
            "category",
            "created_date",
            "id_bucket_16",
            "id_bucket_64",
        ],
        # Iceberg write settings
        "target_file_size_mb": [64, 128, 256, 512],
    }


# Valid compression levels per algorithm
COMPRESSION_LEVELS = {
    "zstd": [1, 3, 6, 9, 12, 15, 19],  # 1-19
    "gzip": [1, 3, 6, 9],  # 1-9
    "snappy": [1],  # No levels
    "lz4": [1],  # No levels
    "none": [1],  # No compression
}


def filter_compression_levels(compression: str, levels: list[int]) -> list[int]:
    """Filter compression levels to valid values for the algorithm."""
    valid = COMPRESSION_LEVELS.get(compression, [1])
    return [level for level in levels if level in valid] or [valid[0]]

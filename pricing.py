"""Cloud pricing configuration.

Centralized pricing rates for all optimizers.
Update this file when cloud provider prices change.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CloudPricing:
    """Pricing rates for a cloud provider."""

    cpu_cost: float  # Cost per vCPU per month (₽)
    ram_cost: float  # Cost per GB RAM per month (₽)
    disk_cost_multipliers: dict[str, float] = field(default_factory=dict)


# Cloud pricing rates in rubles (₽) per month
# Based on https://selectel.ru/prices/ and https://timeweb.cloud/
# Consistent across all optimizers
CLOUD_PRICING: dict[str, CloudPricing] = {
    "selectel": CloudPricing(
        # Standard Line pricing (ru-9 pool, Jan 2026)
        # Derived from calculator: 2vCPU/4GB = 2263₽, extrapolated
        cpu_cost=655,  # ₽/vCPU/month
        ram_cost=238,  # ₽/GB/month
        disk_cost_multipliers={
            # Selectel disk types: https://docs.selectel.ru/cloud-servers/volumes/about-network-volumes/
            "fast": 39,  # ₽/GB/month - SSD Fast (NVMe)
            "universal": 18,  # ₽/GB/month - SSD Universal
            "universal2": 9,  # ₽/GB/month - SSD Universal v2 (+ IOPS billing)
            "basicssd": 9,  # ₽/GB/month - SSD Basic
            "basic": 7,  # ₽/GB/month - HDD Basic
        },
    ),
    "timeweb": CloudPricing(
        # Timeweb Cloud pricing (Jan 2026)
        # Derived from fixed tariffs: 1vCPU/1GB=477₽, 1vCPU/2GB=657₽, 2vCPU/2GB=882₽
        cpu_cost=220,  # ₽/vCPU/month (estimated)
        ram_cost=180,  # ₽/GB/month (657-477=180 for 1GB)
        disk_cost_multipliers={
            "nvme": 5,  # ₽/GB/month (estimated from tariffs)
            "ssd": 4,  # ₽/GB/month
            "hdd": 2,  # ₽/GB/month
        },
    ),
}


def get_cloud_pricing(cloud: str) -> CloudPricing:
    """Get pricing rates for a cloud provider."""
    if cloud not in CLOUD_PRICING:
        raise ValueError(
            f"Unknown cloud: {cloud}. Available: {list(CLOUD_PRICING.keys())}"
        )
    return CLOUD_PRICING[cloud]


def get_disk_types(cloud: str) -> list[str]:
    """Get available disk types for a cloud provider.

    Disk types are derived from the disk_cost_multipliers keys.
    """
    return list(get_cloud_pricing(cloud).disk_cost_multipliers.keys())


# ============================================================================
# Cloud Constraints
# ============================================================================

# Minimum RAM (GB) required per vCPU count
# Based on cloud provider's Standard Line offerings
CLOUD_MIN_RAM: dict[str, dict[int, int]] = {
    "selectel": {
        # Selectel Standard Line constraints
        2: 2,  # 2 vCPU: min 2GB
        4: 4,  # 4 vCPU: min 4GB
        8: 8,  # 8 vCPU: min 8GB
        16: 32,  # 16 vCPU: min 32GB
        32: 64,  # 32 vCPU: min 64GB
    },
    "timeweb": {},  # No known constraints
}


def get_min_ram_for_cpu(cloud: str, cpu: int) -> int:
    """Get minimum RAM (GB) required for given CPU count."""
    constraints = CLOUD_MIN_RAM.get(cloud, {})
    return constraints.get(cpu, 0)


def validate_infra_config(cloud: str, cpu: int, ram_gb: int) -> str | None:
    """Validate infrastructure config against cloud constraints.

    Returns error message if invalid, None if valid.
    """
    min_ram = get_min_ram_for_cpu(cloud, cpu)
    if ram_gb < min_ram:
        return f"{cpu} vCPU requires min {min_ram}GB RAM on {cloud}"
    return None


def filter_valid_ram(cloud: str, cpu: int, ram_options: list[int]) -> list[int]:
    """Filter RAM options to only those valid for the given CPU count.

    Use this to constrain Optuna's search space before suggesting,
    rather than pruning invalid configs after the fact.
    """
    min_ram = get_min_ram_for_cpu(cloud, cpu)
    valid = [r for r in ram_options if r >= min_ram]
    # Fallback to all options if no constraints or empty result
    return valid if valid else ram_options


# ============================================================================
# Cost Calculation
# ============================================================================


@dataclass
class DiskConfig:
    """Disk configuration for cost calculation."""

    size_gb: int
    disk_type: str = "fast"
    count: int = 1  # Number of disks of this type


def calculate_vm_cost(
    cloud: str,
    cpu: int,
    ram_gb: int,
    disks: list[DiskConfig] | None = None,
    nodes: int = 1,
) -> float:
    """Calculate monthly cost for VM(s).

    Args:
        cloud: Cloud provider name
        cpu: vCPUs per node
        ram_gb: RAM in GB per node
        disks: List of disk configs per node (default: 50GB fast disk)
        nodes: Number of nodes (for clustered setups)

    Returns:
        Monthly cost in ₽
    """
    pricing = get_cloud_pricing(cloud)

    if disks is None:
        disks = [DiskConfig(size_gb=50, disk_type="fast")]

    cpu_cost = cpu * pricing.cpu_cost
    ram_cost = ram_gb * pricing.ram_cost

    disk_cost = 0.0
    for disk in disks:
        multiplier = pricing.disk_cost_multipliers.get(disk.disk_type, 0.01)
        disk_cost += disk.size_gb * disk.count * multiplier

    return nodes * (cpu_cost + ram_cost + disk_cost)


# ============================================================================
# Cost Efficiency Extractor Factory
# ============================================================================


@dataclass(frozen=True)
class CostExtractorConfig:
    """Configuration for creating a cost efficiency extractor.

    This allows declarative definition of how to extract cost efficiency
    from benchmark results, handling the variations between services.
    """

    metric_key: str  # Key for primary metric in result (ops_per_sec, tps, qps, etc.)
    config_key: str  # Key for config dict in result (config, infra_config, infra)
    cpu_key: str = "cpu"  # Key for CPU in config
    ram_key: str = "ram_gb"  # Key for RAM in config
    disk_size_key: str | None = None  # Key for disk size (None = use default)
    disk_type_key: str | None = None  # Key for disk type (None = use default)
    default_disk_size: int = 50
    default_disk_type: str = "fast"
    nodes_key: str | None = None  # Key for nodes count (None = use nodes_func)
    nodes_default: int = 1  # Default node count if no key/func
    # For services with complex node logic (e.g., Redis mode-based)
    drives_per_node_key: str | None = None  # For MinIO multi-drive setups


def make_cost_extractor(
    config: CostExtractorConfig,
) -> Callable[[dict[str, Any], str], float]:
    """Create a cost efficiency extractor function from config.

    The returned function has signature: (result: dict, cloud: str) -> float
    """

    def extractor(result: dict[str, Any], cloud: str = "selectel") -> float:
        # Get primary metric value
        metric_value = result.get(config.metric_key, 0)
        if not metric_value:
            return 0

        # Get config dict
        cfg = result.get(config.config_key, {})
        if not cfg:
            return 0

        # Extract CPU and RAM
        cpu = cfg.get(config.cpu_key, 0)
        ram_gb = cfg.get(config.ram_key, 0)

        # Extract disk config
        disk_size = (
            cfg.get(config.disk_size_key, config.default_disk_size)
            if config.disk_size_key
            else config.default_disk_size
        )
        disk_type = (
            cfg.get(config.disk_type_key, config.default_disk_type)
            if config.disk_type_key
            else config.default_disk_type
        )

        # Handle drives per node (MinIO)
        drives_count = (
            cfg.get(config.drives_per_node_key, 1) if config.drives_per_node_key else 1
        )

        # Build disk list
        disks = [DiskConfig(size_gb=disk_size, disk_type=disk_type, count=drives_count)]

        # Get node count
        nodes = (
            cfg.get(config.nodes_key, config.nodes_default)
            if config.nodes_key
            else config.nodes_default
        )

        # Calculate cost
        cost = calculate_vm_cost(
            cloud=cloud,
            cpu=cpu,
            ram_gb=ram_gb,
            disks=disks,
            nodes=nodes,
        )

        return metric_value / cost if cost > 0 else 0

    return extractor

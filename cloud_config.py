"""Base cloud configuration shared by all optimizers."""

from dataclasses import dataclass, field
from pathlib import Path

from pricing import get_cloud_pricing, get_disk_types

TERRAFORM_DIR = Path(__file__).parent / "terraform"


@dataclass
class CloudConfig:
    """Cloud provider configuration."""

    name: str
    terraform_dir: Path
    disk_types: list[str]
    cpu_cost: float  # Cost per vCPU per month
    ram_cost: float  # Cost per GB RAM per month
    disk_cost_multipliers: dict[str, float] = field(default_factory=dict)


def make_cloud_config(name: str, terraform_subdir: str | None = None) -> CloudConfig:
    """Create CloudConfig using common pricing.

    Args:
        name: Cloud provider name (selectel, timeweb)
        terraform_subdir: Terraform subdirectory, defaults to name
    """
    pricing = get_cloud_pricing(name)
    subdir = terraform_subdir or name
    return CloudConfig(
        name=name,
        terraform_dir=TERRAFORM_DIR / subdir,
        disk_types=get_disk_types(name),
        cpu_cost=pricing.cpu_cost,
        ram_cost=pricing.ram_cost,
        disk_cost_multipliers=pricing.disk_cost_multipliers,
    )


# Pre-built configs for common use
CLOUD_CONFIGS: dict[str, CloudConfig] = {
    "selectel": make_cloud_config("selectel"),
    "timeweb": make_cloud_config("timeweb"),
}


def get_cloud_config(cloud: str) -> CloudConfig:
    """Get cloud configuration by name."""
    if cloud not in CLOUD_CONFIGS:
        raise ValueError(
            f"Unknown cloud: {cloud}. Available: {list(CLOUD_CONFIGS.keys())}"
        )
    return CLOUD_CONFIGS[cloud]

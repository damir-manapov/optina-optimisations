"""Cloud provider configurations for the MinIO optimizer."""

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cloud_config import CloudConfig as BaseCloudConfig
from cloud_config import make_cloud_config


@dataclass
class MinIOCloudConfig(BaseCloudConfig):
    """Extended configuration for MinIO with terraform resource names."""

    # Terraform resource names for tainting
    instance_resource: str = ""
    boot_volume_resource: str | None = None
    data_volume_resource: str = ""
    network_port_resource: str | None = None


# Terraform resource mappings per cloud
_TERRAFORM_RESOURCES = {
    "selectel": {
        "instance_resource": "openstack_compute_instance_v2.minio",
        "boot_volume_resource": "openstack_blockstorage_volume_v3.minio_boot",
        "data_volume_resource": "openstack_blockstorage_volume_v3.minio_data",
        "network_port_resource": "openstack_networking_port_v2.minio",
    },
    "timeweb": {
        "instance_resource": "twc_server.minio",
        "boot_volume_resource": None,
        "data_volume_resource": "twc_server_disk.minio_data",
        "network_port_resource": None,
    },
}


def _make_minio_config(name: str) -> MinIOCloudConfig:
    """Create MinIOCloudConfig with terraform resources."""
    base = make_cloud_config(name)
    resources = _TERRAFORM_RESOURCES[name]
    return MinIOCloudConfig(
        name=base.name,
        terraform_dir=base.terraform_dir,
        disk_types=base.disk_types,
        cpu_cost=base.cpu_cost,
        ram_cost=base.ram_cost,
        disk_cost_multipliers=base.disk_cost_multipliers,
        instance_resource=resources["instance_resource"],
        boot_volume_resource=resources["boot_volume_resource"],
        data_volume_resource=resources["data_volume_resource"],
        network_port_resource=resources["network_port_resource"],
    )


# Alias for compatibility
CloudConfig = MinIOCloudConfig

CLOUD_CONFIGS: dict[str, MinIOCloudConfig] = {
    "selectel": _make_minio_config("selectel"),
    "timeweb": _make_minio_config("timeweb"),
}


def get_cloud_config(cloud: str) -> CloudConfig:
    """Get configuration for a cloud provider."""
    if cloud not in CLOUD_CONFIGS:
        raise ValueError(
            f"Unknown cloud: {cloud}. Available: {list(CLOUD_CONFIGS.keys())}"
        )
    return CLOUD_CONFIGS[cloud]


def get_config_space(cloud: str) -> dict:
    """Get configuration space for optimization."""
    config = get_cloud_config(cloud)

    return {
        "nodes": [1, 2, 3, 4],  # Reduced for cost control
        "cpu_per_node": [2, 4, 8],
        "ram_per_node": [4, 8, 16, 32],
        "drives_per_node": [1, 2, 3, 4],
        "drive_size_gb": [100, 200],
        "drive_type": config.disk_types,
    }

"""Pydantic models for trial data.

These models support the actual data structures used by each optimizer.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ============================================================================
# Infrastructure Config
# ============================================================================


class InfraConfig(BaseModel):
    """Infrastructure configuration for a VM."""

    cpu: int = Field(default=0, ge=0, description="Number of vCPUs")
    ram_gb: int = Field(default=0, ge=0, description="RAM in GB")
    disk_type: str = Field(default="", description="Disk type (e.g., 'fast', 'universal')")
    disk_size_gb: int = Field(default=0, ge=0, description="Disk size in GB")
    mode: str | None = Field(default=None, description="Cluster mode (PostgreSQL: single/replica)")


# ============================================================================
# Timings
# ============================================================================


class Timings(BaseModel):
    """Timing measurements for trial phases.

    All fields are optional since each service uses different timing fields.
    """

    # Common fields (all services)
    benchmark_s: float = Field(default=0.0, ge=0, description="Benchmark duration")
    trial_total_s: float = Field(default=0.0, ge=0, description="Total trial time")

    # Redis-specific
    redis_deploy_s: float = Field(default=0.0, ge=0, description="Redis deployment time")

    # MinIO-specific
    minio_deploy_s: float = Field(default=0.0, ge=0, description="MinIO deployment time")
    minio_destroy_s: float = Field(default=0.0, ge=0, description="MinIO destruction time")
    baseline_s: float = Field(default=0.0, ge=0, description="Baseline benchmarks (fio/sysbench)")

    # PostgreSQL-specific
    pg_ready_s: float = Field(default=0.0, ge=0, description="PostgreSQL ready time")
    pgbench_init_s: float = Field(default=0.0, ge=0, description="pgbench initialization time")

    # Meilisearch-specific
    meili_ready_s: float = Field(default=0.0, ge=0, description="Meilisearch ready time")
    dataset_gen_s: float = Field(default=0.0, ge=0, description="Dataset generation time")
    indexing_s: float = Field(default=0.0, ge=0, description="Indexing time")

    # Shared by PostgreSQL and Meilisearch
    terraform_s: float = Field(default=0.0, ge=0, description="Terraform apply time")
    vm_ready_s: float = Field(default=0.0, ge=0, description="VM cloud-init ready time")


# ============================================================================
# Baseline (MinIO-specific)
# ============================================================================


class FioMetrics(BaseModel):
    """FIO disk benchmark results."""

    rand_read_iops: float = Field(default=0.0, ge=0)
    rand_write_iops: float = Field(default=0.0, ge=0)
    rand_read_lat_ms: float = Field(default=0.0, ge=0)
    rand_write_lat_ms: float = Field(default=0.0, ge=0)
    seq_read_mib_s: float = Field(default=0.0, ge=0)
    seq_write_mib_s: float = Field(default=0.0, ge=0)


class SysbenchMetrics(BaseModel):
    """Sysbench CPU/memory benchmark results."""

    cpu_events_per_sec: float = Field(default=0.0, ge=0)
    mem_mib_per_sec: float = Field(default=0.0, ge=0)


class SystemBaseline(BaseModel):
    """Combined system baseline metrics (MinIO-specific)."""

    fio: FioMetrics | None = None
    sysbench: SysbenchMetrics | None = None


# ============================================================================
# Trial
# ============================================================================

ServiceType = Literal["meilisearch", "redis", "postgres", "minio"]


class Trial(BaseModel):
    """A single benchmark trial result.

    Supports all four service types with their specific config/metrics formats.
    """

    # Core fields
    id: int | None = Field(default=None, description="Auto-assigned trial ID")
    trial: int | None = Field(default=None, description="Trial number from optimizer")
    timestamp: datetime | str = Field(
        default_factory=datetime.now, description="When the trial was run"
    )
    service: ServiceType = Field(description="Service being benchmarked")
    cloud: str = Field(description="Cloud provider (e.g., 'selectel')")
    login: str | None = Field(default=None, description="User who ran the trial")

    # Infrastructure - each service uses different field names
    # Meilisearch uses "infra", PostgreSQL uses "infra_config"
    infra: InfraConfig | None = Field(default=None, description="Infra (Meilisearch)")
    infra_config: InfraConfig | None = Field(default=None, description="Infra (PostgreSQL)")

    # Service configuration - varies per service, stored as dict
    config: dict[str, Any] | None = Field(default=None, description="Redis/MinIO/Meilisearch config")
    pg_config: dict[str, Any] | None = Field(default=None, description="PostgreSQL config")

    # Redis metrics
    ops_per_sec: float | None = Field(default=None, ge=0)
    avg_latency_ms: float | None = Field(default=None, ge=0)
    p50_latency_ms: float | None = Field(default=None, ge=0)
    p99_latency_ms: float | None = Field(default=None, ge=0)
    p999_latency_ms: float | None = Field(default=None, ge=0)
    kb_per_sec: float | None = Field(default=None, ge=0)

    # Meilisearch metrics
    qps: float | None = Field(default=None, ge=0)
    p50_ms: float | None = Field(default=None, ge=0)
    p95_ms: float | None = Field(default=None, ge=0)
    p99_ms: float | None = Field(default=None, ge=0)
    error_rate: float | None = Field(default=None, ge=0)
    indexing_time_s: float | None = Field(default=None, ge=0)

    # PostgreSQL metrics
    tps: float | None = Field(default=None, ge=0)
    latency_avg_ms: float | None = Field(default=None, ge=0)
    latency_stddev_ms: float | None = Field(default=None, ge=0)
    transactions: int | None = Field(default=None, ge=0)

    # MinIO metrics
    total_mib_s: float | None = Field(default=None, ge=0)
    get_mib_s: float | None = Field(default=None, ge=0)
    put_mib_s: float | None = Field(default=None, ge=0)

    # Common fields
    duration_s: float | None = Field(default=None, ge=0)
    nodes: int | None = Field(default=None, ge=1)
    total_drives: int | None = Field(default=None, ge=1)
    mode: str | None = Field(default=None, description="Optimization mode (PostgreSQL)")

    # Error and timing
    error: str | None = Field(default=None, description="Error message if failed")
    timings: Timings | None = Field(default=None, description="Timing measurements")

    # MinIO-specific baseline
    system_baseline: SystemBaseline | None = Field(default=None, description="System baseline (MinIO)")

    def is_successful(self) -> bool:
        """Check if trial completed successfully."""
        if self.error is not None:
            return False
        if self.service == "redis":
            return (self.ops_per_sec or 0) > 0
        if self.service == "meilisearch":
            return (self.qps or 0) > 0
        if self.service == "postgres":
            return (self.tps or 0) > 0
        if self.service == "minio":
            return (self.total_mib_s or 0) > 0
        return False

    def get_primary_metric(self) -> float:
        """Get the primary performance metric for this service."""
        if self.service == "redis":
            return self.ops_per_sec or 0
        if self.service == "meilisearch":
            return self.qps or 0
        if self.service == "postgres":
            return self.tps or 0
        if self.service == "minio":
            return self.total_mib_s or 0
        return 0

    def get_config_key(self) -> dict[str, Any]:
        """Get config key dict for cache matching.

        Returns a dict of config values that uniquely identify this trial's
        configuration for caching purposes.
        """
        if self.service == "redis":
            cfg = self.config or {}
            return {
                "cloud": self.cloud,
                "mode": cfg.get("mode"),
                "cpu_per_node": cfg.get("cpu_per_node"),
                "ram_per_node": cfg.get("ram_per_node"),
                "maxmemory_policy": cfg.get("maxmemory_policy"),
                "io_threads": cfg.get("io_threads"),
                "persistence": cfg.get("persistence"),
            }
        if self.service == "minio":
            cfg = self.config or {}
            return {
                "cloud": self.cloud,
                "nodes": cfg.get("nodes"),
                "cpu_per_node": cfg.get("cpu_per_node"),
                "ram_per_node": cfg.get("ram_per_node"),
                "drives_per_node": cfg.get("drives_per_node"),
                "drive_size_gb": cfg.get("drive_size_gb"),
                "drive_type": cfg.get("drive_type"),
            }
        if self.service == "postgres":
            infra = self.infra_config.model_dump() if self.infra_config else {}
            return {
                "cloud": self.cloud,
                "infra": infra,
                "pg": self.pg_config,
            }
        if self.service == "meilisearch":
            infra = self.infra.model_dump() if self.infra else {}
            return {
                "cloud": self.cloud,
                "infra": infra,
                "config": self.config,
            }
        return {"cloud": self.cloud}

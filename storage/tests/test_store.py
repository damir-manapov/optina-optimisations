"""Tests for TrialStore with flat JSON structure."""

import json
from pathlib import Path

import pytest

from storage.models import InfraConfig, Trial
from storage.store import TrialStore


@pytest.fixture
def redis_store(tmp_path: Path) -> TrialStore:
    """Create a temporary Redis store for testing."""
    return TrialStore(tmp_path / "redis_results.json", service="redis")


@pytest.fixture
def meilisearch_store(tmp_path: Path) -> TrialStore:
    """Create a temporary Meilisearch store for testing."""
    return TrialStore(tmp_path / "meili_results.json", service="meilisearch")


@pytest.fixture
def sample_redis_dict() -> dict:
    """Sample Redis trial as dict (optimizer format)."""
    return {
        "trial": 1,
        "timestamp": "2026-02-09T12:00:00",
        "cloud": "selectel",
        "config": {
            "mode": "single",
            "cpu_per_node": 4,
            "ram_per_node": 8,
            "maxmemory_policy": "allkeys-lru",
            "io_threads": 2,
            "persistence": "none",
        },
        "nodes": 1,
        "metrics": {
            "ops_per_sec": 150000,
            "avg_latency_ms": 0.5,
            "p50_latency_ms": 0.4,
            "p99_latency_ms": 1.2,
            "p999_latency_ms": 2.5,
            "kb_per_sec": 12000,
        },
        "duration_s": 60,
        "timings": {
            "redis_deploy_s": 120,
            "benchmark_s": 60,
            "trial_total_s": 200,
        },
    }


@pytest.fixture
def sample_meilisearch_dict() -> dict:
    """Sample Meilisearch trial as dict (optimizer format)."""
    return {
        "trial": 1,
        "timestamp": "2026-02-09T12:00:00",
        "cloud": "selectel",
        "infra": {"cpu": 4, "ram_gb": 8, "disk_type": "fast", "disk_size_gb": 100},
        "config": {"max_indexing_memory_mb": 1024, "max_indexing_threads": 4},
        "metrics": {
            "qps": 3000,
            "p50_ms": 30,
            "p95_ms": 40,
            "p99_ms": 50,
            "error_rate": 0.01,
            "indexing_time_s": 15,
        },
        "timings": {
            "terraform_s": 120,
            "meili_ready_s": 30,
            "indexing_s": 15,
            "benchmark_s": 60,
            "trial_total_s": 250,
        },
    }


class TestTrialStore:
    """Tests for TrialStore basic operations."""

    def test_empty_store(self, redis_store: TrialStore):
        """Empty store should have no trials."""
        assert redis_store.count() == 0
        assert redis_store.trials == []

    def test_add_dict(self, redis_store: TrialStore, sample_redis_dict: dict):
        """Adding a dict should create trial with ID."""
        trial = redis_store.add_dict(sample_redis_dict)

        assert trial.id == 1
        assert trial.service == "redis"
        assert trial.cloud == "selectel"
        assert trial.metrics is not None
        assert trial.metrics.ops_per_sec == 150000
        assert redis_store.count() == 1
        assert redis_store.path.exists()

    def test_auto_increment_id(self, redis_store: TrialStore, sample_redis_dict: dict):
        """Trial IDs should auto-increment."""
        t1 = redis_store.add_dict(sample_redis_dict)

        sample2 = sample_redis_dict.copy()
        sample2["trial"] = 2
        sample2["metrics"] = sample_redis_dict["metrics"].copy()
        sample2["metrics"]["ops_per_sec"] = 160000
        t2 = redis_store.add_dict(sample2)

        assert t1.id == 1
        assert t2.id == 2

    def test_persistence(self, tmp_path: Path, sample_redis_dict: dict):
        """Trials should persist across store instances."""
        path = tmp_path / "results.json"

        # Add trial
        store1 = TrialStore(path, service="redis")
        store1.add_dict(sample_redis_dict)

        # Load in new store
        store2 = TrialStore(path, service="redis")
        assert store2.count() == 1
        assert store2.trials[0].id == 1
        assert store2.trials[0].service == "redis"
        assert store2.trials[0].metrics is not None
        assert store2.trials[0].metrics.ops_per_sec == 150000

    def test_reload(self, redis_store: TrialStore, sample_redis_dict: dict):
        """Reload should refresh from disk."""
        redis_store.add_dict(sample_redis_dict)
        redis_store._trials = []  # Clear in-memory

        redis_store.reload()
        assert redis_store.count() == 1

    def test_clear(self, redis_store: TrialStore, sample_redis_dict: dict):
        """Clear should remove all trials and delete file."""
        redis_store.add_dict(sample_redis_dict)
        assert redis_store.path.exists()

        redis_store.clear()
        assert redis_store.count() == 0
        assert not redis_store.path.exists()


class TestTrialStoreFind:
    """Tests for TrialStore.find()."""

    def test_find_by_cloud(self, redis_store: TrialStore, sample_redis_dict: dict):
        """Find should filter by cloud."""
        redis_store.add_dict(sample_redis_dict)

        timeweb = sample_redis_dict.copy()
        timeweb["cloud"] = "timeweb"
        timeweb["ops_per_sec"] = 140000
        redis_store.add_dict(timeweb)

        selectel = redis_store.find(cloud="selectel")
        timeweb_trials = redis_store.find(cloud="timeweb")

        assert len(selectel) == 1
        assert selectel[0].cloud == "selectel"
        assert len(timeweb_trials) == 1
        assert timeweb_trials[0].cloud == "timeweb"

    def test_find_successful_only(
        self, redis_store: TrialStore, sample_redis_dict: dict
    ):
        """Find with successful_only should exclude failed trials."""
        redis_store.add_dict(sample_redis_dict)

        failed = sample_redis_dict.copy()
        failed["ops_per_sec"] = 0
        failed["error"] = "Benchmark failed"
        redis_store.add_dict(failed)

        all_trials = redis_store.find()
        successful = redis_store.find(successful_only=True)

        assert len(all_trials) == 2
        assert len(successful) == 1
        assert successful[0].error is None


class TestTrialStoreFindByConfigKey:
    """Tests for TrialStore.find_by_config_key()."""

    def test_find_redis_config(self, redis_store: TrialStore, sample_redis_dict: dict):
        """Should find Redis trial with matching config key."""
        redis_store.add_dict(sample_redis_dict)

        config_key = json.dumps(
            {
                "cloud": "selectel",
                "mode": "single",
                "cpu_per_node": 4,
                "ram_per_node": 8,
                "maxmemory_policy": "allkeys-lru",
                "io_threads": 2,
                "persistence": "none",
            },
            sort_keys=True,
        )

        result = redis_store.find_by_config_key(config_key)
        assert result is not None
        assert result.metrics is not None
        assert result.metrics.ops_per_sec == 150000

    def test_no_match(self, redis_store: TrialStore, sample_redis_dict: dict):
        """Should return None when no matching config."""
        redis_store.add_dict(sample_redis_dict)

        config_key = json.dumps(
            {
                "cloud": "timeweb",  # Different cloud
                "mode": "single",
                "cpu_per_node": 4,
                "ram_per_node": 8,
                "maxmemory_policy": "allkeys-lru",
                "io_threads": 2,
                "persistence": "none",
            },
            sort_keys=True,
        )

        result = redis_store.find_by_config_key(config_key)
        assert result is None


class TestTrialStoreGetById:
    """Tests for TrialStore.get_by_id()."""

    def test_get_existing(self, redis_store: TrialStore, sample_redis_dict: dict):
        """Should find trial by ID."""
        redis_store.add_dict(sample_redis_dict)

        result = redis_store.get_by_id(1)
        assert result is not None
        assert result.metrics is not None
        assert result.metrics.ops_per_sec == 150000

    def test_get_nonexistent(self, redis_store: TrialStore):
        """Should return None for non-existent ID."""
        result = redis_store.get_by_id(999)
        assert result is None


class TestTrialModels:
    """Tests for Trial model validation."""

    def test_redis_trial_valid(self, sample_redis_dict: dict):
        """Redis trial dict should parse correctly."""
        sample_redis_dict["service"] = "redis"
        trial = Trial.model_validate(sample_redis_dict)

        assert trial.service == "redis"
        assert trial.metrics is not None
        assert trial.metrics.ops_per_sec == 150000
        assert trial.config is not None
        assert trial.config["mode"] == "single"
        assert trial.is_successful()

    def test_meilisearch_trial_valid(self, sample_meilisearch_dict: dict):
        """Meilisearch trial dict should parse correctly."""
        sample_meilisearch_dict["service"] = "meilisearch"
        trial = Trial.model_validate(sample_meilisearch_dict)

        assert trial.service == "meilisearch"
        assert trial.metrics is not None
        assert trial.metrics.qps == 3000
        assert trial.infra is not None
        assert trial.infra.cpu == 4
        assert trial.is_successful()

    def test_failed_trial(self, sample_redis_dict: dict):
        """Failed trial should not be successful."""
        sample_redis_dict["service"] = "redis"
        sample_redis_dict["error"] = "Connection refused"
        sample_redis_dict["metrics"]["ops_per_sec"] = 0

        trial = Trial.model_validate(sample_redis_dict)
        assert not trial.is_successful()

    def test_get_primary_metric_redis(self, sample_redis_dict: dict):
        """Redis primary metric should be ops_per_sec."""
        sample_redis_dict["service"] = "redis"
        trial = Trial.model_validate(sample_redis_dict)
        assert trial.get_primary_metric() == 150000

    def test_get_primary_metric_meilisearch(self, sample_meilisearch_dict: dict):
        """Meilisearch primary metric should be qps."""
        sample_meilisearch_dict["service"] = "meilisearch"
        trial = Trial.model_validate(sample_meilisearch_dict)
        assert trial.get_primary_metric() == 3000


class TestTrialStoreAsDicts:
    """Tests for TrialStore.as_dicts()."""

    def test_as_dicts(self, redis_store: TrialStore, sample_redis_dict: dict):
        """as_dicts should return list of dicts."""
        redis_store.add_dict(sample_redis_dict)

        dicts = redis_store.as_dicts()
        assert len(dicts) == 1
        assert dicts[0]["metrics"]["ops_per_sec"] == 150000
        assert dicts[0]["service"] == "redis"


class TestInfraConfig:
    """Tests for InfraConfig model."""

    def test_basic_creation(self):
        """Should create with basic fields."""
        infra = InfraConfig(cpu=4, ram_gb=8, disk_type="fast", disk_size_gb=100)
        assert infra.cpu == 4
        assert infra.ram_gb == 8

    def test_defaults(self):
        """Should have sensible defaults."""
        infra = InfraConfig()
        assert infra.cpu == 0
        assert infra.ram_gb == 0
        assert infra.disk_type == ""
        assert infra.disk_size_gb == 0

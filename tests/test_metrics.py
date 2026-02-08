"""Tests for metrics module."""

import pytest

from metrics import Direction, MetricConfig, get_metric_value


class TestDirection:
    """Tests for Direction enum."""

    def test_maximize_value(self) -> None:
        assert Direction.MAXIMIZE.value == "maximize"

    def test_minimize_value(self) -> None:
        assert Direction.MINIMIZE.value == "minimize"


class TestMetricConfig:
    """Tests for MetricConfig dataclass."""

    def test_basic_creation(self) -> None:
        config = MetricConfig(
            name="test_metric",
            description="Test metric",
            direction=Direction.MAXIMIZE,
            unit="ops/s",
        )
        assert config.name == "test_metric"
        assert config.description == "Test metric"
        assert config.direction == Direction.MAXIMIZE
        assert config.unit == "ops/s"
        assert config.format_spec == ".2f"  # default

    def test_custom_format_spec(self) -> None:
        config = MetricConfig(
            name="test",
            description="Test",
            direction=Direction.MINIMIZE,
            unit="ms",
            format_spec=".0f",
        )
        assert config.format_spec == ".0f"

    def test_direction_str_maximize(self) -> None:
        config = MetricConfig(
            name="test",
            description="Test",
            direction=Direction.MAXIMIZE,
            unit="ops/s",
        )
        assert config.direction_str == "maximize"

    def test_direction_str_minimize(self) -> None:
        config = MetricConfig(
            name="test",
            description="Test",
            direction=Direction.MINIMIZE,
            unit="ms",
        )
        assert config.direction_str == "minimize"

    def test_format_value(self) -> None:
        config = MetricConfig(
            name="test",
            description="Test",
            direction=Direction.MAXIMIZE,
            unit="ops/s",
            format_spec=".2f",
        )
        assert config.format_value(1234.567) == "1234.57 ops/s"

    def test_format_value_integer(self) -> None:
        config = MetricConfig(
            name="test",
            description="Test",
            direction=Direction.MAXIMIZE,
            unit="TPS",
            format_spec=".0f",
        )
        assert config.format_value(1234.567) == "1235 TPS"

    def test_frozen_immutable(self) -> None:
        config = MetricConfig(
            name="test",
            description="Test",
            direction=Direction.MAXIMIZE,
            unit="ops/s",
        )
        with pytest.raises(AttributeError):
            config.name = "changed"  # type: ignore[misc]


class TestServiceMetrics:
    """Tests for service-specific metrics."""

    def test_redis_metrics_exist(self) -> None:
        from optimizers.redis.metrics import METRICS

        assert "ops_per_sec" in METRICS
        assert "p99_latency_ms" in METRICS
        assert "cost_efficiency" in METRICS

    def test_redis_metrics_directions(self) -> None:
        from optimizers.redis.metrics import METRICS

        assert METRICS["ops_per_sec"].direction == Direction.MAXIMIZE
        assert METRICS["p99_latency_ms"].direction == Direction.MINIMIZE
        assert METRICS["cost_efficiency"].direction == Direction.MAXIMIZE

    def test_minio_metrics_exist(self) -> None:
        from optimizers.minio.metrics import METRICS

        assert "total_mib_s" in METRICS
        assert "get_mib_s" in METRICS
        assert "put_mib_s" in METRICS
        assert "cost_efficiency" in METRICS

    def test_postgres_metrics_exist(self) -> None:
        from optimizers.postgres.metrics import METRICS

        assert "tps" in METRICS
        assert "latency_avg_ms" in METRICS
        assert "cost_efficiency" in METRICS

    def test_postgres_metrics_directions(self) -> None:
        from optimizers.postgres.metrics import METRICS

        assert METRICS["tps"].direction == Direction.MAXIMIZE
        assert METRICS["latency_avg_ms"].direction == Direction.MINIMIZE

    def test_meilisearch_metrics_exist(self) -> None:
        from optimizers.meilisearch.metrics import METRICS

        assert "qps" in METRICS
        assert "p95_ms" in METRICS
        assert "indexing_time" in METRICS
        assert "cost_efficiency" in METRICS

    def test_all_metrics_have_required_fields(self) -> None:
        """All metrics should have name, description, direction, unit."""
        from optimizers.meilisearch.metrics import METRICS as MEILI_METRICS
        from optimizers.minio.metrics import METRICS as MINIO_METRICS
        from optimizers.postgres.metrics import METRICS as PG_METRICS
        from optimizers.redis.metrics import METRICS as REDIS_METRICS

        all_metrics = [
            ("redis", REDIS_METRICS),
            ("minio", MINIO_METRICS),
            ("postgres", PG_METRICS),
            ("meilisearch", MEILI_METRICS),
        ]

        for service, metrics in all_metrics:
            for name, config in metrics.items():
                assert config.name == name, f"{service}.{name}: name mismatch"
                assert config.description, f"{service}.{name}: missing description"
                assert config.unit, f"{service}.{name}: missing unit"
                assert isinstance(config.direction, Direction), (
                    f"{service}.{name}: invalid direction"
                )


class TestGetMetricValue:
    """Tests for get_metric_value function."""

    def test_maximize_metric_returns_value(self) -> None:
        """Maximize metrics should return value as-is."""
        metrics = {
            "ops_per_sec": MetricConfig(
                name="ops_per_sec",
                description="Ops",
                direction=Direction.MAXIMIZE,
                unit="ops/s",
            )
        }
        result = {"ops_per_sec": 1000.0}
        assert get_metric_value(result, "ops_per_sec", metrics) == 1000.0

    def test_minimize_metric_returns_negative(self) -> None:
        """Minimize metrics should return negated value for Optuna."""
        metrics = {
            "latency_ms": MetricConfig(
                name="latency_ms",
                description="Latency",
                direction=Direction.MINIMIZE,
                unit="ms",
            )
        }
        result = {"latency_ms": 5.0}
        assert get_metric_value(result, "latency_ms", metrics) == -5.0

    def test_minimize_zero_returns_inf(self) -> None:
        """Minimize metric with zero value should return infinity."""
        metrics = {
            "latency_ms": MetricConfig(
                name="latency_ms",
                description="Latency",
                direction=Direction.MINIMIZE,
                unit="ms",
            )
        }
        result = {"latency_ms": 0}
        assert get_metric_value(result, "latency_ms", metrics) == float("inf")

    def test_missing_metric_returns_zero(self) -> None:
        """Missing metric in result should return 0."""
        metrics = {
            "ops_per_sec": MetricConfig(
                name="ops_per_sec",
                description="Ops",
                direction=Direction.MAXIMIZE,
                unit="ops/s",
            )
        }
        result = {}
        assert get_metric_value(result, "ops_per_sec", metrics) == 0

    def test_unknown_metric_returns_zero(self) -> None:
        """Unknown metric (not in metrics dict) should return value as-is."""
        metrics: dict[str, MetricConfig] = {}
        result = {"unknown": 100.0}
        assert get_metric_value(result, "unknown", metrics) == 100.0

    def test_with_real_redis_metrics(self) -> None:
        """Test with actual Redis metrics."""
        from optimizers.redis.metrics import METRICS

        result = {"ops_per_sec": 50000, "p99_latency_ms": 2.5}
        assert get_metric_value(result, "ops_per_sec", METRICS) == 50000
        assert get_metric_value(result, "p99_latency_ms", METRICS) == -2.5

    def test_result_key_alternate_lookup(self) -> None:
        """Metric with result_key should use alternate key for lookup."""
        metrics = {
            "indexing_time": MetricConfig(
                name="indexing_time",
                description="Indexing time",
                direction=Direction.MINIMIZE,
                unit="s",
                result_key="indexing_time_s",  # Different key in results
            )
        }
        result = {"indexing_time_s": 5.0}  # Note: using the alternate key
        # Should find value via result_key and negate (MINIMIZE)
        assert get_metric_value(result, "indexing_time", metrics) == -5.0

    def test_extractor_function(self) -> None:
        """Metric with extractor should use custom function."""
        metrics = {
            "efficiency": MetricConfig(
                name="efficiency",
                description="Calculated efficiency",
                direction=Direction.MAXIMIZE,
                unit="ops/$",
                extractor=lambda r, **kw: r.get("ops", 0) / r.get("cost", 1),
            )
        }
        result = {"ops": 1000, "cost": 10}
        assert get_metric_value(result, "efficiency", metrics) == 100.0

    def test_extractor_with_kwargs(self) -> None:
        """Extractor should receive kwargs passed to get_metric_value."""
        received_kwargs: dict = {}

        def capture_extractor(result: dict, **kwargs) -> float:
            received_kwargs.update(kwargs)
            return result.get("value", 0)

        metrics = {
            "test": MetricConfig(
                name="test",
                description="Test",
                direction=Direction.MAXIMIZE,
                unit="x",
                extractor=capture_extractor,
            )
        }
        result = {"value": 42.0}
        get_metric_value(result, "test", metrics, cloud="selectel", extra="arg")
        assert received_kwargs["cloud"] == "selectel"
        assert received_kwargs["extra"] == "arg"

    def test_meilisearch_indexing_time_uses_result_key(self) -> None:
        """Meilisearch indexing_time should use result_key for lookup."""
        from optimizers.meilisearch.metrics import METRICS

        result = {"indexing_time_s": 12.5}
        # Should use result_key="indexing_time_s" and negate (MINIMIZE)
        assert get_metric_value(result, "indexing_time", METRICS) == -12.5

    def test_meilisearch_cost_efficiency_uses_extractor(self) -> None:
        """Meilisearch cost_efficiency should calculate from qps and infra."""
        from optimizers.meilisearch.metrics import METRICS

        result = {
            "qps": 1000,
            "infra": {"cpu": 2, "ram_gb": 4, "disk_size_gb": 50, "disk_type": "fast"},
        }
        # extractor calculates qps / cost
        value = get_metric_value(result, "cost_efficiency", METRICS, cloud="selectel")
        assert value > 0  # Should calculate something
        # With 2cpu/4gb/50gb fast disk on selectel: ~4212₽/mo
        # 1000 qps / 4212 ≈ 0.237
        assert 0.1 < value < 0.5

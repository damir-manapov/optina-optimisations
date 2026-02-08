"""Tests for pricing module."""

import pytest

from pricing import (
    CLOUD_PRICING,
    CloudPricing,
    DiskConfig,
    calculate_vm_cost,
    filter_valid_ram,
    get_cloud_pricing,
    get_disk_types,
    get_min_ram_for_cpu,
    validate_infra_config,
)


class TestCloudPricing:
    """Tests for CloudPricing dataclass."""

    def test_selectel_pricing_exists(self) -> None:
        assert "selectel" in CLOUD_PRICING

    def test_timeweb_pricing_exists(self) -> None:
        assert "timeweb" in CLOUD_PRICING

    def test_get_cloud_pricing_selectel(self) -> None:
        pricing = get_cloud_pricing("selectel")
        assert isinstance(pricing, CloudPricing)
        assert pricing.cpu_cost > 0
        assert pricing.ram_cost > 0
        assert len(pricing.disk_cost_multipliers) > 0

    def test_get_cloud_pricing_timeweb(self) -> None:
        pricing = get_cloud_pricing("timeweb")
        assert isinstance(pricing, CloudPricing)
        assert pricing.cpu_cost > 0
        assert pricing.ram_cost > 0

    def test_get_cloud_pricing_unknown(self) -> None:
        with pytest.raises(ValueError, match="Unknown cloud"):
            get_cloud_pricing("unknown_cloud")


class TestDiskTypes:
    """Tests for disk type functions."""

    def test_selectel_disk_types(self) -> None:
        types = get_disk_types("selectel")
        assert "fast" in types
        assert "universal" in types
        assert "basic" in types

    def test_timeweb_disk_types(self) -> None:
        types = get_disk_types("timeweb")
        assert "nvme" in types
        assert "ssd" in types


class TestInfraValidation:
    """Tests for infrastructure validation."""

    def test_selectel_min_ram_for_2cpu(self) -> None:
        min_ram = get_min_ram_for_cpu("selectel", 2)
        assert min_ram == 2

    def test_selectel_min_ram_for_16cpu(self) -> None:
        min_ram = get_min_ram_for_cpu("selectel", 16)
        assert min_ram == 32

    def test_timeweb_no_constraints(self) -> None:
        # Timeweb has no known constraints
        min_ram = get_min_ram_for_cpu("timeweb", 16)
        assert min_ram == 0

    def test_unknown_cloud_returns_zero(self) -> None:
        min_ram = get_min_ram_for_cpu("unknown", 4)
        assert min_ram == 0

    def test_validate_valid_config(self) -> None:
        error = validate_infra_config("selectel", cpu=4, ram_gb=8)
        assert error is None

    def test_validate_invalid_config(self) -> None:
        error = validate_infra_config("selectel", cpu=16, ram_gb=16)
        assert error is not None
        assert "requires min 32GB" in error

    def test_filter_valid_ram(self) -> None:
        ram_options = [2, 4, 8, 16, 32, 64]
        valid = filter_valid_ram("selectel", cpu=16, ram_options=ram_options)
        assert valid == [32, 64]

    def test_filter_valid_ram_no_constraints(self) -> None:
        ram_options = [2, 4, 8, 16]
        valid = filter_valid_ram("timeweb", cpu=16, ram_options=ram_options)
        assert valid == ram_options


class TestCostCalculation:
    """Tests for VM cost calculation."""

    def test_basic_cost_calculation(self) -> None:
        cost = calculate_vm_cost("selectel", cpu=2, ram_gb=4)
        assert cost > 0
        # 2 * 655 + 4 * 238 + 50 * 39 = 1310 + 952 + 1950 = 4212
        assert cost == pytest.approx(4212, rel=0.01)

    def test_cost_with_custom_disk(self) -> None:
        disks = [DiskConfig(size_gb=100, disk_type="fast")]
        cost = calculate_vm_cost("selectel", cpu=2, ram_gb=4, disks=disks)
        # 2 * 655 + 4 * 238 + 100 * 39 = 1310 + 952 + 3900 = 6162
        assert cost == pytest.approx(6162, rel=0.01)

    def test_cost_with_multiple_disks(self) -> None:
        disks = [
            DiskConfig(size_gb=50, disk_type="fast"),
            DiskConfig(size_gb=200, disk_type="basic"),
        ]
        cost = calculate_vm_cost("selectel", cpu=2, ram_gb=4, disks=disks)
        # 2 * 655 + 4 * 238 + 50 * 39 + 200 * 7 = 1310 + 952 + 1950 + 1400 = 5612
        assert cost == pytest.approx(5612, rel=0.01)

    def test_cost_with_multiple_nodes(self) -> None:
        cost = calculate_vm_cost("selectel", cpu=2, ram_gb=4, nodes=3)
        single_node_cost = calculate_vm_cost("selectel", cpu=2, ram_gb=4, nodes=1)
        assert cost == pytest.approx(single_node_cost * 3, rel=0.01)

    def test_cost_timeweb(self) -> None:
        cost = calculate_vm_cost("timeweb", cpu=2, ram_gb=4)
        assert cost > 0
        # Should be cheaper than selectel (lower rates)
        selectel_cost = calculate_vm_cost("selectel", cpu=2, ram_gb=4)
        assert cost < selectel_cost

    def test_disk_count_multiplier(self) -> None:
        single_disk = calculate_vm_cost(
            "selectel",
            cpu=2,
            ram_gb=4,
            disks=[DiskConfig(size_gb=50, disk_type="fast", count=1)],
        )
        triple_disk = calculate_vm_cost(
            "selectel",
            cpu=2,
            ram_gb=4,
            disks=[DiskConfig(size_gb=50, disk_type="fast", count=3)],
        )
        # Disk cost should triple
        disk_diff = triple_disk - single_disk
        expected_diff = 50 * 39 * 2  # 2 extra disks
        assert disk_diff == pytest.approx(expected_diff, rel=0.01)


class TestCostExtractorConfig:
    """Tests for CostExtractorConfig and make_cost_extractor."""

    def test_basic_extractor(self) -> None:
        from pricing import CostExtractorConfig, make_cost_extractor

        config = CostExtractorConfig(
            metric_key="tps",
            config_key="config",
            cpu_key="cpu",
            ram_key="ram_gb",
        )
        extractor = make_cost_extractor(config)
        result = {
            "tps": 1000,
            "config": {"cpu": 2, "ram_gb": 4},
        }
        efficiency = extractor(result, "selectel")
        assert efficiency > 0

    def test_extractor_with_disk_config(self) -> None:
        from pricing import CostExtractorConfig, make_cost_extractor

        config = CostExtractorConfig(
            metric_key="qps",
            config_key="infra",
            cpu_key="cpu",
            ram_key="ram_gb",
            disk_size_key="disk_size_gb",
            disk_type_key="disk_type",
        )
        extractor = make_cost_extractor(config)
        result = {
            "qps": 500,
            "infra": {"cpu": 4, "ram_gb": 8, "disk_size_gb": 100, "disk_type": "fast"},
        }
        efficiency = extractor(result, "selectel")
        assert efficiency > 0

    def test_extractor_with_nodes(self) -> None:
        from pricing import CostExtractorConfig, make_cost_extractor

        config = CostExtractorConfig(
            metric_key="ops",
            config_key="config",
            cpu_key="cpu",
            ram_key="ram_gb",
            nodes_key="nodes",
        )
        extractor = make_cost_extractor(config)
        result_1node = {"ops": 1000, "config": {"cpu": 2, "ram_gb": 4, "nodes": 1}}
        result_3nodes = {"ops": 1000, "config": {"cpu": 2, "ram_gb": 4, "nodes": 3}}

        eff_1 = extractor(result_1node, "selectel")
        eff_3 = extractor(result_3nodes, "selectel")
        # 3 nodes = 3x cost = 1/3 efficiency for same metric
        assert eff_3 == pytest.approx(eff_1 / 3, rel=0.01)

    def test_extractor_with_drives_per_node(self) -> None:
        from pricing import CostExtractorConfig, make_cost_extractor

        config = CostExtractorConfig(
            metric_key="throughput",
            config_key="config",
            cpu_key="cpu",
            ram_key="ram_gb",
            drives_per_node_key="drives",
        )
        extractor = make_cost_extractor(config)
        result_1drive = {
            "throughput": 100,
            "config": {"cpu": 2, "ram_gb": 4, "drives": 1},
        }
        result_4drives = {
            "throughput": 100,
            "config": {"cpu": 2, "ram_gb": 4, "drives": 4},
        }

        eff_1 = extractor(result_1drive, "selectel")
        eff_4 = extractor(result_4drives, "selectel")
        # More drives = higher cost = lower efficiency
        assert eff_4 < eff_1

    def test_extractor_missing_metric_returns_zero(self) -> None:
        from pricing import CostExtractorConfig, make_cost_extractor

        config = CostExtractorConfig(
            metric_key="tps",
            config_key="config",
            cpu_key="cpu",
            ram_key="ram_gb",
        )
        extractor = make_cost_extractor(config)
        result = {"config": {"cpu": 2, "ram_gb": 4}}  # No tps
        assert extractor(result, "selectel") == 0

    def test_extractor_missing_config_returns_zero(self) -> None:
        from pricing import CostExtractorConfig, make_cost_extractor

        config = CostExtractorConfig(
            metric_key="tps",
            config_key="config",
            cpu_key="cpu",
            ram_key="ram_gb",
        )
        extractor = make_cost_extractor(config)
        result = {"tps": 1000}  # No config
        assert extractor(result, "selectel") == 0

    def test_extractor_uses_defaults(self) -> None:
        from pricing import CostExtractorConfig, make_cost_extractor

        config = CostExtractorConfig(
            metric_key="ops",
            config_key="config",
            cpu_key="cpu",
            ram_key="ram_gb",
            default_disk_size=100,
            default_disk_type="universal",
            nodes_default=2,
        )
        extractor = make_cost_extractor(config)
        result = {"ops": 1000, "config": {"cpu": 2, "ram_gb": 4}}
        efficiency = extractor(result, "selectel")
        # Should use defaults and return non-zero
        assert efficiency > 0

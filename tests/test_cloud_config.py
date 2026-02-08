"""Tests for cloud_config module."""

from pathlib import Path

import pytest

from cloud_config import (
    CLOUD_CONFIGS,
    CloudConfig,
    get_cloud_config,
    make_cloud_config,
)


class TestCloudConfig:
    """Tests for CloudConfig dataclass."""

    def test_has_required_fields(self) -> None:
        config = CloudConfig(
            name="test",
            terraform_dir=Path("/tmp/test"),
            disk_types=["fast"],
            cpu_cost=1.0,
            ram_cost=0.5,
            disk_cost_multipliers={"fast": 10.0},
        )
        assert config.name == "test"
        assert config.cpu_cost == 1.0
        assert config.ram_cost == 0.5

    def test_default_disk_cost_multipliers(self) -> None:
        config = CloudConfig(
            name="test",
            terraform_dir=Path("/tmp/test"),
            disk_types=["fast"],
            cpu_cost=1.0,
            ram_cost=0.5,
        )
        assert config.disk_cost_multipliers == {}


class TestMakeCloudConfig:
    """Tests for make_cloud_config function."""

    def test_selectel_config(self) -> None:
        config = make_cloud_config("selectel")
        assert config.name == "selectel"
        assert config.cpu_cost > 0
        assert config.ram_cost > 0
        assert "fast" in config.disk_types

    def test_timeweb_config(self) -> None:
        config = make_cloud_config("timeweb")
        assert config.name == "timeweb"
        assert config.cpu_cost > 0
        assert config.ram_cost > 0

    def test_custom_terraform_subdir(self) -> None:
        config = make_cloud_config("selectel", terraform_subdir="custom")
        assert "custom" in str(config.terraform_dir)

    def test_default_terraform_subdir_uses_name(self) -> None:
        config = make_cloud_config("selectel")
        assert "selectel" in str(config.terraform_dir)


class TestGetCloudConfig:
    """Tests for get_cloud_config function."""

    def test_get_selectel(self) -> None:
        config = get_cloud_config("selectel")
        assert config.name == "selectel"

    def test_get_timeweb(self) -> None:
        config = get_cloud_config("timeweb")
        assert config.name == "timeweb"

    def test_unknown_cloud_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown cloud"):
            get_cloud_config("aws")

    def test_error_message_lists_available(self) -> None:
        with pytest.raises(ValueError, match="selectel"):
            get_cloud_config("unknown")


class TestCloudConfigs:
    """Tests for pre-built CLOUD_CONFIGS."""

    def test_has_selectel(self) -> None:
        assert "selectel" in CLOUD_CONFIGS

    def test_has_timeweb(self) -> None:
        assert "timeweb" in CLOUD_CONFIGS

    def test_configs_have_terraform_dir(self) -> None:
        for name, config in CLOUD_CONFIGS.items():
            assert config.terraform_dir is not None
            assert name in str(config.terraform_dir)

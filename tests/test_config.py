"""Tests for configuration loading and validation."""

from pathlib import Path

import pytest

from crimecity3k.config import AggregationConfig, Config


def test_config_loads_from_file() -> None:
    """Test config.toml loads successfully."""
    config = Config.from_file("config.toml")
    assert config.data_dir == Path("data")
    assert 4 in config.aggregation.resolutions
    assert 5 in config.aggregation.resolutions
    assert 6 in config.aggregation.resolutions


def test_config_validates_resolutions() -> None:
    """Test resolution validation rejects invalid values."""
    with pytest.raises(ValueError, match="Resolutions must be between 4 and 6"):
        AggregationConfig(resolutions=[99])


def test_config_validates_resolutions_too_low() -> None:
    """Test resolution validation rejects values below 4."""
    with pytest.raises(ValueError, match="Resolutions must be between 4 and 6"):
        AggregationConfig(resolutions=[3])


def test_config_accepts_valid_resolutions() -> None:
    """Test resolution validation accepts valid values."""
    config = AggregationConfig(resolutions=[4, 5, 6])
    assert config.resolutions == [4, 5, 6]


def test_config_file_not_found() -> None:
    """Test Config.from_file raises error when file doesn't exist."""
    with pytest.raises(FileNotFoundError, match="Config not found"):
        Config.from_file("nonexistent.toml")


def test_config_defaults() -> None:
    """Test default configuration values."""
    config = Config()
    assert config.data_dir == Path("data")
    assert config.aggregation.resolutions == [4, 5, 6]
    assert config.aggregation.min_population_threshold == 100
    assert config.duckdb.memory_limit == "4GB"
    assert config.duckdb.threads == 2
    assert config.export.geojson_compression is True
    assert config.export.pmtiles_max_zoom == 10

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


def test_category_mapping_loads_from_file() -> None:
    """Test category_mapping.toml loads with all expected structure."""
    from crimecity3k.config import CategoryMapping

    mapping = CategoryMapping.from_file("category_mapping.toml")

    # Verify all 8 categories exist
    assert "traffic" in mapping.categories
    assert "property" in mapping.categories
    assert "violence" in mapping.categories
    assert "narcotics" in mapping.categories
    assert "fraud" in mapping.categories
    assert "public_order" in mapping.categories
    assert "weapons" in mapping.categories
    assert "other" in mapping.categories
    assert len(mapping.categories) == 8

    # Verify each category has name and types
    for category_id, category in mapping.categories.items():
        assert category.name, f"Category {category_id} missing name"
        assert category.types, f"Category {category_id} has empty types list"
        assert isinstance(category.types, list), f"Category {category_id} types not a list"

    # Verify all types are unique across categories
    all_types: list[str] = []
    for category in mapping.categories.values():
        all_types.extend(category.types)

    assert len(all_types) == len(set(all_types)), "Duplicate event types found across categories"

    # Verify total count matches known data
    assert len(all_types) == 51, f"Expected 51 event types, found {len(all_types)}"


def test_category_mapping_specific_categories() -> None:
    """Test category mapping has correct Swedish names and sample types."""
    from crimecity3k.config import CategoryMapping

    mapping = CategoryMapping.from_file("category_mapping.toml")

    # Test traffic category
    traffic = mapping.categories["traffic"]
    assert traffic.name == "Trafik"
    assert "Trafikolycka, personskada" in traffic.types
    assert "Rattfylleri" in traffic.types

    # Test property category
    property_crime = mapping.categories["property"]
    assert property_crime.name == "Egendomsbrott"
    assert "Stöld" in property_crime.types
    assert "Inbrott" in property_crime.types

    # Test violence category
    violence = mapping.categories["violence"]
    assert violence.name == "Våld"
    assert "Misshandel" in violence.types


def test_category_mapping_file_not_found() -> None:
    """Test CategoryMapping.from_file raises error for missing file."""
    from crimecity3k.config import CategoryMapping, CategoryMappingError

    with pytest.raises(CategoryMappingError, match="not found"):
        CategoryMapping.from_file("nonexistent_mapping.toml")

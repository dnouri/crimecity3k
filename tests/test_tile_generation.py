"""Tests for GeoJSON export and tile generation.

These tests verify the H3-to-GeoJSONL export pipeline for web visualization.
Following aviation-anomaly patterns for tile generation testing.
"""

import gzip
import json
from pathlib import Path

import duckdb
import pytest

from crimecity3k.config import Config


@pytest.fixture
def config() -> Config:
    """Load project configuration."""
    return Config.from_file("config.toml")


@pytest.fixture
def events_fixture() -> Path:
    """Path to test events fixture."""
    return Path("tests/fixtures/data/events.parquet")


def test_export_h3_to_geojson_single_cell(tmp_path: Path) -> None:
    """Test exporting a single H3 cell to GeoJSONL format.

    Verifies:
    - Output file is created
    - Valid GeoJSON Feature structure
    - Polygon geometry (hexagon)
    - All crime statistics properties present
    """
    # Create minimal test data with a single H3 cell
    conn = duckdb.connect()
    conn.execute("INSTALL h3 FROM community; LOAD h3; INSTALL spatial; LOAD spatial")

    # Create test H3 aggregated data matching our schema
    conn.execute("""
        CREATE TABLE test_events AS
        SELECT
            '851f94a3fffffff' as h3_cell,
            10 as total_count,
            3 as traffic_count,
            2 as property_count,
            1 as violence_count,
            0 as narcotics_count,
            0 as fraud_count,
            2 as public_order_count,
            0 as weapons_count,
            2 as other_count,
            [{'type': 'Trafikolycka', 'count': 3}, {'type': 'Stöld', 'count': 2}] as type_counts,
            'Stockholm' as dominant_location,
            1000.0 as population,
            100.0 as rate_per_10000
    """)

    # Import the function we're testing
    from crimecity3k.tile_generation import export_h3_to_geojson

    output_file = tmp_path / "test_r5.geojsonl.gz"

    export_h3_to_geojson(
        conn=conn,
        events_table="test_events",
        output_file=output_file,
    )

    # Verify the output
    assert output_file.exists(), "Output file not created"

    # Load and validate GeoJSONL structure (one feature per line)
    with gzip.open(output_file, "rt") as f:
        lines = f.readlines()

    assert len(lines) == 1, "Should have exactly one line for one feature"

    # Parse the single feature
    feature = json.loads(lines[0])

    # Validate GeoJSON structure
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Polygon"

    # H3 hexagon should have 7 coordinates (6 vertices + closing point)
    coords = feature["geometry"]["coordinates"][0]
    assert len(coords) == 7, f"H3 hexagon should have 7 coords, got {len(coords)}"

    # Validate all properties present
    props = feature["properties"]
    assert props["h3_cell"] == "851f94a3fffffff"
    assert props["total_count"] == 10
    assert props["traffic_count"] == 3
    assert props["property_count"] == 2
    assert props["violence_count"] == 1
    assert props["narcotics_count"] == 0
    assert props["fraud_count"] == 0
    assert props["public_order_count"] == 2
    assert props["weapons_count"] == 0
    assert props["other_count"] == 2
    assert props["population"] == 1000.0
    assert props["rate_per_10000"] == 100.0
    assert "type_counts" in props

    conn.close()


def test_export_h3_to_geojson_multiple_cells(tmp_path: Path) -> None:
    """Test exporting multiple H3 cells to GeoJSONL format.

    Verifies:
    - Multiple features exported as separate lines
    - Each line is valid JSON
    - Properties preserved correctly
    """
    conn = duckdb.connect()
    conn.execute("INSTALL h3 FROM community; LOAD h3; INSTALL spatial; LOAD spatial")

    # Create test data with multiple cells
    conn.execute("""
        CREATE TABLE test_events AS
        SELECT * FROM (VALUES
            ('851f94a3fffffff', 10, 5, 2, 1, 0, 0, 1, 0, 1, [], 'Stockholm', 1000.0, 100.0),
            ('851f94abfffffff', 5, 2, 1, 0, 1, 0, 0, 0, 1, [], 'Malmö', 500.0, 100.0),
            ('851f94b3fffffff', 3, 0, 1, 1, 0, 0, 1, 0, 0, [], 'Göteborg', 0.0, 0.0)
        ) AS t(h3_cell, total_count, traffic_count, property_count, violence_count,
               narcotics_count, fraud_count, public_order_count, weapons_count,
               other_count, type_counts, dominant_location, population, rate_per_10000)
    """)

    from crimecity3k.tile_generation import export_h3_to_geojson

    output_file = tmp_path / "test_multiple.geojsonl.gz"

    export_h3_to_geojson(
        conn=conn,
        events_table="test_events",
        output_file=output_file,
    )

    # Load and count features
    with gzip.open(output_file, "rt") as f:
        lines = f.readlines()

    assert len(lines) == 3, f"Should have 3 features, got {len(lines)}"

    # Each line should be valid JSON
    for i, line in enumerate(lines):
        feature = json.loads(line)
        assert feature["type"] == "Feature", f"Line {i} is not a valid Feature"
        assert "geometry" in feature
        assert "properties" in feature

    conn.close()


def test_export_h3_to_geojson_coordinate_order(tmp_path: Path) -> None:
    """Test GeoJSON coordinates are in correct [lon, lat] order.

    GeoJSON spec requires [longitude, latitude] order.
    """
    conn = duckdb.connect()
    conn.execute("INSTALL h3 FROM community; LOAD h3; INSTALL spatial; LOAD spatial")

    # Use a known H3 cell in Stockholm area (59.33°N, 18.07°E)
    conn.execute("""
        CREATE TABLE test_events AS
        SELECT
            '85088663fffffff' as h3_cell,
            1 as total_count,
            0 as traffic_count, 0 as property_count, 0 as violence_count,
            0 as narcotics_count, 0 as fraud_count, 0 as public_order_count,
            0 as weapons_count, 1 as other_count,
            [] as type_counts,
            'Stockholm' as dominant_location,
            0.0 as population, 0.0 as rate_per_10000
    """)

    from crimecity3k.tile_generation import export_h3_to_geojson

    output_file = tmp_path / "test_coords.geojsonl.gz"

    export_h3_to_geojson(
        conn=conn,
        events_table="test_events",
        output_file=output_file,
    )

    with gzip.open(output_file, "rt") as f:
        feature = json.loads(f.readline())

    # Get first coordinate pair
    coords = feature["geometry"]["coordinates"][0]
    lon, lat = coords[0]

    # Sweden is roughly 55-69°N, 11-24°E
    # Longitude should be smaller than latitude for Sweden
    assert 10.0 <= lon <= 25.0, f"Longitude {lon} out of Sweden range"
    assert 55.0 <= lat <= 70.0, f"Latitude {lat} out of Sweden range"

    conn.close()


def test_export_h3_to_geojson_type_counts_serialized(tmp_path: Path) -> None:
    """Test type_counts array is properly serialized in GeoJSON.

    The sparse type_counts array should be preserved as JSON array.
    """
    conn = duckdb.connect()
    conn.execute("INSTALL h3 FROM community; LOAD h3; INSTALL spatial; LOAD spatial")

    conn.execute("""
        CREATE TABLE test_events AS
        SELECT
            '851f94a3fffffff' as h3_cell,
            5 as total_count,
            0 as traffic_count, 3 as property_count, 0 as violence_count,
            0 as narcotics_count, 0 as fraud_count, 0 as public_order_count,
            0 as weapons_count, 2 as other_count,
            [
                {'type': 'Stöld', 'count': 3},
                {'type': 'Övrigt', 'count': 2}
            ] as type_counts,
            'Stockholm' as dominant_location,
            1000.0 as population, 50.0 as rate_per_10000
    """)

    from crimecity3k.tile_generation import export_h3_to_geojson

    output_file = tmp_path / "test_type_counts.geojsonl.gz"

    export_h3_to_geojson(
        conn=conn,
        events_table="test_events",
        output_file=output_file,
    )

    with gzip.open(output_file, "rt") as f:
        feature = json.loads(f.readline())

    props = feature["properties"]
    type_counts = props["type_counts"]

    # Should be a list of objects
    assert isinstance(type_counts, list), f"type_counts should be list, got {type(type_counts)}"
    assert len(type_counts) == 2, f"Should have 2 type entries, got {len(type_counts)}"

    # Verify structure
    for item in type_counts:
        assert "type" in item, "type_counts item missing 'type' field"
        assert "count" in item, "type_counts item missing 'count' field"

    conn.close()


def test_export_h3_to_geojson_atomic_write(tmp_path: Path) -> None:
    """Test atomic write pattern - no temp file left on success."""
    conn = duckdb.connect()
    conn.execute("INSTALL h3 FROM community; LOAD h3; INSTALL spatial; LOAD spatial")

    conn.execute("""
        CREATE TABLE test_events AS
        SELECT
            '851f94a3fffffff' as h3_cell,
            1 as total_count,
            0 as traffic_count, 0 as property_count, 0 as violence_count,
            0 as narcotics_count, 0 as fraud_count, 0 as public_order_count,
            0 as weapons_count, 1 as other_count,
            [] as type_counts,
            'Stockholm' as dominant_location,
            0.0 as population, 0.0 as rate_per_10000
    """)

    from crimecity3k.tile_generation import export_h3_to_geojson

    output_file = tmp_path / "test_atomic.geojsonl.gz"
    temp_file = output_file.with_suffix(".tmp")

    export_h3_to_geojson(
        conn=conn,
        events_table="test_events",
        output_file=output_file,
    )

    assert output_file.exists(), "Output file not created"
    assert not temp_file.exists(), "Temp file should be cleaned up"

    conn.close()


def test_export_h3_integration_with_fixture(
    events_fixture: Path,
    synthetic_population_h3: Path,
    tmp_path: Path,
    config: Config,
) -> None:
    """Integration test: GeoJSON export with real aggregated event data.

    Tests complete pipeline from events → H3 aggregation → GeoJSONL export.
    """
    from crimecity3k.h3_processing import aggregate_events_to_h3
    from crimecity3k.tile_generation import export_h3_to_geojson

    # Step 1: Aggregate events to H3
    events_h3_file = tmp_path / "events_r5.parquet"
    aggregate_events_to_h3(
        events_file=events_fixture,
        population_file=synthetic_population_h3,
        output_file=events_h3_file,
        resolution=5,
        config=config,
    )

    # Step 2: Export to GeoJSONL
    conn = duckdb.connect()
    conn.execute("INSTALL h3 FROM community; LOAD h3; INSTALL spatial; LOAD spatial")
    conn.execute(f"CREATE VIEW events AS SELECT * FROM '{events_h3_file}'")

    geojson_file = tmp_path / "h3_r5.geojsonl.gz"
    export_h3_to_geojson(
        conn=conn,
        events_table="events",
        output_file=geojson_file,
    )
    conn.close()

    # Verify output
    assert geojson_file.exists(), "GeoJSONL file not created"

    # Load and validate
    with gzip.open(geojson_file, "rt") as f:
        lines = f.readlines()

    # Should have multiple features (one per H3 cell)
    assert len(lines) > 0, "GeoJSONL is empty"

    # Validate first feature structure
    feature = json.loads(lines[0])
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Polygon"

    props = feature["properties"]
    required_props = [
        "h3_cell",
        "total_count",
        "traffic_count",
        "property_count",
        "violence_count",
        "narcotics_count",
        "fraud_count",
        "public_order_count",
        "weapons_count",
        "other_count",
        "type_counts",
        "population",
        "rate_per_10000",
    ]
    for prop in required_props:
        assert prop in props, f"Missing property: {prop}"

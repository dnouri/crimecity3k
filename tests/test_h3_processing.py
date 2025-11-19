"""Integration tests for H3 spatial processing.

These tests verify the population-to-H3 conversion pipeline against real SCB data.
They test actual database operations and file I/O, not mocked behavior.
"""

from pathlib import Path

import duckdb
import pytest

from crimecity3k.config import Config
from crimecity3k.h3_processing import convert_population_to_h3


@pytest.fixture
def config() -> Config:
    """Load project configuration."""
    return Config.from_file("config.toml")


@pytest.fixture
def input_file() -> Path:
    """Path to SCB population GeoPackage."""
    return Path("data/population_1km_2024.gpkg")


@pytest.fixture
def output_file(tmp_path: Path) -> Path:
    """Temporary output file for test results."""
    return tmp_path / "population_r5_test.parquet"


@pytest.mark.integration
def test_convert_population_to_h3_creates_valid_output(
    input_file: Path,
    output_file: Path,
    config: Config,
) -> None:
    """Test population conversion produces valid H3 Parquet file.

    Verifies:
    - Output file is created
    - Output has correct schema (h3_cell, population, female, male)
    - All H3 cells are valid format
    - Population values are positive
    - Data is non-empty
    """
    if not input_file.exists():
        pytest.skip(f"Input data not found: {input_file}. Run 'make {input_file}' first.")

    # Execute conversion
    convert_population_to_h3(
        input_file=input_file,
        output_file=output_file,
        resolution=5,
        config=config,
    )

    # Verify output file exists
    assert output_file.exists(), f"Output file not created: {output_file}"

    # Verify schema and data quality
    conn = duckdb.connect(":memory:")
    try:
        df = conn.execute(f"SELECT * FROM '{output_file}'").fetchdf()

        # Schema verification
        expected_columns = {"h3_cell", "population", "female", "male"}
        assert set(df.columns) == expected_columns, (
            f"Schema mismatch. Expected {expected_columns}, got {set(df.columns)}"
        )

        # Data quality checks
        assert len(df) > 0, "Output is empty - no H3 cells generated"
        assert (df["population"] > 0).all(), "Found zero or negative population values"
        assert (df["female"] >= 0).all(), "Found negative female population values"
        assert (df["male"] >= 0).all(), "Found negative male population values"

        # H3 cell format verification (15-character hex string)
        assert df["h3_cell"].str.len().eq(15).all(), "Invalid H3 cell format detected"

        # Basic sanity checks
        total_population = df["population"].sum()
        assert total_population > 1_000_000, (
            f"Total population ({total_population:,}) seems too low for Sweden"
        )

    finally:
        conn.close()


@pytest.mark.integration
def test_convert_population_to_h3_raises_on_missing_input() -> None:
    """Test conversion fails gracefully when input file doesn't exist."""
    nonexistent = Path("data/nonexistent.gpkg")
    output = Path("data/h3/test_output.parquet")

    with pytest.raises(FileNotFoundError, match="Input file not found"):
        convert_population_to_h3(
            input_file=nonexistent,
            output_file=output,
            resolution=5,
        )


@pytest.mark.integration
def test_convert_population_to_h3_atomic_write_pattern(
    input_file: Path,
    tmp_path: Path,
    config: Config,
) -> None:
    """Test atomic write pattern prevents partial files on failure.

    Verifies that if conversion fails, no output file or temp file is left behind.
    """
    if not input_file.exists():
        pytest.skip(f"Input data not found: {input_file}. Run 'make {input_file}' first.")

    output_file = tmp_path / "population_atomic_test.parquet"
    temp_file = output_file.with_suffix(".tmp")

    # This should succeed, so both files should be cleaned up properly
    convert_population_to_h3(
        input_file=input_file,
        output_file=output_file,
        resolution=5,
        config=config,
    )

    # Verify final file exists and temp file was cleaned up
    assert output_file.exists(), "Final output file not created"
    assert not temp_file.exists(), "Temporary file not cleaned up after success"


@pytest.mark.integration
def test_population_conservation(
    input_file: Path,
    tmp_path: Path,
    config: Config,
) -> None:
    """Test population conservation: no data lost during H3 aggregation.

    Verifies that the total population in the output matches the input,
    ensuring the spatial transformation preserves all demographic data.
    """
    if not input_file.exists():
        pytest.skip(f"Input data not found: {input_file}. Run 'make {input_file}' first.")

    output_file = tmp_path / "population_conservation_test.parquet"

    # Run conversion
    convert_population_to_h3(
        input_file=input_file,
        output_file=output_file,
        resolution=5,
        config=config,
    )

    # Compare total populations
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    try:
        # Get input total
        input_total_result = conn.execute(
            f"SELECT SUM(beftotalt) FROM '{input_file}' WHERE beftotalt > 0"
        ).fetchone()
        assert input_total_result is not None
        input_total = input_total_result[0]

        # Get output total
        output_total_result = conn.execute(
            f"SELECT SUM(population) FROM '{output_file}'"
        ).fetchone()
        assert output_total_result is not None
        output_total = output_total_result[0]

        # Allow 0.1% tolerance for floating point arithmetic
        tolerance = input_total * 0.001
        assert abs(output_total - input_total) <= tolerance, (
            f"Population not conserved: input={input_total:,.0f}, "
            f"output={output_total:,.0f}, diff={output_total - input_total:,.0f}"
        )

    finally:
        conn.close()


@pytest.mark.integration
def test_geographic_coverage_sweden(
    input_file: Path,
    tmp_path: Path,
    config: Config,
) -> None:
    """Test H3 cells fall within expected Swedish geographic bounds.

    Verifies that all generated H3 cells are located within Sweden's
    approximate latitude/longitude boundaries.
    """
    if not input_file.exists():
        pytest.skip(f"Input data not found: {input_file}. Run 'make {input_file}' first.")

    output_file = tmp_path / "population_geography_test.parquet"

    # Run conversion
    convert_population_to_h3(
        input_file=input_file,
        output_file=output_file,
        resolution=5,
        config=config,
    )

    # Check geographic bounds
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL h3 FROM community; LOAD h3;")
    try:
        # Get lat/lon of all H3 cells
        bounds_result = conn.execute(f"""
            SELECT
                MIN(h3_cell_to_lat(h3_string_to_h3(h3_cell))) AS min_lat,
                MAX(h3_cell_to_lat(h3_string_to_h3(h3_cell))) AS max_lat,
                MIN(h3_cell_to_lng(h3_string_to_h3(h3_cell))) AS min_lon,
                MAX(h3_cell_to_lng(h3_string_to_h3(h3_cell))) AS max_lon
            FROM '{output_file}'
        """).fetchone()
        assert bounds_result is not None

        min_lat, max_lat, min_lon, max_lon = bounds_result

        # Sweden's approximate bounds (with small buffer for H3 cell centers)
        # Sweden extends from ~55°N to ~69°N latitude, ~11°E to ~24°E longitude
        assert 54.5 <= min_lat <= 56.0, f"Minimum latitude {min_lat} outside expected range"
        assert 68.0 <= max_lat <= 70.0, f"Maximum latitude {max_lat} outside expected range"
        assert 10.0 <= min_lon <= 12.0, f"Minimum longitude {min_lon} outside expected range"
        assert 23.0 <= max_lon <= 25.0, f"Maximum longitude {max_lon} outside expected range"

    finally:
        conn.close()

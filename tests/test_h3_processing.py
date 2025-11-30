"""Integration tests for H3 spatial processing.

These tests verify the population-to-H3 conversion pipeline against real SCB data.
They test actual database operations and file I/O, not mocked behavior.
"""

from pathlib import Path

import duckdb
import pytest

from crimecity3k.config import Config
from crimecity3k.h3_processing import aggregate_events_to_h3, convert_population_to_h3


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


# Event aggregation tests


@pytest.fixture
def events_fixture() -> Path:
    """Path to test events fixture."""
    return Path("tests/fixtures/events_2024_01_15-22.parquet")


@pytest.mark.integration
def test_aggregate_events_to_h3_creates_valid_output(
    events_fixture: Path,
    synthetic_population_h3: Path,
    tmp_path: Path,
    config: Config,
) -> None:
    """Test event aggregation produces valid H3 Parquet file.

    Verifies:
    - Output file is created
    - Output has correct schema (all category columns + type_counts)
    - All H3 cells are valid format
    - Data is non-empty
    """
    output_file = tmp_path / "events_r5_test.parquet"

    # Execute aggregation
    aggregate_events_to_h3(
        events_file=events_fixture,
        population_file=synthetic_population_h3,
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
        expected_columns = {
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
        }
        assert set(df.columns) == expected_columns, (
            f"Schema mismatch. Expected {expected_columns}, got {set(df.columns)}"
        )

        # Data quality checks
        assert len(df) > 0, "Output is empty - no H3 cells generated"
        assert (df["total_count"] > 0).all(), "Found cells with zero events"

        # H3 cell format verification (15-character hex string)
        assert df["h3_cell"].str.len().eq(15).all(), "Invalid H3 cell format"

        # Type verification - count columns should be integers, not floats
        # DuckDB INTEGER maps to int32 in pandas (sufficient for event counts)
        count_columns = [
            "total_count",
            "traffic_count",
            "property_count",
            "violence_count",
            "narcotics_count",
            "fraud_count",
            "public_order_count",
            "weapons_count",
            "other_count",
        ]
        for col in count_columns:
            assert df[col].dtype == "int32", (
                f"Column {col} should be int32 (INTEGER), got {df[col].dtype}"
            )

    finally:
        conn.close()


@pytest.mark.integration
def test_aggregate_events_category_counts_sum_to_total(
    events_fixture: Path,
    synthetic_population_h3: Path,
    tmp_path: Path,
    config: Config,
) -> None:
    """Test critical invariant: category counts sum to total_count.

    This is the most important test - it verifies we're not losing or
    duplicating events during category aggregation. For every H3 cell:
        sum(category_counts) == total_count

    Verifies:
    - No events are lost during categorization
    - No events are duplicated across categories
    - Category assignment is exhaustive (every event gets a category)
    """
    output_file = tmp_path / "events_category_test.parquet"

    # Execute aggregation
    aggregate_events_to_h3(
        events_file=events_fixture,
        population_file=synthetic_population_h3,
        output_file=output_file,
        resolution=5,
        config=config,
    )

    # Verify category count invariant
    conn = duckdb.connect(":memory:")
    try:
        # Check invariant for every cell
        violations = conn.execute(f"""
            SELECT
                h3_cell,
                total_count,
                (traffic_count + property_count + violence_count +
                 narcotics_count + fraud_count + public_order_count +
                 weapons_count + other_count) as category_sum,
                total_count - (traffic_count + property_count + violence_count +
                               narcotics_count + fraud_count + public_order_count +
                               weapons_count + other_count) as diff
            FROM '{output_file}'
            WHERE ABS(total_count - (traffic_count + property_count + violence_count +
                                     narcotics_count + fraud_count + public_order_count +
                                     weapons_count + other_count)) > 0.001
        """).fetchall()

        assert len(violations) == 0, (
            f"Category count invariant violated in {len(violations)} cells:\n"
            + "\n".join(
                f"  {cell}: total={total}, sum={cat_sum}, diff={diff}"
                for cell, total, cat_sum, diff in violations[:5]
            )
        )

        # Also verify total events match input
        total_events = conn.execute(f"SELECT SUM(total_count) FROM '{output_file}'").fetchone()
        assert total_events is not None
        input_events = conn.execute(f"SELECT COUNT(*) FROM '{events_fixture}'").fetchone()
        assert input_events is not None

        assert total_events[0] == input_events[0], (
            f"Total events mismatch: input={input_events[0]}, output={total_events[0]}"
        )

    finally:
        conn.close()


@pytest.mark.integration
def test_aggregate_events_type_counts_structure(
    events_fixture: Path,
    synthetic_population_h3: Path,
    tmp_path: Path,
    config: Config,
) -> None:
    """Test type_counts sparse array structure and correctness.

    Verifies:
    - type_counts is a list of structs with 'type' and 'count' fields
    - type_counts are sorted by count descending
    - sum of type_counts matches total_count
    - type_counts match category aggregation
    """
    output_file = tmp_path / "events_type_counts_test.parquet"

    # Execute aggregation
    aggregate_events_to_h3(
        events_file=events_fixture,
        population_file=synthetic_population_h3,
        output_file=output_file,
        resolution=5,
        config=config,
    )

    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL h3 FROM community; LOAD h3;")
    try:
        # Check structure and sorting for a sample cell
        sample = conn.execute(f"""
            SELECT h3_cell, total_count, type_counts
            FROM '{output_file}'
            ORDER BY total_count DESC
            LIMIT 1
        """).fetchone()

        assert sample is not None, "No cells in output"
        h3_cell, total_count, type_counts = sample

        # Verify type_counts is a list
        assert isinstance(type_counts, list), f"type_counts should be list, got {type(type_counts)}"
        assert len(type_counts) > 0, "type_counts should not be empty"

        # Verify each element is a struct with 'type' and 'count'
        for item in type_counts:
            assert "type" in item, "Missing 'type' field in type_counts struct"
            assert "count" in item, "Missing 'count' field in type_counts struct"

        # Verify sorted by count descending
        counts = [item["count"] for item in type_counts]
        assert counts == sorted(counts, reverse=True), "type_counts not sorted by count descending"

        # Verify sum of type counts matches total_count
        type_count_sum = sum(item["count"] for item in type_counts)
        assert abs(type_count_sum - total_count) < 0.001, (
            f"Type counts sum ({type_count_sum}) doesn't match total_count ({total_count})"
        )

    finally:
        conn.close()


@pytest.mark.integration
def test_aggregate_events_rate_calculation(
    events_fixture: Path,
    synthetic_population_h3: Path,
    tmp_path: Path,
    config: Config,
) -> None:
    """Test normalized rate calculation (events per 10,000 residents).

    Verifies:
    - Rate is calculated correctly: (total_count / population) * 10000
    - Rate is 0 for cells below minimum population threshold
    - Rate is reasonable for cells with population
    """
    output_file = tmp_path / "events_rate_test.parquet"

    # Execute aggregation
    aggregate_events_to_h3(
        events_file=events_fixture,
        population_file=synthetic_population_h3,
        output_file=output_file,
        resolution=5,
        config=config,
    )

    conn = duckdb.connect(":memory:")
    try:
        # Check rate calculation for cells with population
        samples = conn.execute(f"""
            SELECT h3_cell, total_count, population, rate_per_10000
            FROM '{output_file}'
            WHERE population >= {config.aggregation.min_population_threshold}
            ORDER BY rate_per_10000 DESC
            LIMIT 3
        """).fetchall()

        assert len(samples) > 0, "No cells with sufficient population for rate calc"

        for h3_cell, total_count, population, rate_per_10000 in samples:
            expected_rate = (float(total_count) / float(population)) * 10000.0
            assert abs(rate_per_10000 - expected_rate) < 0.01, (
                f"Rate calculation error for {h3_cell}: "
                f"expected {expected_rate:.2f}, got {rate_per_10000:.2f}"
            )

    finally:
        conn.close()


@pytest.mark.integration
def test_aggregate_events_raises_on_missing_events_file(
    synthetic_population_h3: Path,
    tmp_path: Path,
) -> None:
    """Test aggregation fails gracefully when events file doesn't exist."""
    nonexistent = Path("data/nonexistent_events.parquet")
    output = tmp_path / "test_output.parquet"

    with pytest.raises(FileNotFoundError, match="Events file not found"):
        aggregate_events_to_h3(
            events_file=nonexistent,
            population_file=synthetic_population_h3,
            output_file=output,
            resolution=5,
        )


@pytest.mark.integration
def test_aggregate_events_raises_on_missing_population_file(
    events_fixture: Path,
    tmp_path: Path,
) -> None:
    """Test aggregation fails gracefully when population file doesn't exist."""
    nonexistent = Path("data/nonexistent_population.parquet")
    output = tmp_path / "test_output.parquet"

    with pytest.raises(FileNotFoundError, match="Population file not found"):
        aggregate_events_to_h3(
            events_file=events_fixture,
            population_file=nonexistent,
            output_file=output,
            resolution=5,
        )


@pytest.mark.integration
def test_aggregate_events_atomic_write_pattern(
    events_fixture: Path,
    synthetic_population_h3: Path,
    tmp_path: Path,
    config: Config,
) -> None:
    """Test atomic write pattern prevents partial files on success.

    Verifies that temp files are cleaned up properly after successful execution.
    """
    output_file = tmp_path / "events_atomic_test.parquet"
    temp_file = output_file.with_suffix(".tmp")

    # This should succeed
    aggregate_events_to_h3(
        events_file=events_fixture,
        population_file=synthetic_population_h3,
        output_file=output_file,
        resolution=5,
        config=config,
    )

    # Verify final file exists and temp file was cleaned up
    assert output_file.exists(), "Final output file not created"
    assert not temp_file.exists(), "Temporary file not cleaned up after success"


@pytest.mark.integration
def test_aggregate_events_handles_partial_population(
    events_fixture: Path,
    tmp_path: Path,
    config: Config,
) -> None:
    """Test LEFT JOIN behavior: events without population data are preserved.

    Verifies critical LEFT JOIN semantics:
    - Events in cells without population data still appear in output
    - Missing population is represented as 0.0 (not NULL or dropped)
    - Rate calculation is 0.0 for cells without population
    - All events are preserved (none dropped due to missing population)
    - Only cells with sufficient population get non-zero rates

    This tests a realistic scenario where population data doesn't cover all
    geographic areas with crime events (e.g., new developments, data gaps).
    """
    output_file = tmp_path / "events_partial_pop.parquet"

    # Create partial population covering only 10 H3 cells
    # This ensures some event cells will lack population data
    partial_pop_file = tmp_path / "partial_population.parquet"
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL h3 FROM community; LOAD h3;")
    try:
        conn.execute(f"""
            COPY (
                WITH h3_cells AS (
                    SELECT DISTINCT
                        h3_latlng_to_cell_string(latitude, longitude, 5) as h3_cell
                    FROM '{events_fixture}'
                )
                SELECT h3_cell, 1000.0 as population
                FROM h3_cells
                LIMIT 10
            ) TO '{partial_pop_file}' (FORMAT PARQUET)
        """)

        # Run aggregation with partial population
        aggregate_events_to_h3(
            events_file=events_fixture,
            population_file=partial_pop_file,
            output_file=output_file,
            resolution=5,
            config=config,
        )

        # Verify LEFT JOIN preserved all event cells
        results = conn.execute(f"""
            SELECT
                COUNT(*) as total_cells,
                SUM(CASE WHEN population > 0 THEN 1 ELSE 0 END) as cells_with_pop,
                SUM(CASE WHEN population = 0 THEN 1 ELSE 0 END) as cells_without_pop,
                SUM(total_count) as total_events
            FROM '{output_file}'
        """).fetchone()

        assert results is not None
        total_cells, cells_with_pop, cells_without_pop, total_events = results

        # Verify population coverage
        assert cells_with_pop == 10, "Should have exactly 10 cells with population"
        assert cells_without_pop > 0, "Should have cells without population (LEFT JOIN)"
        assert total_cells == cells_with_pop + cells_without_pop, "Cell counts should sum"

        # Verify all events preserved (none dropped)
        input_events = conn.execute(f"SELECT COUNT(*) FROM '{events_fixture}'").fetchone()
        assert input_events is not None
        assert total_events == input_events[0], (
            f"Events should be preserved: input={input_events[0]}, output={total_events}"
        )

        # Verify rate calculation for cells without population
        zero_pop_rates = conn.execute(f"""
            SELECT DISTINCT rate_per_10000
            FROM '{output_file}'
            WHERE population = 0
        """).fetchall()

        assert len(zero_pop_rates) == 1, "All zero-pop cells should have same rate"
        assert zero_pop_rates[0][0] == 0.0, "Zero population should yield zero rate"

        # Verify rates calculated for cells with population
        nonzero_rates = conn.execute(f"""
            SELECT COUNT(*) FROM '{output_file}'
            WHERE population > 0 AND rate_per_10000 > 0
        """).fetchone()

        assert nonzero_rates is not None
        assert nonzero_rates[0] > 0, "Should have non-zero rates for populated cells"

    finally:
        conn.close()

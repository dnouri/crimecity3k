"""Shared pytest fixtures for CrimeCity3K tests."""

from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest

from crimecity3k.config import Config


@pytest.fixture
def test_config() -> Config:
    """Create test configuration with safe defaults.

    Returns:
        Config object with test-specific settings
    """
    config = Config()
    # Override for tests
    config.aggregation.resolutions = [5]
    config.duckdb.memory_limit = "1GB"
    config.duckdb.threads = 1
    config.duckdb.temp_directory = "/tmp/test_duckdb"
    return config


@pytest.fixture
def duckdb_conn(
    test_config: Config,
) -> Generator[duckdb.DuckDBPyConnection]:
    """In-memory DuckDB with h3 and spatial extensions.

    Following aviation-anomaly pattern for reliable extension loading in CI.

    Args:
        test_config: Test configuration fixture

    Yields:
        Configured DuckDB connection

    Note:
        Connection is automatically closed after test
    """
    conn = duckdb.connect(":memory:")

    # Apply basic DuckDB settings
    conn.execute(f"SET memory_limit = '{test_config.duckdb.memory_limit}'")
    conn.execute(f"SET threads = {test_config.duckdb.threads}")

    # Install and load spatial extension (core extension)
    try:
        conn.execute("INSTALL spatial")
        conn.execute("LOAD spatial")
    except Exception as e:
        pytest.skip(f"Spatial extension not available: {e}")

    # Install and load H3 extension from community repository
    try:
        conn.execute("INSTALL h3 FROM community")
        conn.execute("LOAD h3")
    except Exception as e:
        pytest.fail(f"H3 extension is required but failed to load: {e}")

    yield conn
    conn.close()


@pytest.fixture
def sample_events(duckdb_conn: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """Load test fixture events into DuckDB.

    Args:
        duckdb_conn: DuckDB connection fixture

    Returns:
        DuckDB connection with 'events' table loaded
    """
    fixture_path = Path(__file__).parent / "fixtures" / "events_2024_01_15-22.parquet"
    duckdb_conn.execute(f"""
        CREATE TABLE events AS
        SELECT * FROM '{fixture_path}'
    """)
    return duckdb_conn


@pytest.fixture
def synthetic_population_h3(tmp_path: Path, duckdb_conn: duckdb.DuckDBPyConnection) -> Path:
    """Create synthetic population data for H3 cells in test fixture.

    Creates a minimal population dataset with 1000 people per H3 cell,
    covering all cells in the events test fixture.

    Args:
        tmp_path: Pytest temporary directory fixture
        duckdb_conn: DuckDB connection with H3 extension

    Returns:
        Path to synthetic population Parquet file
    """
    fixture_path = Path(__file__).parent / "fixtures" / "events_2024_01_15-22.parquet"
    population_path = tmp_path / "synthetic_population_r5.parquet"

    duckdb_conn.execute(f"""
        COPY (
            WITH h3_cells AS (
                SELECT DISTINCT h3_latlng_to_cell_string(latitude, longitude, 5) as h3_cell
                FROM '{fixture_path}'
            )
            SELECT
                h3_cell,
                1000.0 as population
            FROM h3_cells
        ) TO '{population_path}' (FORMAT PARQUET)
    """)

    return population_path

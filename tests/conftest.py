"""Shared pytest fixtures for CrimeCity3K tests."""

from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest

from crimecity3k.config import Config
from crimecity3k.data_access import create_configured_connection


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

    Args:
        test_config: Test configuration fixture

    Yields:
        Configured DuckDB connection

    Note:
        Connection is automatically closed after test
    """
    conn = create_configured_connection(test_config, extensions=["h3", "spatial"])
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

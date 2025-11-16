"""Tests for DuckDB connection management."""

import duckdb

from crimecity3k.config import Config
from crimecity3k.data_access import create_configured_connection


def test_duckdb_h3_extension(duckdb_conn: duckdb.DuckDBPyConnection) -> None:
    """Test H3 extension loads and works."""
    result = duckdb_conn.execute("SELECT h3_latlng_to_cell(59.3293, 18.0686, 5)").fetchone()
    assert result is not None
    assert result[0] is not None
    assert isinstance(result[0], int)


def test_duckdb_spatial_extension(duckdb_conn: duckdb.DuckDBPyConnection) -> None:
    """Test spatial extension loads and works."""
    result = duckdb_conn.execute("SELECT ST_AsText(ST_Point(18.0686, 59.3293))").fetchone()
    assert result is not None
    assert "POINT" in result[0]


def test_sample_events_fixture(sample_events: duckdb.DuckDBPyConnection) -> None:
    """Test sample events loads correctly."""
    count = sample_events.execute("SELECT COUNT(*) FROM events").fetchone()
    assert count is not None
    assert count[0] == 476


def test_sample_events_schema(sample_events: duckdb.DuckDBPyConnection) -> None:
    """Test sample events has expected schema."""
    columns = sample_events.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'events'"
    ).fetchall()

    column_names = [col[0] for col in columns]
    expected_columns = [
        "event_id",
        "datetime",
        "name",
        "summary",
        "url",
        "type",
        "location_name",
        "latitude",
        "longitude",
    ]

    for expected in expected_columns:
        assert expected in column_names, f"Missing column: {expected}"


def test_configured_connection_settings(test_config: Config) -> None:
    """Test connection applies config settings."""
    conn = create_configured_connection(test_config)

    # Verify memory limit was set (DuckDB may format it differently)
    result = conn.execute(
        "SELECT value FROM duckdb_settings() WHERE name = 'memory_limit'"
    ).fetchone()
    assert result is not None
    # Accept any format that contains GB or GiB or MiB
    memory_value = result[0].lower()
    expected_units = ["gb", "gib", "mib"]
    assert any(unit in memory_value for unit in expected_units), (
        f"Unexpected memory format: {result[0]}"
    )

    # Verify threads were set
    result = conn.execute("SELECT value FROM duckdb_settings() WHERE name = 'threads'").fetchone()
    assert result is not None
    assert int(result[0]) == 1

    conn.close()

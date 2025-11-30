"""Tile generation for map visualization.

This module provides functions for exporting H3-aggregated crime data to
GeoJSON format suitable for web visualization and PMTiles generation.
"""

import logging
from pathlib import Path

import duckdb
from qck import qck  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


def export_h3_to_geojson(
    conn: duckdb.DuckDBPyConnection,
    events_table: str,
    output_file: Path,
) -> None:
    """Export H3 aggregated crime data to GeoJSONL format.

    Outputs newline-delimited GeoJSON (one feature per line) for memory-efficient
    streaming and processing of large datasets. Output is gzip compressed.

    Args:
        conn: DuckDB connection with h3 and spatial extensions loaded
        events_table: Name of table/view with H3 aggregated crime data
        output_file: Path to write GeoJSONL output (will be gzip compressed)

    Raises:
        RuntimeError: If SQL execution fails

    Example:
        >>> conn = duckdb.connect()
        >>> conn.execute("INSTALL h3 FROM community; LOAD h3; INSTALL spatial; LOAD spatial")
        >>> export_h3_to_geojson(conn, "events_r5", Path("data/tiles/h3_r5.geojsonl.gz"))
    """
    # Use SQL template that includes the COPY TO statement
    sql_path = Path(__file__).parent / "sql" / "h3_to_geojson.sql"

    # Atomic write pattern
    temp_file = output_file.with_suffix(".tmp")

    params = {
        "events_table": events_table,
        "output_file": str(temp_file),
    }

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Exporting {events_table} to GeoJSONL")
    logger.info(f"  Output: {output_file}")

    try:
        # Execute the SQL with qck - it handles templating and runs COPY TO
        qck(str(sql_path), params=params, connection=conn)
        temp_file.rename(output_file)

        # Log file size
        file_size_kb = output_file.stat().st_size / 1024
        logger.info(f"  Result: {file_size_kb:.1f} KB compressed GeoJSONL")

    except Exception as e:
        if temp_file.exists():
            temp_file.unlink()
        logger.error(f"GeoJSON export failed: {e}")
        raise RuntimeError(f"Failed to export H3 to GeoJSON: {e}") from e

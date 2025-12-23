"""Municipality tile generation for map visualization.

This module provides functions for exporting municipality-aggregated crime data
to GeoJSON format and generating PMTiles for web visualization.
"""

import gzip
import json
import logging
import subprocess
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


def export_municipalities_to_geojsonl(
    boundaries_file: Path,
    events_file: Path,
    output_file: Path,
) -> None:
    """Export municipality data to GeoJSONL format.

    Joins municipality boundaries (GeoJSON) with aggregated events (Parquet)
    and outputs newline-delimited GeoJSON with gzip compression.

    Args:
        boundaries_file: Path to municipality boundaries GeoJSON
        events_file: Path to municipality events Parquet
        output_file: Path for output GeoJSONL (will be gzip compressed)

    Raises:
        FileNotFoundError: If input files don't exist
        RuntimeError: If export fails
    """
    if not boundaries_file.exists():
        raise FileNotFoundError(f"Boundaries file not found: {boundaries_file}")
    if not events_file.exists():
        raise FileNotFoundError(f"Events file not found: {events_file}")

    # Load boundaries GeoJSON
    with open(boundaries_file, encoding="utf-8") as f:
        boundaries = json.load(f)

    # Load events data
    conn = duckdb.connect()
    events_df = conn.execute(f"SELECT * FROM '{events_file}'").fetchdf()
    conn.close()

    # Create lookup by kommun_kod
    events_lookup = {row["kommun_kod"]: row for _, row in events_df.iterrows()}

    # Atomic write pattern
    temp_file = output_file.with_suffix(".tmp")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Exporting municipalities to GeoJSONL")
    logger.info(f"  Boundaries: {boundaries_file}")
    logger.info(f"  Events: {events_file}")
    logger.info(f"  Output: {output_file}")

    def get_int(row: dict | None, key: str, default: int = 0) -> int:
        """Get integer value from row or return default."""
        return int(row[key]) if row is not None else default

    def get_float(row: dict | None, key: str, default: float = 0.0) -> float:
        """Get float value from row or return default."""
        return float(row[key]) if row is not None else default

    try:
        with gzip.open(temp_file, "wt", encoding="utf-8") as f:
            for boundary_feature in boundaries["features"]:
                # Get kommun_kod from boundary properties
                kommun_kod = boundary_feature["properties"]["id"]

                # Get events data for this municipality
                row = events_lookup.get(kommun_kod)

                # Build output feature
                feature = {
                    "type": "Feature",
                    "geometry": boundary_feature["geometry"],
                    "properties": {
                        "kommun_kod": kommun_kod,
                        "kommun_namn": boundary_feature["properties"]["kom_namn"],
                        "total_count": get_int(row, "total_count"),
                        "traffic_count": get_int(row, "traffic_count"),
                        "property_count": get_int(row, "property_count"),
                        "violence_count": get_int(row, "violence_count"),
                        "narcotics_count": get_int(row, "narcotics_count"),
                        "fraud_count": get_int(row, "fraud_count"),
                        "public_order_count": get_int(row, "public_order_count"),
                        "weapons_count": get_int(row, "weapons_count"),
                        "other_count": get_int(row, "other_count"),
                        "population": get_int(row, "population"),
                    },
                }

                f.write(json.dumps(feature, ensure_ascii=False) + "\n")

        # Atomic rename on success
        temp_file.rename(output_file)

        # Log file size
        file_size_kb = output_file.stat().st_size / 1024
        logger.info(f"  Result: {file_size_kb:.1f} KB compressed GeoJSONL")

    except Exception as e:
        if temp_file.exists():
            temp_file.unlink()
        logger.error(f"Municipality GeoJSONL export failed: {e}")
        raise RuntimeError(f"Failed to export municipalities to GeoJSONL: {e}") from e


def build_municipality_tippecanoe_command(
    input_file: Path,
    output_file: Path,
) -> list[str]:
    """Build Tippecanoe command for municipality tiles.

    Args:
        input_file: Input GeoJSONL file (gzip compressed)
        output_file: Output PMTiles file

    Returns:
        Command as list of strings for subprocess
    """
    # Key attributes to preserve for client-side filtering
    key_attributes = [
        "kommun_kod",
        "kommun_namn",
        "total_count",
        "traffic_count",
        "property_count",
        "violence_count",
        "narcotics_count",
        "fraud_count",
        "public_order_count",
        "weapons_count",
        "other_count",
        "population",
    ]

    cmd = [
        "tippecanoe",
        "-o",
        str(output_file),
        "--layer=municipalities",
        "--minimum-zoom=3",
        "--maximum-zoom=10",
        "--simplification=10",
        "--force",
        "--no-feature-limit",
        "--no-tile-size-limit",
    ]

    # Add -P flag for parallel parsing of newline-delimited GeoJSON
    suffix = input_file.suffix.lower()
    if suffix in (".geojsonl", ".gz"):
        cmd.append("-P")

    # Add attribute preservation
    for attr in key_attributes:
        cmd.extend(["--include", attr])

    # Input file last
    cmd.append(str(input_file))

    return cmd


def generate_municipality_pmtiles(
    input_file: Path,
    output_file: Path,
) -> Path:
    """Generate PMTiles from municipality GeoJSONL using Tippecanoe.

    Args:
        input_file: Input GeoJSONL file (gzip compressed)
        output_file: Output PMTiles file

    Returns:
        Path to generated PMTiles file

    Raises:
        FileNotFoundError: If input file doesn't exist
        RuntimeError: If Tippecanoe is not installed or generation fails
    """
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # Check Tippecanoe is installed
    try:
        result = subprocess.run(
            ["tippecanoe", "--version"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError("Tippecanoe not available")
    except FileNotFoundError:
        raise RuntimeError(
            "Tippecanoe is not installed. Install from https://github.com/mapbox/tippecanoe"
        ) from None

    cmd = build_municipality_tippecanoe_command(input_file, output_file)

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Generating municipality PMTiles")
    logger.debug(f"Command: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Tippecanoe failed with code {result.returncode}\nstderr: {result.stderr}"
        )

    if not output_file.exists():
        raise RuntimeError(f"Tippecanoe completed but output file not found: {output_file}")

    file_size_kb = output_file.stat().st_size / 1024
    logger.info(f"Generated PMTiles: {output_file} ({file_size_kb:.1f} KB)")

    return output_file

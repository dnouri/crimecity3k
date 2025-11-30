"""Generate PMTiles from GeoJSON using Tippecanoe.

This module provides functions to convert GeoJSONL exports to PMTiles format
for efficient web map tile serving. Uses Tippecanoe for tile generation.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def get_zoom_range_for_resolution(resolution: int) -> tuple[int, int]:
    """Get appropriate zoom range for H3 resolution.

    Maps H3 resolution to Mapbox/MapLibre zoom levels based on
    hexagon size and visual appearance at different zoom levels.

    Args:
        resolution: H3 resolution (4-6)

    Returns:
        Tuple of (min_zoom, max_zoom)

    Example:
        >>> get_zoom_range_for_resolution(5)
        (5, 9)
    """
    # H3 resolution to zoom ranges based on cell size
    # r4: ~25km edge, visible at z4-8 (city to regional view)
    # r5: ~8km edge, visible at z5-9 (neighborhood to city view)
    # r6: ~3km edge, visible at z6-10 (detailed to neighborhood view)
    zoom_ranges = {
        4: (4, 8),
        5: (5, 9),
        6: (6, 10),
    }
    return zoom_ranges.get(resolution, (resolution, resolution + 4))


def build_tippecanoe_command(
    input_file: Path,
    output_file: Path,
    min_zoom: int,
    max_zoom: int,
    preserve_attributes: list[str] | None = None,
) -> list[str]:
    """Build Tippecanoe command with appropriate parameters.

    Args:
        input_file: Input GeoJSONL file (newline-delimited, optionally gzipped)
        output_file: Output PMTiles file
        min_zoom: Minimum zoom level
        max_zoom: Maximum zoom level
        preserve_attributes: List of properties to preserve in tiles

    Returns:
        Command as list of strings for subprocess

    Example:
        >>> cmd = build_tippecanoe_command(Path("h3.geojsonl.gz"), Path("h3.pmtiles"), 5, 9)
        >>> cmd[0]
        'tippecanoe'
    """
    cmd = [
        "tippecanoe",
        "-o",
        str(output_file),
        "--layer=h3_cells",
        f"--minimum-zoom={min_zoom}",
        f"--maximum-zoom={max_zoom}",
        "--maximum-tile-features=10000",
        "--simplification=10",
        "--force",
        "--drop-densest-as-needed",
        "--extend-zooms-if-still-dropping",
    ]

    # Add -P flag for parallel parsing of newline-delimited GeoJSON
    suffix = input_file.suffix.lower()
    if suffix in (".geojsonl", ".gz"):
        cmd.append("-P")

    # Add attribute preservation
    if preserve_attributes:
        for attr in preserve_attributes:
            cmd.extend(["--include", attr])

    # Input file last
    cmd.append(str(input_file))

    return cmd


def check_tippecanoe_installed() -> bool:
    """Check if Tippecanoe is installed and available.

    Returns:
        True if Tippecanoe is available, False otherwise
    """
    try:
        result = subprocess.run(
            ["tippecanoe", "--version"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def generate_pmtiles(
    input_file: Path,
    output_file: Path,
    resolution: int,
) -> Path:
    """Generate PMTiles from GeoJSONL using Tippecanoe.

    Args:
        input_file: Input GeoJSONL file (gzip compressed)
        output_file: Output PMTiles file
        resolution: H3 resolution (determines zoom range)

    Returns:
        Path to generated PMTiles file

    Raises:
        FileNotFoundError: If input file doesn't exist
        RuntimeError: If Tippecanoe is not installed or generation fails

    Example:
        >>> generate_pmtiles(Path("h3_r5.geojsonl.gz"), Path("h3_r5.pmtiles"), 5)
        PosixPath('h3_r5.pmtiles')
    """
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    if not check_tippecanoe_installed():
        raise RuntimeError(
            "Tippecanoe is not installed. Install from https://github.com/mapbox/tippecanoe"
        )

    # Get zoom range for resolution
    min_zoom, max_zoom = get_zoom_range_for_resolution(resolution)

    # Key attributes to preserve for client-side filtering
    key_attributes = [
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

    cmd = build_tippecanoe_command(
        input_file=input_file,
        output_file=output_file,
        min_zoom=min_zoom,
        max_zoom=max_zoom,
        preserve_attributes=key_attributes,
    )

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Generating PMTiles for resolution {resolution}")
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

    file_size_mb = output_file.stat().st_size / (1024 * 1024)
    logger.info(
        f"Generated PMTiles: {output_file} ({file_size_mb:.1f} MB) "
        f"for zoom levels {min_zoom}-{max_zoom}"
    )

    return output_file

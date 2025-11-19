"""H3 spatial processing functions.

This module provides functions for converting spatial data to H3 hexagonal cells
and aggregating statistics at various resolutions. All functions use SQL templates
for the core transformations, with Python providing orchestration and error handling.
"""

import logging
from pathlib import Path

from qck import qck  # type: ignore[import-untyped]

from crimecity3k.config import Config
from crimecity3k.data_access import create_configured_connection

logger = logging.getLogger(__name__)


def convert_population_to_h3(
    input_file: Path,
    output_file: Path,
    resolution: int,
    config: Config | None = None,
) -> None:
    """Convert SCB population grid to H3 hexagonal cells.

    Executes the population_to_h3.sql template to transform Sweden's 1km²
    population grid into H3 cells at the specified resolution. Uses atomic
    write pattern to prevent partial files on failure.

    The conversion process:
    1. Extracts centroids from 1km grid polygons
    2. Maps centroids to H3 cells via lat/lon
    3. Aggregates population statistics by H3 cell
    4. Filters zero-population cells

    Args:
        input_file: Path to SCB population GeoPackage (1km grid, SWEREF99 TM)
        output_file: Path for output Parquet file (created by this function)
        resolution: H3 resolution (4=~25km, 5=~8km, 6=~3km edge length)
        config: Configuration object (loads from config.toml if None)

    Raises:
        FileNotFoundError: If input GeoPackage doesn't exist
        RuntimeError: If SQL execution fails (wraps underlying exception)

    Example:
        >>> from pathlib import Path
        >>> from crimecity3k.config import Config
        >>> config = Config.from_file("config.toml")
        >>> convert_population_to_h3(
        ...     Path("data/population_1km_2024.gpkg"),
        ...     Path("data/h3/population_r5.parquet"),
        ...     resolution=5,
        ...     config=config
        ... )
    """
    if config is None:
        config = Config.from_file("config.toml")

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # Atomic write pattern: write to temp file, rename on success
    # This prevents corrupted partial files if SQL execution fails
    temp_file = output_file.with_suffix(".tmp")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Locate SQL template relative to this module
    sql_path = Path(__file__).parent / "sql" / "population_to_h3.sql"

    # Build parameters for Jinja2 template rendering
    params = {
        "input_file": str(input_file),
        "output_file": str(temp_file),  # Write to .tmp first
        "resolution": resolution,
    }

    logger.info(f"Converting population to H3 resolution {resolution}")
    logger.info(f"  Input:  {input_file}")
    logger.info(f"  Output: {output_file}")

    # Execute SQL with configured connection (loads H3 and spatial extensions)
    conn = create_configured_connection(config, extensions=["h3", "spatial"])
    try:
        # qck renders Jinja2 template and executes SQL
        qck(str(sql_path), params=params, connection=conn)

        # Atomic rename on success (prevents partial files)
        temp_file.rename(output_file)

        # Log result summary
        count_result = conn.execute(f"SELECT COUNT(*) FROM '{output_file}'").fetchone()
        assert count_result is not None  # COUNT(*) always returns a row
        count = count_result[0]

        pop_result = conn.execute(f"SELECT SUM(population) FROM '{output_file}'").fetchone()
        assert pop_result is not None  # SUM always returns a row (NULL if empty, but not None)
        total_pop = pop_result[0]

        logger.info(f"  Result: {count:,} H3 cells, {total_pop:,} total population")

    except Exception as e:
        # Clean up temp file on any error
        if temp_file.exists():
            temp_file.unlink()
        logger.error(f"Population conversion failed: {e}")
        raise RuntimeError(f"Failed to convert population to H3: {e}") from e
    finally:
        conn.close()

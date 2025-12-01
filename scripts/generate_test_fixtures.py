#!/usr/bin/env python3
"""Generate test fixture PMTiles from test events data.

This script creates PMTiles for E2E tests by:
1. Creating synthetic population data (1000 per H3 cell)
2. Aggregating test events to H3 cells
3. Exporting to GeoJSONL
4. Generating PMTiles via Tippecanoe

Usage:
    python scripts/generate_test_fixtures.py
    # Or via Makefile:
    make test-fixtures
"""

import logging
import tempfile
from pathlib import Path

import duckdb

from crimecity3k.config import Config
from crimecity3k.h3_processing import aggregate_events_to_h3
from crimecity3k.pmtiles import generate_pmtiles
from crimecity3k.tile_generation import export_h3_to_geojson

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
EVENTS_FIXTURE = FIXTURES_DIR / "events_2024_01_15-22.parquet"
OUTPUT_DIR = FIXTURES_DIR / "pmtiles"

# Resolutions to generate (matches backend pipeline output)
RESOLUTIONS = [4, 5, 6]


def create_synthetic_population(
    conn: duckdb.DuckDBPyConnection,
    events_file: Path,
    output_file: Path,
    resolution: int,
) -> None:
    """Create synthetic population data for H3 cells in test events.

    Assigns 1000 population to each H3 cell that contains events.
    This allows normalized rate calculations without real population data.

    Args:
        conn: DuckDB connection with H3 extension loaded
        events_file: Path to events parquet file
        output_file: Path to write population parquet
        resolution: H3 resolution
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    conn.execute(f"""
        COPY (
            SELECT DISTINCT
                h3_latlng_to_cell_string(latitude, longitude, {resolution}) as h3_cell,
                1000.0 as population
            FROM '{events_file}'
        ) TO '{output_file}' (FORMAT PARQUET)
    """)

    count = conn.execute(f"SELECT COUNT(*) FROM '{output_file}'").fetchone()[0]
    logger.info(f"  Created synthetic population: {count} H3 cells")


def generate_fixtures_for_resolution(
    resolution: int,
    events_file: Path,
    output_dir: Path,
    config: Config,
) -> Path:
    """Generate PMTiles fixture for a single resolution.

    Args:
        resolution: H3 resolution (4, 5, or 6)
        events_file: Path to test events parquet
        output_dir: Directory for output PMTiles
        config: Configuration object

    Returns:
        Path to generated PMTiles file
    """
    logger.info(f"Generating fixtures for resolution {resolution}...")

    # Use temp directory for intermediate files
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Step 1: Create synthetic population
        pop_file = tmp_path / f"population_r{resolution}.parquet"
        conn = duckdb.connect()
        conn.execute("INSTALL h3 FROM community; LOAD h3")
        create_synthetic_population(conn, events_file, pop_file, resolution)

        # Step 2: Aggregate events to H3
        h3_file = tmp_path / f"events_r{resolution}.parquet"
        aggregate_events_to_h3(
            events_file=events_file,
            population_file=pop_file,
            output_file=h3_file,
            resolution=resolution,
            config=config,
        )

        # Step 3: Export to GeoJSONL
        geojson_file = tmp_path / f"h3_r{resolution}.geojsonl.gz"
        conn.execute("INSTALL spatial; LOAD spatial")
        conn.execute(f"CREATE VIEW events AS SELECT * FROM '{h3_file}'")
        export_h3_to_geojson(conn, "events", geojson_file)
        conn.close()

        # Step 4: Generate PMTiles
        output_dir.mkdir(parents=True, exist_ok=True)
        pmtiles_file = output_dir / f"h3_r{resolution}.pmtiles"
        generate_pmtiles(geojson_file, pmtiles_file, resolution)

        return pmtiles_file


def main() -> None:
    """Generate all test fixture PMTiles."""
    logger.info("=" * 60)
    logger.info("Generating test fixture PMTiles")
    logger.info("=" * 60)

    if not EVENTS_FIXTURE.exists():
        raise FileNotFoundError(f"Events fixture not found: {EVENTS_FIXTURE}")

    # Use default config with relaxed thresholds for test data
    config = Config()
    config.aggregation.min_population_threshold = 0  # No filtering for tests

    generated = []
    for resolution in RESOLUTIONS:
        pmtiles_path = generate_fixtures_for_resolution(
            resolution=resolution,
            events_file=EVENTS_FIXTURE,
            output_dir=OUTPUT_DIR,
            config=config,
        )
        generated.append(pmtiles_path)

    logger.info("")
    logger.info("=" * 60)
    logger.info("Test fixtures generated successfully:")
    for path in generated:
        size_kb = path.stat().st_size / 1024
        logger.info(f"  {path.name}: {size_kb:.1f} KB")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

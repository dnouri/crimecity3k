#!/usr/bin/env python3
"""Generate PMTiles fixtures for E2E tests.

This script creates municipality-based PMTiles for E2E tests by:
1. Copying municipality data files (boundaries, population) to test fixtures
2. Aggregating test events to municipalities
3. Exporting to GeoJSONL
4. Generating PMTiles via Tippecanoe
5. Copying static files

Usage:
    python scripts/generate_tile_fixtures.py
    # Or via Makefile:
    make test-fixtures
"""

import logging
import shutil
from pathlib import Path

from crimecity3k.municipality_processing import aggregate_events_to_municipalities
from crimecity3k.municipality_tiles import (
    export_municipalities_to_geojsonl,
    generate_municipality_pmtiles,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"

# Source data
MUNI_DIR = PROJECT_ROOT / "data" / "municipalities"
MUNI_BOUNDARIES = MUNI_DIR / "boundaries.geojson"
MUNI_POPULATION = MUNI_DIR / "population.csv"

# Test fixture paths
EVENTS_FIXTURE = FIXTURES_DIR / "data" / "events.parquet"
FIXTURES_MUNI_DIR = FIXTURES_DIR / "data" / "municipalities"
OUTPUT_DIR = FIXTURES_DIR / "data" / "tiles" / "pmtiles"


def copy_municipality_data() -> None:
    """Copy municipality data files to test fixtures directory."""
    FIXTURES_MUNI_DIR.mkdir(parents=True, exist_ok=True)

    # Copy boundaries
    dst_boundaries = FIXTURES_MUNI_DIR / "boundaries.geojson"
    needs_copy = not dst_boundaries.exists()
    needs_copy = needs_copy or dst_boundaries.stat().st_mtime < MUNI_BOUNDARIES.stat().st_mtime
    if needs_copy:
        shutil.copy2(MUNI_BOUNDARIES, dst_boundaries)
        logger.info(f"  Copied boundaries.geojson to {dst_boundaries}")
    else:
        logger.info("  Boundaries already up to date")

    # Copy population
    dst_population = FIXTURES_MUNI_DIR / "population.csv"
    needs_copy = not dst_population.exists()
    needs_copy = needs_copy or dst_population.stat().st_mtime < MUNI_POPULATION.stat().st_mtime
    if needs_copy:
        shutil.copy2(MUNI_POPULATION, dst_population)
        logger.info(f"  Copied population.csv to {dst_population}")
    else:
        logger.info("  Population already up to date")


def generate_municipality_fixtures() -> Path:
    """Generate municipality PMTiles fixture.

    Returns:
        Path to generated PMTiles file
    """
    logger.info("Generating municipality fixtures...")

    # Step 1: Aggregate events to municipalities
    events_parquet = FIXTURES_MUNI_DIR / "events.parquet"
    aggregate_events_to_municipalities(
        events_file=EVENTS_FIXTURE,
        population_file=FIXTURES_MUNI_DIR / "population.csv",
        output_file=events_parquet,
    )

    # Step 2: Export to GeoJSONL
    geojson_file = FIXTURES_DIR / "data" / "tiles" / "municipalities.geojsonl.gz"
    geojson_file.parent.mkdir(parents=True, exist_ok=True)
    export_municipalities_to_geojsonl(
        boundaries_file=FIXTURES_MUNI_DIR / "boundaries.geojson",
        events_file=events_parquet,
        output_file=geojson_file,
    )

    # Step 3: Generate PMTiles
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pmtiles_file = OUTPUT_DIR / "municipalities.pmtiles"
    generate_municipality_pmtiles(geojson_file, pmtiles_file)

    return pmtiles_file


def copy_static_files() -> None:
    """Copy static files to test fixtures directory."""
    src_dir = PROJECT_ROOT / "static"
    dst_dir = FIXTURES_DIR / "static"

    if dst_dir.exists():
        shutil.rmtree(dst_dir)

    shutil.copytree(src_dir, dst_dir)
    logger.info(f"Copied static files to {dst_dir}")


def main() -> None:
    """Generate all test fixture PMTiles and copy static files."""
    logger.info("=" * 60)
    logger.info("Generating test fixtures")
    logger.info("=" * 60)

    # Verify required source files exist
    if not EVENTS_FIXTURE.exists():
        raise FileNotFoundError(f"Events fixture not found: {EVENTS_FIXTURE}")
    if not MUNI_BOUNDARIES.exists():
        raise FileNotFoundError(f"Municipality boundaries not found: {MUNI_BOUNDARIES}")
    if not MUNI_POPULATION.exists():
        raise FileNotFoundError(f"Municipality population not found: {MUNI_POPULATION}")

    # Copy static files for test server
    copy_static_files()

    # Copy municipality data
    logger.info("")
    logger.info("Copying municipality data...")
    copy_municipality_data()

    # Generate municipality PMTiles
    logger.info("")
    pmtiles_path = generate_municipality_fixtures()

    logger.info("")
    logger.info("=" * 60)
    logger.info("Test fixtures generated successfully:")
    size_kb = pmtiles_path.stat().st_size / 1024
    logger.info(f"  {pmtiles_path.name}: {size_kb:.1f} KB")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

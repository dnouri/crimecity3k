#!/usr/bin/env python3
"""Create test population fixture from production data.

This script creates a small subset (~200 cells, ~144KB) of the production
population GeoPackage for use in tests. The subset is carefully selected to:

1. Overlap with H3 cells that have events in the test fixture
2. Include diverse population densities (from 3 to 24,630 per cell)
3. Cover 20 different H3 cells for geographic diversity

Usage:
    python scripts/create_population_fixture.py

Prerequisites:
    - Production data: data/population_1km_2024.gpkg
    - Test events fixture: tests/fixtures/data/events.parquet
"""

from pathlib import Path

import duckdb


def create_population_fixture(
    production_gpkg: Path,
    events_fixture: Path,
    output_gpkg: Path,
    cells_per_h3: int = 10,
    top_h3_cells: int = 20,
) -> None:
    """Create test population fixture from production data.

    Selects population cells that overlap with H3 cells containing test events,
    taking the top N most populated cells from each H3 cell for diversity.

    Args:
        production_gpkg: Path to production population GeoPackage
        events_fixture: Path to test events Parquet file
        output_gpkg: Path for output test fixture GeoPackage
        cells_per_h3: Number of population cells to sample per H3 cell
        top_h3_cells: Number of top H3 cells (by event count) to sample from
    """
    if not production_gpkg.exists():
        raise FileNotFoundError(f"Production data not found: {production_gpkg}")
    if not events_fixture.exists():
        raise FileNotFoundError(f"Events fixture not found: {events_fixture}")

    conn = duckdb.connect()
    conn.execute("INSTALL spatial; LOAD spatial")
    conn.execute("INSTALL h3 FROM community; LOAD h3")

    print(f"Creating population fixture from {production_gpkg}")

    # Create event H3 lookup (which H3 cells have events)
    conn.execute(f"""
        CREATE TEMP TABLE event_h3 AS
        SELECT
            h3_latlng_to_cell_string(latitude, longitude, 5) as h3_cell,
            COUNT(*) as event_count
        FROM '{events_fixture}'
        GROUP BY 1
    """)

    # Add population with H3 mapping
    conn.execute(f"""
        CREATE TEMP TABLE pop_with_h3 AS
        SELECT
            objectid,
            rutid_scb,
            rutstorl,
            beftotalt,
            kvinna,
            man,
            referenstid,
            sp_geometry,
            h3_latlng_to_cell_string(
                ST_Y(ST_Transform(ST_Centroid(sp_geometry), 'EPSG:3006', 'EPSG:4326', true)),
                ST_X(ST_Transform(ST_Centroid(sp_geometry), 'EPSG:3006', 'EPSG:4326', true)),
                5
            ) as h3_cell
        FROM st_read('{production_gpkg}')
        WHERE beftotalt > 0
    """)

    # Ensure output directory exists
    output_gpkg.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing file if present
    if output_gpkg.exists():
        output_gpkg.unlink()

    # Select subset: top N population cells from top M H3 cells (by event count)
    conn.execute(f"""
        COPY (
            WITH target_h3 AS (
                SELECT
                    e.h3_cell,
                    e.event_count
                FROM event_h3 e
                JOIN pop_with_h3 p ON e.h3_cell = p.h3_cell
                GROUP BY e.h3_cell, e.event_count
                ORDER BY e.event_count DESC
                LIMIT {top_h3_cells}
            ),
            ranked AS (
                SELECT
                    p.objectid, p.rutid_scb, p.rutstorl, p.beftotalt,
                    p.kvinna, p.man, p.referenstid, p.sp_geometry,
                    ROW_NUMBER() OVER (PARTITION BY p.h3_cell ORDER BY p.beftotalt DESC) as rn
                FROM pop_with_h3 p
                JOIN target_h3 t ON p.h3_cell = t.h3_cell
            )
            SELECT objectid, rutid_scb, rutstorl, beftotalt, kvinna, man, referenstid, sp_geometry
            FROM ranked
            WHERE rn <= {cells_per_h3}
        ) TO '{output_gpkg}' WITH (
            FORMAT GDAL,
            DRIVER 'GPKG',
            LAYER_CREATION_OPTIONS 'GEOMETRY_NAME=sp_geometry'
        )
    """)

    # Verify result
    count = conn.execute(f"SELECT COUNT(*) FROM st_read('{output_gpkg}')").fetchone()[0]
    total_pop = conn.execute(
        f"SELECT SUM(beftotalt) FROM st_read('{output_gpkg}')"
    ).fetchone()[0]
    size_kb = output_gpkg.stat().st_size / 1024

    print(f"Created: {output_gpkg}")
    print(f"  Size: {size_kb:.1f} KB")
    print(f"  Cells: {count}")
    print(f"  Population: {total_pop:,}")

    conn.close()


def main() -> None:
    """Create the test population fixture."""
    production_gpkg = Path("data/population_1km_2024.gpkg")
    events_fixture = Path("tests/fixtures/data/events.parquet")
    output_gpkg = Path("tests/fixtures/data/population_test.gpkg")

    create_population_fixture(production_gpkg, events_fixture, output_gpkg)


if __name__ == "__main__":
    main()

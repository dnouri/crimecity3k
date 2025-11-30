#!/usr/bin/env python3
"""Spike: Test H3 aggregation with fixture data to understand output structure."""

import duckdb
from pathlib import Path
from qck import qck  # type: ignore[import-untyped]

# Paths
fixture_path = Path("tests/fixtures/events_2024_01_15-22.parquet")
sql_path = Path("crimecity3k/sql/h3_aggregation.sql")
output_path = Path("/tmp/spike_h3_aggregation_test.parquet")

# We need population data - let's create a minimal synthetic one for testing
synthetic_pop_path = Path("/tmp/spike_synthetic_population.parquet")

conn = duckdb.connect(":memory:")
conn.execute("INSTALL h3 FROM community; LOAD h3")
conn.execute("INSTALL spatial; LOAD spatial")

# Create synthetic population for Sweden's geographic bounds
# This is just for testing - real population data would come from SCB
print("Creating synthetic population data...")
conn.execute(f"""
    COPY (
        WITH h3_cells AS (
            -- Generate H3 cells covering Sweden's bounds (approximate)
            SELECT DISTINCT h3_latlng_to_cell_string(latitude, longitude, 5) as h3_cell
            FROM '{fixture_path}'
        )
        SELECT
            h3_cell,
            1000.0 as population  -- Synthetic: 1000 people per cell
        FROM h3_cells
    ) TO '{synthetic_pop_path}' (FORMAT PARQUET)
""")

print(f"Synthetic population created: {synthetic_pop_path}")

# Check synthetic population
pop_count = conn.execute(f"SELECT COUNT(*) FROM '{synthetic_pop_path}'").fetchone()[0]
print(f"  H3 cells with population: {pop_count}")

# Now run the aggregation
print("\n═══ RUNNING H3 AGGREGATION ═══")

params = {
    "events_file": str(fixture_path),
    "population_file": str(synthetic_pop_path),
    "output_file": str(output_path),
    "resolution": 5,
    "min_population": 100,
}

qck(str(sql_path), params=params, connection=conn)

print(f"\nAggregation complete: {output_path}")

# Inspect output
print("\n═══ OUTPUT SCHEMA ═══")
schema = conn.execute(f"DESCRIBE '{output_path}'").fetchall()
for col in schema:
    print(f"  {col[0]:20s} {col[1]}")

print("\n═══ OUTPUT STATISTICS ═══")
stats = conn.execute(f"""
    SELECT
        COUNT(*) as cell_count,
        SUM(total_count) as total_events,
        SUM(traffic_count) as traffic,
        SUM(property_count) as property,
        SUM(violence_count) as violence,
        SUM(narcotics_count) as narcotics,
        SUM(fraud_count) as fraud,
        SUM(public_order_count) as public_order,
        SUM(weapons_count) as weapons,
        SUM(other_count) as other
    FROM '{output_path}'
""").fetchone()

print(f"  Total H3 cells: {stats[0]}")
print(f"  Total events: {stats[1]}")
print(f"\n  Category breakdown:")
print(f"    Traffic:       {stats[2]}")
print(f"    Property:      {stats[3]}")
print(f"    Violence:      {stats[4]}")
print(f"    Narcotics:     {stats[5]}")
print(f"    Fraud:         {stats[6]}")
print(f"    Public order:  {stats[7]}")
print(f"    Weapons:       {stats[8]}")
print(f"    Other:         {stats[9]}")

# Verify category counts sum to total
category_sum = sum(stats[2:10])
print(f"\n  Sum of categories: {category_sum}")
print(f"  Matches total? {category_sum == stats[1]}")

# Inspect type_counts structure
print("\n═══ TYPE_COUNTS STRUCTURE ═══")
sample = conn.execute(f"""
    SELECT h3_cell, total_count, type_counts
    FROM '{output_path}'
    ORDER BY total_count DESC
    LIMIT 1
""").fetchone()

print(f"  Sample cell: {sample[0]}")
print(f"  Total count: {sample[1]}")
print(f"  Type counts structure: {type(sample[2])}")
print(f"  Type counts content:")

# type_counts is a list of structs - let's inspect
type_counts_df = conn.execute(f"""
    SELECT UNNEST(type_counts, recursive := true)
    FROM '{output_path}'
    WHERE total_count = {sample[1]}
    LIMIT 5
""").fetchdf()
print(type_counts_df)

# Check for cells with specific categories
print("\n═══ CELLS WITH TRAFFIC EVENTS ═══")
traffic_cells = conn.execute(f"""
    SELECT h3_cell, traffic_count, total_count
    FROM '{output_path}'
    WHERE traffic_count > 0
    ORDER BY traffic_count DESC
    LIMIT 3
""").fetchall()

for cell, traffic, total in traffic_cells:
    print(f"  {cell}: {traffic}/{total} events")

# Check rate calculation
print("\n═══ RATE CALCULATION SAMPLE ═══")
rate_sample = conn.execute(f"""
    SELECT h3_cell, total_count, population, rate_per_10000
    FROM '{output_path}'
    WHERE population > 0
    ORDER BY rate_per_10000 DESC
    LIMIT 3
""").fetchall()

for cell, count, pop, rate in rate_sample:
    expected_rate = (float(count) / float(pop)) * 10000
    print(f"  Cell: {cell}")
    print(f"    Events: {count}, Population: {pop}")
    print(f"    Calculated rate: {rate:.4f}")
    print(f"    Expected rate: {expected_rate:.4f}")
    print(f"    Match? {abs(rate - expected_rate) < 0.001}")

conn.close()

print("\n✓ Spike complete!")

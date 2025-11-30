#!/usr/bin/env python3
"""Spike: Explore test fixture data to understand structure and event types."""

import duckdb
from pathlib import Path

fixture_path = Path("tests/fixtures/events_2024_01_15-22.parquet")

conn = duckdb.connect(":memory:")
conn.execute("INSTALL h3 FROM community; LOAD h3")

# Load fixture
conn.execute(f"CREATE TABLE events AS SELECT * FROM '{fixture_path}'")

# Basic stats
print("═══ FIXTURE OVERVIEW ═══")
result = conn.execute("SELECT COUNT(*) as count FROM events").fetchone()
print(f"Total events: {result[0]}")

# Schema
print("\n═══ SCHEMA ═══")
schema = conn.execute("DESCRIBE events").fetchall()
for col in schema:
    print(f"  {col[0]:20s} {col[1]}")

# Sample row
print("\n═══ SAMPLE ROW ═══")
sample = conn.execute("SELECT * FROM events LIMIT 1").fetchdf()
print(sample.T)

# Event types distribution
print("\n═══ EVENT TYPES DISTRIBUTION ═══")
types = conn.execute("""
    SELECT type, COUNT(*) as count
    FROM events
    GROUP BY type
    ORDER BY count DESC
""").fetchall()

for event_type, count in types:
    print(f"  {count:3d}  {event_type}")

print(f"\nTotal distinct types: {len(types)}")

# Category simulation (based on our CASE statement)
print("\n═══ CATEGORY DISTRIBUTION (simulated) ═══")
categories = conn.execute("""
    SELECT
        CASE
            WHEN type IN (
                'Trafikolycka, personskada', 'Trafikolycka, smitning',
                'Trafikolycka, singel', 'Trafikolycka, övrigt',
                'Trafikbrott, övriga', 'Rattfylleri', 'Olovlig körning'
            ) THEN 'traffic'
            WHEN type IN (
                'Stöld', 'Stöld/inbrott', 'Tillgrepp, stöld', 'Inbrott',
                'Skadegörelse', 'Rån', 'Rån, övrigt', 'Rån väpnat'
            ) THEN 'property'
            WHEN type IN (
                'Misshandel', 'Misshandel, grov', 'Våld/hot mot tjänsteman',
                'Våldtäkt', 'Våldtäkt, försök', 'Mord/dråp, försök', 'Mord/dråp'
            ) THEN 'violence'
            WHEN type = 'Narkotikabrott' THEN 'narcotics'
            WHEN type IN ('Bedrägeri', 'Bedrägeri, ocker') THEN 'fraud'
            WHEN type IN (
                'Ordningslagen', 'Fylleri', 'Ofredande/förargelse', 'Brand',
                'Alkohollagen', 'Övriga brott mot person'
            ) THEN 'public_order'
            WHEN type = 'Vapenlagen' THEN 'weapons'
            ELSE 'other'
        END as category,
        COUNT(*) as count
    FROM events
    GROUP BY category
    ORDER BY count DESC
""").fetchall()

for category, count in categories:
    print(f"  {count:3d}  {category}")

# Geographic coverage
print("\n═══ GEOGRAPHIC BOUNDS ═══")
bounds = conn.execute("""
    SELECT
        MIN(latitude) as min_lat,
        MAX(latitude) as max_lat,
        MIN(longitude) as min_lon,
        MAX(longitude) as max_lon
    FROM events
""").fetchone()

print(f"  Latitude:  {bounds[0]:.4f} to {bounds[1]:.4f}")
print(f"  Longitude: {bounds[2]:.4f} to {bounds[3]:.4f}")

# Unique locations
print("\n═══ LOCATION DIVERSITY ═══")
locations = conn.execute("""
    SELECT COUNT(DISTINCT location_name) as unique_locations
    FROM events
""").fetchone()
print(f"  Unique locations: {locations[0]}")

# Top locations
top_locations = conn.execute("""
    SELECT location_name, COUNT(*) as count
    FROM events
    GROUP BY location_name
    ORDER BY count DESC
    LIMIT 5
""").fetchall()

print("\n  Top 5 locations:")
for loc, count in top_locations:
    print(f"    {count:3d}  {loc}")

conn.close()

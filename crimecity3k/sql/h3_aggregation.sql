-- Event aggregation to H3 cells with category-based filtering
--
-- Aggregates police events to H3 hexagonal cells with pre-computed category counts
-- and sparse type-level details for client-side filtering. Implements variant 3B
-- architecture: 8 category columns + sparse type_counts JSON array.
--
-- Parameters:
--   {{events_file}}      : Path to events Parquet file
--   {{population_file}}  : Path to population H3 Parquet (from population_to_h3.sql)
--   {{output_file}}      : Path for output Parquet file (will be created)
--   {{resolution}}       : H3 resolution (4=~25km, 5=~8km, 6=~3km edge length)
--   {{min_population}}   : Minimum population threshold for rate calculation (default: 100)
--
-- Algorithm:
--   1. Map events to H3 cells and assign semantic categories
--   2. Count events per (cell, type) pair for sparse type_counts
--   3. Aggregate type counts into 8 category counts per cell
--   4. Join with population data for normalized rate calculation
--   5. Filter cells with zero population below threshold
--
-- Output schema:
--   h3_cell           : VARCHAR  (H3 cell ID, e.g., '85283473fffffff')
--   total_count       : INTEGER  (total events in cell)
--   traffic_count     : INTEGER  (traffic-related events)
--   property_count    : INTEGER  (property crime events)
--   violence_count    : INTEGER  (violence-related events)
--   narcotics_count   : INTEGER  (narcotics events)
--   fraud_count       : INTEGER  (fraud events)
--   public_order_count: INTEGER  (public order events)
--   weapons_count     : INTEGER  (weapons-related events)
--   other_count       : INTEGER  (uncategorized events)
--   type_counts       : STRUCT[] (sparse array: [{type: VARCHAR, count: BIGINT}, ...])
--   dominant_location : VARCHAR  (most common location_name in cell)
--   population        : DOUBLE   (population in cell)
--   rate_per_10000    : DOUBLE   (events per 10,000 residents)
--
-- Dependencies: DuckDB H3 community extension
--
-- Category definitions (52 event types → 8 semantic categories):
--   traffic       : 7 types  (accidents, traffic violations, drunk driving)
--   property      : 8 types  (theft, burglary, robbery, vandalism)
--   violence      : 7 types  (assault, rape, murder, threats)
--   narcotics     : 1 type   (drug offenses)
--   fraud         : 2 types  (fraud, usury)
--   public_order  : 6 types  (public order act, drunkenness, disturbance)
--   weapons       : 1 type   (weapons law violations)
--   other         : 20 types (all remaining event types)
--
-- Categories are hardcoded in the CASE statement below (lines 46-104).
-- New event types default to 'other' category via ELSE clause.

COPY (
    WITH events_h3 AS (
        -- Map events to H3 cells and assign semantic categories
        -- Category mapping based on category_mapping.toml
        -- Excludes editorial "Sammanfattning" (summary) reports which are
        -- meta-content, not actual crime events
        SELECT
            h3_latlng_to_cell_string(latitude, longitude, {{ resolution }}) AS h3_cell,
            type,
            location_name,
            CASE
                -- Traffic (Trafik): 7 types
                WHEN type IN (
                    'Trafikolycka, personskada',
                    'Trafikolycka, smitning',
                    'Trafikolycka, singel',
                    'Trafikolycka, övrigt',
                    'Trafikbrott, övriga',
                    'Rattfylleri',
                    'Olovlig körning'
                ) THEN 'traffic'

                -- Property crimes (Egendomsbrott): 8 types
                WHEN type IN (
                    'Stöld',
                    'Stöld/inbrott',
                    'Tillgrepp, stöld',
                    'Inbrott',
                    'Skadegörelse',
                    'Rån',
                    'Rån, övrigt',
                    'Rån väpnat'
                ) THEN 'property'

                -- Violence (Våld): 7 types
                WHEN type IN (
                    'Misshandel',
                    'Misshandel, grov',
                    'Våld/hot mot tjänsteman',
                    'Våldtäkt',
                    'Våldtäkt, försök',
                    'Mord/dråp, försök',
                    'Mord/dråp'
                ) THEN 'violence'

                -- Narcotics (Narkotika): 1 type
                WHEN type = 'Narkotikabrott' THEN 'narcotics'

                -- Fraud (Bedrägeri): 2 types
                WHEN type IN (
                    'Bedrägeri',
                    'Bedrägeri, ocker'
                ) THEN 'fraud'

                -- Public order (Ordningsstörning): 6 types
                WHEN type IN (
                    'Ordningslagen',
                    'Fylleri',
                    'Ofredande/förargelse',
                    'Brand',
                    'Alkohollagen',
                    'Övriga brott mot person'
                ) THEN 'public_order'

                -- Weapons (Vapen): 1 type
                WHEN type = 'Vapenlagen' THEN 'weapons'

                -- Other (Övrigt): 20 types (all remaining)
                ELSE 'other'
            END AS category
        FROM '{{ events_file }}'
        WHERE type NOT LIKE 'Sammanfattning%'
    ),

    type_counts AS (
        -- Count events per (cell, type) combination
        -- One row per unique (h3_cell, type) pair with count
        -- Preserves category for later aggregation
        SELECT
            h3_cell,
            type,
            category,
            COUNT(*) AS type_count
        FROM events_h3
        GROUP BY h3_cell, type, category
    ),

    events_aggregated AS (
        -- Aggregate type counts into category counts and collect sparse type_counts
        -- Each cell gets one row with 8 category integers + type_counts array
        SELECT
            h3_cell,
            CAST(SUM(type_count) AS INTEGER) AS total_count,

            -- Category counts (8 pre-computed integers, explicitly cast for correctness)
            CAST(SUM(CASE WHEN category = 'traffic' THEN type_count ELSE 0 END) AS INTEGER) AS traffic_count,
            CAST(SUM(CASE WHEN category = 'property' THEN type_count ELSE 0 END) AS INTEGER) AS property_count,
            CAST(SUM(CASE WHEN category = 'violence' THEN type_count ELSE 0 END) AS INTEGER) AS violence_count,
            CAST(SUM(CASE WHEN category = 'narcotics' THEN type_count ELSE 0 END) AS INTEGER) AS narcotics_count,
            CAST(SUM(CASE WHEN category = 'fraud' THEN type_count ELSE 0 END) AS INTEGER) AS fraud_count,
            CAST(SUM(CASE WHEN category = 'public_order' THEN type_count ELSE 0 END) AS INTEGER) AS public_order_count,
            CAST(SUM(CASE WHEN category = 'weapons' THEN type_count ELSE 0 END) AS INTEGER) AS weapons_count,
            CAST(SUM(CASE WHEN category = 'other' THEN type_count ELSE 0 END) AS INTEGER) AS other_count,

            -- Sparse type_counts: only types present in this cell, sorted by count descending
            LIST(
                STRUCT_PACK(type := type, count := type_count)
                ORDER BY type_count DESC
            ) AS type_counts
        FROM type_counts
        GROUP BY h3_cell
    ),

    location_by_cell AS (
        -- Compute dominant (most common) location_name per cell
        -- Uses mode() aggregate to find the most frequent value
        SELECT
            h3_cell,
            mode(location_name) AS dominant_location
        FROM events_h3
        GROUP BY h3_cell
    ),

    population AS (
        -- Load population data for this resolution
        SELECT
            h3_cell,
            population
        FROM '{{ population_file }}'
    ),

    merged AS (
        -- Join events with population and location, calculate normalized rates
        SELECT
            e.h3_cell,
            e.total_count,
            e.traffic_count,
            e.property_count,
            e.violence_count,
            e.narcotics_count,
            e.fraud_count,
            e.public_order_count,
            e.weapons_count,
            e.other_count,
            e.type_counts,
            l.dominant_location,
            COALESCE(p.population, 0.0) AS population,

            -- Calculate normalized rate (events per 10,000 residents)
            -- Only calculate for cells meeting minimum population threshold
            CASE
                WHEN COALESCE(p.population, 0) >= {{ min_population }}
                THEN (e.total_count::DOUBLE / p.population) * 10000.0
                ELSE 0.0
            END AS rate_per_10000
        FROM events_aggregated e
        LEFT JOIN location_by_cell l ON e.h3_cell = l.h3_cell
        LEFT JOIN population p ON e.h3_cell = p.h3_cell
    )

    -- Final output: sorted by total event count descending
    SELECT
        h3_cell,
        total_count,
        traffic_count,
        property_count,
        violence_count,
        narcotics_count,
        fraud_count,
        public_order_count,
        weapons_count,
        other_count,
        type_counts,
        dominant_location,
        population,
        rate_per_10000
    FROM merged
    ORDER BY total_count DESC

) TO '{{ output_file }}' (FORMAT PARQUET, COMPRESSION ZSTD);

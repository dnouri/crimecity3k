-- Event aggregation to municipalities with category-based filtering
--
-- Aggregates police events to Swedish municipalities with pre-computed category
-- counts and sparse type-level details for client-side filtering. Uses the same
-- 8-category structure as H3 aggregation for frontend compatibility.
--
-- Key differences from H3 aggregation:
--   - JOIN by location_name (case-insensitive) instead of h3_latlng_to_cell()
--   - LEFT JOIN from municipalities ensures all 290 appear (even with 0 events)
--   - Uses official SCB population data instead of H3 population grid
--   - Excludes county-level events (location_name LIKE '% län')
--
-- Parameters:
--   {{events_file}}      : Path to events Parquet file
--   {{population_file}}  : Path to municipality population CSV
--   {{output_file}}      : Path for output Parquet file (will be created)
--
-- Output schema:
--   kommun_kod        : VARCHAR  (4-digit municipality code like "0114")
--   kommun_namn       : VARCHAR  (municipality name like "Upplands Väsby")
--   total_count       : INTEGER  (total events in municipality)
--   traffic_count     : INTEGER  (traffic-related events)
--   property_count    : INTEGER  (property crime events)
--   violence_count    : INTEGER  (violence-related events)
--   narcotics_count   : INTEGER  (narcotics events)
--   fraud_count       : INTEGER  (fraud events)
--   public_order_count: INTEGER  (public order events)
--   weapons_count     : INTEGER  (weapons-related events)
--   other_count       : INTEGER  (uncategorized events)
--   type_counts       : STRUCT[] (sparse array: [{type: VARCHAR, count: BIGINT}, ...])
--   population        : INTEGER  (official SCB population)
--   rate_per_10000    : DOUBLE   (events per 10,000 population)
--
-- Category definitions (same 52 types → 8 categories as H3):
--   traffic       : 7 types  (accidents, traffic violations, drunk driving)
--   property      : 8 types  (theft, burglary, robbery, vandalism)
--   violence      : 7 types  (assault, rape, murder, threats)
--   narcotics     : 1 type   (drug offenses)
--   fraud         : 2 types  (fraud, usury)
--   public_order  : 6 types  (public order act, drunkenness, disturbance)
--   weapons       : 1 type   (weapons law violations)
--   other         : 20 types (all remaining event types)

COPY (
    WITH municipalities AS (
        -- Load all 290 municipalities with population
        SELECT
            kommun_kod,
            kommun_namn,
            population
        FROM '{{ population_file }}'
    ),

    events_categorized AS (
        -- Assign semantic categories to events
        -- Exclude county-level events (ending in " län") and summary reports
        SELECT
            LOWER(location_name) AS location_name_lower,
            type,
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

                -- Other (Övrigt): all remaining event types
                ELSE 'other'
            END AS category
        FROM '{{ events_file }}'
        WHERE type NOT LIKE 'Sammanfattning%'
          AND location_name NOT LIKE '% län'
    ),

    type_counts AS (
        -- Count events per (municipality, type) combination
        SELECT
            location_name_lower,
            type,
            category,
            COUNT(*) AS type_count
        FROM events_categorized
        GROUP BY location_name_lower, type, category
    ),

    events_aggregated AS (
        -- Aggregate type counts into category counts per municipality
        SELECT
            location_name_lower,
            CAST(SUM(type_count) AS INTEGER) AS total_count,

            -- Category counts (8 pre-computed integers)
            CAST(SUM(CASE WHEN category = 'traffic' THEN type_count ELSE 0 END) AS INTEGER) AS traffic_count,
            CAST(SUM(CASE WHEN category = 'property' THEN type_count ELSE 0 END) AS INTEGER) AS property_count,
            CAST(SUM(CASE WHEN category = 'violence' THEN type_count ELSE 0 END) AS INTEGER) AS violence_count,
            CAST(SUM(CASE WHEN category = 'narcotics' THEN type_count ELSE 0 END) AS INTEGER) AS narcotics_count,
            CAST(SUM(CASE WHEN category = 'fraud' THEN type_count ELSE 0 END) AS INTEGER) AS fraud_count,
            CAST(SUM(CASE WHEN category = 'public_order' THEN type_count ELSE 0 END) AS INTEGER) AS public_order_count,
            CAST(SUM(CASE WHEN category = 'weapons' THEN type_count ELSE 0 END) AS INTEGER) AS weapons_count,
            CAST(SUM(CASE WHEN category = 'other' THEN type_count ELSE 0 END) AS INTEGER) AS other_count,

            -- Sparse type_counts: only types present, sorted by count descending
            LIST(
                STRUCT_PACK(type := type, count := type_count)
                ORDER BY type_count DESC
            ) AS type_counts
        FROM type_counts
        GROUP BY location_name_lower
    ),

    merged AS (
        -- LEFT JOIN from municipalities ensures all 290 appear
        -- Case-insensitive join via LOWER(kommun_namn)
        SELECT
            m.kommun_kod,
            m.kommun_namn,
            COALESCE(e.total_count, 0) AS total_count,
            COALESCE(e.traffic_count, 0) AS traffic_count,
            COALESCE(e.property_count, 0) AS property_count,
            COALESCE(e.violence_count, 0) AS violence_count,
            COALESCE(e.narcotics_count, 0) AS narcotics_count,
            COALESCE(e.fraud_count, 0) AS fraud_count,
            COALESCE(e.public_order_count, 0) AS public_order_count,
            COALESCE(e.weapons_count, 0) AS weapons_count,
            COALESCE(e.other_count, 0) AS other_count,
            COALESCE(e.type_counts, []) AS type_counts,
            m.population
        FROM municipalities m
        LEFT JOIN events_aggregated e ON LOWER(m.kommun_namn) = e.location_name_lower
    )

    -- Final output: sorted by total event count descending
    SELECT
        kommun_kod,
        kommun_namn,
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
        population,
        (CAST(total_count AS DOUBLE) / population) * 10000 AS rate_per_10000
    FROM merged
    ORDER BY total_count DESC

) TO '{{ output_file }}' (FORMAT PARQUET, COMPRESSION ZSTD);

-- Population grid to H3 hexagonal cells aggregation
--
-- Transforms SCB's 1km² population grid into H3 hexagonal cells at specified
-- resolution. This conversion enables consistent spatial aggregation with crime
-- event data and facilitates multi-resolution analysis.
--
-- Parameters:
--   {{input_file}}  : Path to SCB population GeoPackage (1km grid, SWEREF99 TM)
--   {{output_file}} : Path for output Parquet file (will be created)
--   {{resolution}}  : H3 resolution (4=~25km, 5=~8km, 6=~3km edge length)
--
-- Algorithm:
--   1. Extract centroids from 1km grid polygons
--   2. Convert WGS84 lat/lon coordinates to H3 cell IDs
--   3. Aggregate population statistics by H3 cell
--   4. Filter zero-population cells to reduce output size
--
-- Output schema:
--   h3_cell    : VARCHAR (H3 cell ID, e.g., '85283473fffffff')
--   population : BIGINT  (total population in cell)
--   female     : BIGINT  (female population in cell)
--   male       : BIGINT  (male population in cell)
--
-- Dependencies: DuckDB spatial extension, H3 community extension

COPY (
    WITH grid_centroids AS (
        -- Convert 1km grid polygons to point centroids for H3 mapping
        -- SCB grid uses SWEREF99 TM (EPSG:3006); transform to WGS84 (EPSG:4326) lat/lon
        -- always_xy=true ensures [longitude, latitude] order for WGS84
        SELECT
            ST_Y(ST_Transform(ST_Centroid(sp_geometry), 'EPSG:3006', 'EPSG:4326', true)) AS latitude,
            ST_X(ST_Transform(ST_Centroid(sp_geometry), 'EPSG:3006', 'EPSG:4326', true)) AS longitude,
            beftotalt AS population,
            kvinna AS female,
            man AS male
        FROM '{{ input_file }}'
        WHERE beftotalt > 0  -- Skip unpopulated cells to reduce processing
    ),

    h3_mapped AS (
        -- Map each grid centroid to its containing H3 cell
        -- Multiple 1km cells may map to the same H3 cell (aggregated next)
        SELECT
            h3_latlng_to_cell_string(latitude, longitude, {{ resolution }}) AS h3_cell,
            population,
            female,
            male
        FROM grid_centroids
    )

    -- Aggregate population by H3 cell
    -- Sum across all 1km grid cells that fall within each hexagon
    SELECT
        h3_cell,
        SUM(population) AS population,
        SUM(female) AS female,
        SUM(male) AS male
    FROM h3_mapped
    GROUP BY h3_cell
    HAVING SUM(population) > 0  -- Final filter to ensure no zero-population cells

) TO '{{ output_file }}' (FORMAT PARQUET, COMPRESSION ZSTD);

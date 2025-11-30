-- H3 to GeoJSONL Export Pipeline
-- Outputs newline-delimited GeoJSON features (one per line) for web visualization
--
-- Parameters:
--   {{events_table}}: Name of table/view with H3 aggregated crime data
--   {{output_file}}: Path to write the GeoJSONL output file
--
-- Note: H3 and spatial extensions must be loaded on the connection
--
-- Output format: Compressed (.gz) newline-delimited GeoJSON
-- Each line is a complete GeoJSON Feature with:
--   - geometry: H3 hexagon polygon
--   - properties: all crime statistics columns

COPY (
    WITH features AS (
        SELECT
            json_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(
                    ST_GeomFromText(h3_cell_to_boundary_wkt(h3_cell))
                )::json,
                'properties', json_object(
                    'h3_cell', h3_cell,
                    'total_count', total_count,
                    'traffic_count', traffic_count,
                    'property_count', property_count,
                    'violence_count', violence_count,
                    'narcotics_count', narcotics_count,
                    'fraud_count', fraud_count,
                    'public_order_count', public_order_count,
                    'weapons_count', weapons_count,
                    'other_count', other_count,
                    'type_counts', type_counts,
                    'population', population,
                    'rate_per_10000', rate_per_10000
                )
            ) as feature
        FROM {{ events_table }}
    )
    -- Export each feature as a JSON string on its own line
    SELECT feature::VARCHAR as json_text
    FROM features
) TO '{{ output_file }}'
(FORMAT CSV, HEADER FALSE, QUOTE '', ESCAPE '', DELIMITER E'\n', COMPRESSION 'gzip')

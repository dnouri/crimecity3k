# Municipality-Based Analysis: A Better Approach for Swedish Police Data

**Analysis Date:** 2025-12-14
**Author:** Claude (AI-assisted analysis)

---

## Executive Summary

**Key Finding: Swedish Police API reports locations ONLY at municipality or county level.**

The event data contains exactly **311 unique locations**:
- **21 counties** (län) - regional summaries
- **290 municipalities** (kommuner) - exactly matching Sweden's 290 municipalities

There are **NO sub-municipality locations** (no streets, neighborhoods, or villages). This means **H3 hexagonal cells are the wrong abstraction** for this data.

**Recommendation:** Replace H3 cells with Swedish municipality boundaries for accurate visualization and rate calculations.

---

## Part 1: Data Granularity Verification

### Location Analysis Results

```
Total unique location_name values: 311
Total unique coordinate pairs: 311 (1:1 mapping)
```

Every `location_name` maps to exactly ONE coordinate pair - the centroid of that administrative area.

### Location Types

| Type | Count | Examples |
|------|-------|----------|
| Counties (län) | 21 | Västra Götalands län, Norrbottens län |
| Municipalities (kommun) | 290 | Stockholm, Malmö, Storuman, Kiruna |
| **Sub-municipality** | **0** | None found |

### Verification Queries

No street-level locations found:
- No locations containing "gatan" (street)
- No locations containing "vägen" (road)
- No locations with comma separators (address patterns)

Only 3 multi-word municipality names found:
- "Upplands väsby" (municipality)
- "Östra göinge" (municipality)
- "Lilla edet" (municipality)

**Conclusion: The Swedish Police API provides NO granularity below municipality level.**

---

## Part 2: The Problem with H3

### Current Architecture Issues

1. **False Precision**: H3 R5 cells are ~252 km² but municipalities can be 20,000+ km²
2. **Misaligned Boundaries**: H3 hexagons don't match administrative boundaries
3. **Population Mismatch**: Population calculated for H3 cell, but events from entire municipality
4. **Artificial Hotspots**: Events concentrated at centroids create false crime hotspots

### Concrete Example: Kiruna Municipality

| Metric | Value |
|--------|-------|
| Municipality area | 19,447 km² |
| H3 R5 cell area | 252 km² |
| Ratio | Municipality is **77x larger** than cell |
| Events | 323 total |
| Events from remote villages | Vittangi (90km), Karesuando (180km) |
| Current rate | 509/10k (misleading) |

Events explicitly mentioning remote locations but attributed to Kiruna:
- "Trafikolycka på E45, norr om Vittangi" (90km away)
- "Polisen har insats i trakten av Karesuando" (180km away)
- "Stöld i Vittangi" (90km away)

**These events are placed at Kiruna's centroid, not their actual locations.**

---

## Part 3: Municipality Boundaries Solution

### Data Sources

#### 1. GeoJSON Boundaries (FREE)

**GitHub - okfse/sweden-geojson**
- URL: https://github.com/okfse/sweden-geojson
- File: `swedish_municipalities.geojson`
- Size: ~500KB (compressed from 25MB original)
- License: Free to use

Properties per feature:
```json
{
  "lan_code": "01",
  "kom_namn": "Stockholm",
  "id": "0180",
  "geo_point_2d": [59.3293, 18.0686]
}
```

**Opendatasoft - Kommuner Sweden**
- URL: https://public.opendatasoft.com/explore/dataset/georef-sweden-kommun/
- Source: Lantmäteriet (Swedish mapping authority)
- Formats: GeoJSON, Shapefile, CSV
- License: Open data

#### 2. Population Data (FREE)

**Statistics Sweden (SCB)**
- URL: https://www.scb.se/en/services/open-data-api/open-geodata/
- Table: Population by municipality, 2024
- Direct link: https://www.statistikdatabasen.scb.se/goto/en/ssd/BefArealTathetKon
- Formats: CSV, Excel, API

Population data includes:
- Municipality code (matches `id` in GeoJSON)
- Population by year (1991-2024)
- Land area in km²

---

## Part 4: Proposed New Architecture

### New Data Model

Instead of H3 cells, use municipalities as the geographic unit:

```
MUNICIPALITY AGGREGATION
├── kommun_kod       (VARCHAR) - Municipality code e.g. "0180"
├── kommun_namn      (VARCHAR) - Municipality name e.g. "Stockholm"
├── total_count      (INTEGER) - Total events
├── traffic_count    (INTEGER) - Traffic events
├── property_count   (INTEGER) - Property crime
├── violence_count   (INTEGER) - Violence
├── narcotics_count  (INTEGER) - Drug crimes
├── fraud_count      (INTEGER) - Fraud
├── public_order_count (INTEGER) - Public order
├── weapons_count    (INTEGER) - Weapons
├── other_count      (INTEGER) - Other
├── population       (INTEGER) - Official SCB population
├── area_km2         (DOUBLE)  - Land area
├── rate_per_10000   (DOUBLE)  - Normalized rate
├── density          (DOUBLE)  - Events per km²
└── geometry         (GEOMETRY) - Municipality polygon
```

### Pipeline Changes

#### Current Flow (H3-based)
```
events.parquet
    → h3_latlng_to_cell() → events by H3 cell
    → JOIN population_h3  → add population
    → GeoJSONL           → hexagon polygons
    → PMTiles            → vector tiles
```

#### New Flow (Municipality-based)
```
events.parquet
    → JOIN by location_name → events by municipality
    → JOIN population_csv   → add official population
    → JOIN boundaries.geojson → add geometry
    → GeoJSONL              → municipality polygons
    → PMTiles               → vector tiles
```

### Key Differences

| Aspect | H3 Approach | Municipality Approach |
|--------|-------------|----------------------|
| Geographic unit | 252 km² hexagons | Variable municipality polygons |
| Boundary source | Computed from lat/lon | Official boundaries |
| Population source | SCB 1km grid → H3 | Official SCB by municipality |
| Events join | By computed H3 cell | By `location_name` |
| Rate accuracy | Poor (mismatch) | Accurate (data matches) |
| Zoom levels | Multiple resolutions | Single layer |
| Visual style | Hexagonal grid | Irregular polygons |

---

## Part 5: Implementation Plan

### Phase 1: Data Preparation (1-2 hours)

1. **Download municipality GeoJSON**
   ```bash
   curl -o data/swedish_municipalities.geojson \
     https://raw.githubusercontent.com/okfse/sweden-geojson/master/swedish_municipalities.geojson
   ```

2. **Download population data**
   - From SCB Statistical Database
   - Export as CSV with columns: kommun_kod, kommun_namn, population

3. **Create lookup table** for location_name → kommun_kod mapping
   - Handle name variations (Upplands-Väsby vs "Upplands väsby")

### Phase 2: Pipeline Modification (4-6 hours)

#### New SQL: municipality_aggregation.sql

```sql
COPY (
    WITH events_by_municipality AS (
        SELECT
            location_name AS kommun_namn,
            type,
            CASE ... END AS category  -- same category mapping
        FROM '{{ events_file }}'
        WHERE type NOT LIKE 'Sammanfattning%'
          AND location_name NOT LIKE '% län'  -- exclude county-level
    ),

    aggregated AS (
        SELECT
            kommun_namn,
            COUNT(*) AS total_count,
            SUM(CASE WHEN category = 'traffic' THEN 1 ELSE 0 END) AS traffic_count,
            -- ... other categories
        FROM events_by_municipality
        GROUP BY kommun_namn
    ),

    with_population AS (
        SELECT
            a.*,
            p.kommun_kod,
            p.population,
            p.area_km2,
            (a.total_count::DOUBLE / p.population) * 10000 AS rate_per_10000
        FROM aggregated a
        JOIN '{{ population_file }}' p ON a.kommun_namn = p.kommun_namn
    ),

    with_geometry AS (
        SELECT
            w.*,
            ST_GeomFromGeoJSON(g.geometry) AS geom
        FROM with_population w
        JOIN '{{ geojson_file }}' g ON w.kommun_kod = g.id
    )

    SELECT * FROM with_geometry
) TO '{{ output_file }}' (FORMAT PARQUET);
```

#### Modified Files

| File | Change |
|------|--------|
| `Makefile` | Add municipality pipeline targets |
| `crimecity3k/h3_processing.py` | Add `aggregate_events_to_municipalities()` |
| `crimecity3k/sql/municipality_aggregation.sql` | New SQL template |
| `crimecity3k/tile_generation.py` | Handle municipality polygons |
| `crimecity3k/pmtiles.py` | Adjust tippecanoe parameters |

### Phase 3: UI Updates (2-4 hours)

#### Frontend Changes

| Component | Change |
|-----------|--------|
| Map layer | Change from fill-extrusion hexagons to fill polygons |
| Hover info | Update property names |
| Legend | Simplify (single resolution) |
| Zoom behavior | Remove resolution switching |
| Cell details panel | Rename to "Municipality details" |
| Drill-down drawer | Works same way (events by location_name) |

#### app.js Changes

```javascript
// Remove H3-specific configuration
const CONFIG = {
    // No more zoomToResolution mapping
    // No more resolutions array

    // Single tile source
    tilesPath: '/data/tiles/pmtiles/municipalities.pmtiles',

    // Color scale remains similar
    // ...
};

// Simplify layer setup - no resolution switching needed
function setupLayers() {
    map.addSource('municipalities', {
        type: 'vector',
        url: `pmtiles://${CONFIG.tilesPath}`
    });

    map.addLayer({
        id: 'municipality-fill',
        type: 'fill',
        source: 'municipalities',
        'source-layer': 'municipalities',
        paint: {
            'fill-color': getColorExpression(),
            'fill-opacity': 0.7,
            'fill-outline-color': '#333'
        }
    });
}
```

### Phase 4: Testing (2-3 hours)

1. **Data validation**
   - Verify all 290 municipalities have events
   - Check population joins correctly
   - Validate rate calculations

2. **Visual testing**
   - Verify municipality boundaries render correctly
   - Check hover/click interactions
   - Test legend and color scales

3. **Update E2E tests**
   - Change layer name references
   - Update expected property names
   - Adjust zoom behavior tests

---

## Part 6: What About Counties?

### County-Level Events

Currently 21 county locations have 17,637 events (25.8% of total). These should be handled separately:

#### Option A: Exclude from municipalities, show separately
- Remove county events from municipality aggregation
- Add a separate "County-level events" indicator
- UI shows: "This view excludes 17,637 county-level events"

#### Option B: Distribute to municipalities (weighted)
- Distribute county events to municipalities within that county
- Weight by population or existing event count
- Adds complexity, may not be accurate

#### Option C: Show county layer at low zoom
- At zoom 3-5: Show county polygons with county events
- At zoom 6+: Show municipality polygons (excluding county events)
- Similar to current R4/R5 resolution switching

**Recommendation: Option A** - Most honest representation. County events are regional summaries, not specific incidents.

---

## Part 7: Impact Assessment

### Benefits

1. **Accuracy**: Rate calculations use correct population denominators
2. **Clarity**: Boundaries match data attribution
3. **Simplicity**: No resolution switching, single geographic unit
4. **Performance**: Fewer polygons (290 vs 1000+ H3 cells)
5. **Correctness**: No artificial hotspots at centroids

### Tradeoffs

1. **Variable granularity**: Rural municipalities are huge (Kiruna: 19,447 km²), urban are small
2. **Visual change**: Users accustomed to hexagons will see irregular shapes
3. **Less "modern" look**: H3 hexagons have visual appeal
4. **Development time**: Requires pipeline rewrite

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Name matching failures | Create comprehensive lookup table |
| Missing municipalities | Validate all 290 present in output |
| Population data quality | Use official SCB data |
| Visual regression | Implement alongside H3, A/B test |

---

## Part 8: Pair Programming Discussion

**Me:** We've discovered the Swedish Police data only has municipality-level precision. H3 cells are creating artificial hotspots.

**Tim:** "Simple is better than complex." If the data is at municipality level, the visualization should be at municipality level. Trying to fit municipality data into H3 cells is adding complexity that doesn't serve accuracy.

**Kent:** What's the test that would prove our approach is correct? If we switch to municipalities, every event should be in exactly one polygon that matches its `location_name`. No more events in the wrong cell.

**Me:** Right. Currently, events from Vittangi (90km from Kiruna center) are in a Kiruna H3 cell. With municipalities, they'd correctly show in Kiruna municipality polygon.

**Tim:** "Explicit is better than implicit." The current H3 approach implicitly claims sub-municipality precision we don't have. Municipal boundaries make the actual data granularity explicit.

**Kent:** The simplest fix is the right fix. We have municipality data, we should show municipality boundaries. The H3 approach was premature optimization based on an incorrect assumption about data precision.

**Me:** What about the county-level events?

**Tim:** "Errors should never pass silently." County events are fundamentally different - they're regional summaries. Don't mix them with municipal incident data. Make the distinction explicit.

**Kent:** Show a separate indicator: "17,637 events at county level not shown on map." Honest, simple, testable.

---

## Appendix: Data Sources

### Municipality Boundaries

| Source | URL | License |
|--------|-----|---------|
| okfse/sweden-geojson | https://github.com/okfse/sweden-geojson | Free to use |
| Opendatasoft | https://public.opendatasoft.com/explore/dataset/georef-sweden-kommun/ | Open |
| Lantmäteriet (original) | via Opendatasoft | Public data |

### Population Data

| Source | URL | Coverage |
|--------|-----|----------|
| SCB Statistical Database | https://www.statistikdatabasen.scb.se/ | All 290 municipalities |
| SCB Open Geodata | https://www.scb.se/en/services/open-data-api/open-geodata/ | API access |

### Related Resources

| Resource | URL |
|----------|-----|
| Swedish municipality codes | https://www.scb.se/hitta-statistik/regional-statistik-och-kartor/regionala-indelningar/ |
| stefur/swemaps (GeoParquet) | https://github.com/stefur/swemaps |

---

## Conclusion

The discovery that Swedish Police data is exclusively at municipality level makes the decision clear: **municipality boundaries are the correct geographic unit** for this visualization.

The current H3 approach creates artificial problems:
- False hotspots at centroids
- Incorrect rate calculations
- Misleading granularity

Switching to municipality boundaries will:
- Accurately represent the data's true precision
- Calculate correct crime rates
- Simplify the pipeline and UI
- Be honest with users about data limitations

**Recommended next step:** Implement the municipality-based pipeline alongside the existing H3 pipeline, validate the output, then deprecate H3.

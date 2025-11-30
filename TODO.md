# CrimeCity3K - V1 Implementation TODO

**Project Goal:** Interactive web map visualizing Swedish police events (2022-2025) aggregated to H3 hexagonal cells with population normalization.

**Development Approach:** Test-Driven Development (TDD) with red-green-refactor cycles, SQL-driven pipeline with qck templates, Pydantic config management.

**Test Fixture:** Week of 2024-01-15 to 2024-01-22 (476 events, 51 types, 154 locations) - representative sample from middle of dataset.

**Architecture Pattern:** Follows aviation-anomaly's proven patterns for SQL execution, configuration management, and testing.

---

## Phase 0: Project Foundation & Setup ✅ COMPLETE

**Goal:** Establish project structure, dependencies, test infrastructure, and configuration system.

**Duration:** ~3 hours

**Outcome:** 11 tests passing, CI configured with GitHub Actions, pre-commit hooks installed

**Key Deliverables:**
- [x] Directory structure with `crimecity3k/`, `tests/`, `data/`, `tmp/`
- [x] Dependencies installed via `uv` (duckdb, qck, pydantic, pytest, ruff, mypy)
- [x] Config system with `config.toml` + Pydantic validation
- [x] DuckDB connection management with H3 and spatial extensions
- [x] Test fixture (476 events) in `tests/fixtures/`
- [x] Makefile with `install`, `check`, `test`, `clean` targets
- [x] GitHub Actions CI workflow
- [x] Pre-commit hooks running `make check`

**Key Improvements Made:**
- Distinguished core DuckDB extensions (spatial) from community (h3)
- Added HTML coverage reports
- Excluded `tmp/` from linting (spike scripts allowed)
- Type annotations with Generator for fixtures

---

## Phase 1: Population Data Pipeline ✅ COMPLETE

**Goal:** Download SCB population data, convert to H3 cells, establish SQL-driven pattern.

**Duration:** ~4 hours

**Outcome:** 16 tests passing, 3 population resolutions generated (r4=8KB, r5=24KB, r6=96KB)

**Key Deliverables:**
- [x] SQL template: `crimecity3k/sql/population_to_h3.sql`
  - Converts SCB 1km grid → H3 cells via centroids
  - ST_Transform for SWEREF99 TM → WGS84
  - Uses `h3_latlng_to_cell_string()` for VARCHAR cells
  - Aggregates population by H3 cell, filters zero-population
- [x] Python wrapper: `convert_population_to_h3()` in `h3_processing.py`
  - Executes SQL via qck with Jinja2 params
  - Atomic write pattern (.tmp → rename)
  - Error handling with cleanup
- [x] Makefile pattern rule: `$(H3_DIR)/population_r%.parquet`
  - Downloads SCB data (34MB GeoPackage, cached)
  - Tracks SQL + config as dependencies
  - Generates all resolutions with `make pipeline-population`
- [x] Integration tests with real SCB data
  - Schema validation
  - Population conservation (no data lost)
  - Geographic coverage (Sweden bounds)
  - Error handling (missing files)
  - Atomic write verification

**Key Improvements Made:**
- Fixed SCB schema (beftotalt, kvinna, man, sp_geometry columns)
- Added `always_xy=true` for correct lon/lat ordering
- Pattern rule instead of 3 separate rules

---

## Phase 2: H3 Event Aggregation with Category Filtering ✅ COMPLETE

**Goal:** Aggregate crime events to H3 cells with population normalization and category-based filtering. Implements variant 3B architecture.

**Duration:** ~5 hours

**Outcome:** 24 tests passing, refined through code smell analysis

**Architecture:** Variant 3B - 8 pre-computed category columns + sparse type_counts array
- Static deployment (no API needed)
- Client-side category + type filtering
- Estimated tileset size: ~300KB

**Key Deliverables:**
- [x] SQL template: `crimecity3k/sql/h3_aggregation.sql` (201 lines)
  - 4-CTE pipeline: `events_h3` → `type_counts` → `events_aggregated` → `merged`
  - Hardcoded CASE statement mapping 52 event types → 8 categories
  - 8 category count columns (INTEGER): traffic, property, violence, narcotics, fraud, public_order, weapons, other
  - Sparse `type_counts`: `LIST(STRUCT_PACK(type, count) ORDER BY count DESC)`
  - LEFT JOIN with population (preserves events without population data)
  - Normalized rate calculation: `(total_count / population) * 10000` with min threshold
  - Output schema: h3_cell, 9 count columns (INTEGER), type_counts (STRUCT[]), population (DOUBLE), rate_per_10000 (DOUBLE)

- [x] Python wrapper: `aggregate_events_to_h3()` in `h3_processing.py`
  - Executes h3_aggregation.sql via qck
  - Atomic write pattern
  - Logging with summary stats

- [x] Makefile pattern rule: `$(H3_DIR)/events_r%.parquet`
  - Depends on events, population, SQL, config
  - Builds all resolutions with `make pipeline-h3`
  - Full pipeline: `make pipeline-all` (population + events)

- [x] Integration tests (8 tests total)
  - Schema validation with INTEGER dtype checking (int32 in pandas)
  - **Critical invariant:** Category counts sum to total_count (no data loss/duplication)
  - type_counts structure validation (list of structs, sorted descending)
  - Rate calculation correctness
  - LEFT JOIN behavior: partial population coverage (NEW - validates events without population preserved)
  - Error handling: missing files
  - Atomic write pattern

- [x] Test fixture: `synthetic_population_h3()` in conftest.py
  - Creates minimal population data (1000/cell) for test isolation

**Code Smell Resolutions:**
1. **CategoryMapping (YAGNI):**
   - Deleted `category_mapping.toml` and related classes
   - Removed 3 tests
   - Enhanced SQL comments documenting 52 types → 8 categories inline
   - Single source of truth: SQL CASE statement

2. **INTEGER Types (Explicit over Implicit):**
   - Added `CAST(SUM(...) AS INTEGER)` to all 9 count columns
   - DuckDB INTEGER → pandas int32 (sufficient for event counts, max 2.1B)
   - Test verification with dtype assertions

3. **LEFT JOIN Test Coverage:**
   - Created `test_aggregate_events_handles_partial_population()`
   - Tests realistic scenario: partial population coverage
   - Verifies events preserved, population=0.0, rate=0.0 for cells without data

**Category Definitions (Hardcoded in SQL):**
- Traffic (7 types): accidents, violations, drunk driving
- Property (8 types): theft, burglary, robbery, vandalism
- Violence (7 types): assault, rape, murder, threats
- Narcotics (1 type): drug offenses
- Fraud (2 types): fraud, usury
- Public Order (6 types): public order act, drunkenness, disturbance
- Weapons (1 type): weapons law violations
- Other (20 types): all remaining (defaults via ELSE clause)

**Final State:**
- 24 tests passing (26 original - 3 CategoryMapping + 1 new partial population test)
- 2 commits on `phase-2-h3-aggregation` branch
- Ready for merge to main

---

## Phase 3: GeoJSON Export and PMTiles Generation ✅ COMPLETE

**Goal:** Export H3 aggregations to GeoJSON and generate PMTiles for web consumption.

**Duration:** ~3 hours

**Outcome:** 16 new tests passing (6 GeoJSON + 10 PMTiles), full tile pipeline integrated

**Architecture:**
- Newline-delimited GeoJSON (.geojsonl.gz) with gzip compression
- PMTiles generation via Tippecanoe v2.53.0
- Zoom range mapping: r4→z4-8, r5→z5-9, r6→z6-10

**Key Deliverables:**
- [x] SQL template: `crimecity3k/sql/h3_to_geojson.sql`
  - Converts H3 cells to GeoJSON Features using `json_object()`
  - Geometry: `ST_AsGeoJSON(ST_GeomFromText(h3_cell_to_boundary_wkt()))`
  - All 13 properties: h3_cell, 9 count columns, type_counts, population, rate
  - Output: CSV format hack for newline-delimited JSON with gzip compression

- [x] Python module: `crimecity3k/tile_generation.py`
  - `export_h3_to_geojson(conn, events_table, output_file)`
  - Atomic write pattern with qck SQL execution
  - Logs file size after export

- [x] Python module: `crimecity3k/pmtiles.py`
  - `get_zoom_range_for_resolution(resolution)`: Maps H3 res → zoom levels
  - `build_tippecanoe_command()`: Constructs CLI command with all flags
  - `check_tippecanoe_installed()`: Validates Tippecanoe availability
  - `generate_pmtiles()`: Full wrapper with attribute preservation

- [x] GeoJSON tests (6 tests in `test_tile_generation.py`)
  - Single/multiple cell export
  - Coordinate order verification [lon, lat]
  - type_counts serialization
  - Atomic write pattern
  - Integration test with event fixture

- [x] PMTiles tests (10 tests in `test_pmtiles_generation.py`)
  - Zoom range calculation
  - Command construction with attributes
  - Parallel parsing flag for GeoJSONL
  - Tippecanoe availability check
  - Mocked and integration tests

- [x] Makefile pattern rules
  - `$(GEOJSONL_DIR)/h3_r%.geojsonl.gz`: GeoJSON export
  - `$(PMTILES_DIR)/h3_r%.pmtiles`: PMTiles generation
  - Convenience: `pipeline-geojson`, `pipeline-pmtiles`
  - Updated `pipeline-all` to include full tile generation

**Acceptance Criteria:**
- [x] `make pipeline-all` generates all tiles (population → events → GeoJSON → PMTiles)
- [x] GeoJSON is valid newline-delimited format with gzip compression
- [x] All 16 new tests pass
- [x] Code quality checks pass (ruff, mypy)

---

## Phase 4: FastAPI Backend (Not Started)

**Goal:** Serve PMTiles and provide metadata API.

**Key Components:**
- Static file serving for PMTiles
- Metadata endpoints (resolutions, bounds, stats)
- CORS configuration
- Health check endpoint

---

## Phase 5: Web Frontend (Not Started)

**Goal:** Interactive map with MapLibre GL JS + PMTiles protocol.

**Key Components:**
- MapLibre GL JS with PMTiles plugin
- Layer switching (resolutions, categories)
- Click interactions (popup with stats)
- Legend with category colors
- Responsive design

---

## Phase 6: Deployment (Not Started)

**Goal:** Deploy to static hosting or simple server.

**Options:**
- Static: GitHub Pages, Cloudflare Pages, Netlify
- Server: Railway, Fly.io, DigitalOcean

---

## Phase 7: Documentation & Polish (Not Started)

**Goal:** Complete README, add examples, tag v1.0.0.

**Deliverables:**
- Comprehensive README with screenshots
- Data pipeline documentation
- API documentation
- Deployment guide
- Contributing guidelines

---

## Development Patterns

### SQL-Driven Pipeline
- All transformations in `.sql` files with Jinja2 templates
- Executed via qck with parameter dictionaries
- SQL files tracked as Makefile dependencies (automatic rebuilds)

### Configuration Management
- `config.toml` with Pydantic validation
- Type-safe config access throughout
- Config passed as parameters to SQL templates

### Test-Driven Development
- Write test first (RED)
- Create SQL + Python wrapper (GREEN)
- Add data quality tests (REFACTOR)
- Test behavior, not SQL implementation
- Minimal mocking, real SQL execution

### Atomic Writes
- Write to `.tmp` file first
- Rename on success (atomic operation)
- Clean up temps on error

### Makefile Pattern Rules
- Use `%` wildcards for resolutions
- Track SQL + config as dependencies
- Automatic rebuilds on file changes

---

## Success Criteria

CrimeCity3K v1 is complete when:
- ✅ Phase 0: Foundation (11 tests, CI working)
- ✅ Phase 1: Population pipeline (16 tests, 3 resolutions)
- ✅ Phase 2: Event aggregation (24 tests, category filtering)
- ✅ Phase 3: GeoJSON + PMTiles (16 tests, full tile pipeline)
- ⏳ Phase 4: FastAPI backend
- ⏳ Phase 5: Web frontend
- ⏳ Phase 6: Deployment
- ⏳ Phase 7: Documentation

**Current Progress:** 4/7 phases complete (~55%)

**Estimated Remaining:** 12-15 hours

**Next Step:** Phase 4 - FastAPI Backend

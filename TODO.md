# CrimeCity3K - V1 Implementation TODO

**Project Goal:** Interactive web map visualizing Swedish police events (2022-2025) aggregated to H3 hexagonal cells with population normalization.

**Development Approach:** Test-Driven Development (TDD) with red-green-refactor cycles, SQL-driven pipeline with qck templates, Pydantic config management.

**Test Fixture:** Week of 2024-01-15 to 2024-01-22 (476 events, 51 types, 154 locations) - representative sample from middle of dataset.

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

## Architectural Decision: Static-Only Deployment

**Decision:** Deploy as fully static site. No backend server required.

**Rationale:** The PMTiles contain all data needed for visualization:
- 9 count columns for category filtering (client-side)
- `type_counts` array for drill-down breakdown
- Population and rate for normalization display

No dynamic queries are needed - all filtering and aggregation happens client-side.

**Benefits:**
- Zero infrastructure cost (GitHub Pages, Cloudflare Pages)
- Global CDN by default
- No server process to maintain
- No security attack surface
- Simpler deployment pipeline

**Future extensibility:** If individual event drill-down is needed later, a backend can be added. Current architecture doesn't preclude this.

---

## Phase 4: Web Frontend (Not Started)

**Goal:** Interactive map with MapLibre GL JS loading PMTiles directly.

**Estimated Duration:** ~5 hours

**Architecture:** Vanilla JS, no build step, CDN dependencies, mobile-first CSS.

```
static/
├── index.html          # Page structure and layout
├── app.js              # MapLibre + PMTiles + interactions
├── style.css           # Responsive styling with mobile breakpoints
```

**Key Deliverables:**

- [ ] Basic map with PMTiles loading
  - `static/index.html` with MapLibre GL JS from unpkg CDN
  - `static/app.js` with PMTiles protocol registration
  - OSM raster base layer, Sweden-centered (lat: 62.5, lon: 16.5, zoom: 5)
  - Load single resolution (r5) to verify tiles display correctly

- [ ] H3 layer with color scale
  - Fill layer colored by `total_count`
  - Color interpolation: light (low) → dark red (high)
  - Cell outlines for visual clarity
  - `static/style.css` with legend positioning

- [ ] Automatic resolution switching
  - Pre-load all three PMTiles sources (r4, r5, r6)
  - Zoom-to-resolution mapping: z3-4→r4, z5→r5, z6+→r6
  - Switch layers on `zoomend` event
  - Resolution indicator in UI (current H3 level)

- [ ] Display mode toggle (Absolute/Normalized)
  - Toggle switch component
  - Absolute mode: color by `total_count`
  - Normalized mode: color by `rate_per_10000`
  - Dynamic legend labels update with mode

- [ ] Category filter dropdown
  - `<select>` with "All" + 8 category options
  - Filter expression updates layer based on `{category}_count > 0`
  - Maintains current display mode when filtering

- [ ] Click popup with cell details
  - Show on cell click: total, rate, category breakdown, top types, population
  - Parse `type_counts` array from tile properties
  - Dismiss on click outside
  - Selected cell highlight (outline)

- [ ] Mobile responsiveness
  - CSS breakpoint at 768px
  - Bottom sheet pattern for popup on mobile
  - Collapsible legend (tap to expand/collapse)
  - Touch-friendly controls (44px minimum)

- [ ] E2E test infrastructure
  - Add `playwright` and `pytest-playwright` to dev dependencies
  - `live_server` fixture in conftest.py (Python http.server on random port)
  - Serves `static/` directory with PMTiles in `tiles/` subdirectory
  - Server starts before tests, terminates after

- [ ] E2E tests (`tests/test_frontend_e2e.py`)
  - `@pytest.mark.e2e` marker for selective running
  - Test map loads (canvas visible, zoom in expected range)
  - Test PMTiles sources load (verify via `window.map.getSource()`)
  - Test H3 layer displays (verify via `window.map.getLayer()`)
  - Test resolution switching (set zoom via JS, check `window.currentResolution`)
  - Test display mode toggle (click toggle, verify legend updates)
  - Test category filter (select option, verify layer filter changes)
  - Test click popup (click map, verify popup appears with expected content)
  - Test filter persists across resolution changes

- [ ] Cross-browser verification
  - Playwright tests run in Chromium by default
  - Manual spot-check in Firefox, Safari
  - Test on actual mobile device

---

## Phase 5: Static Deployment (Not Started)

**Goal:** Deploy frontend + PMTiles to static hosting.

**Estimated Duration:** ~1 hour

**Hosting:** GitHub Pages (simplest, integrated with repo, free).

```
gh-pages branch:
├── index.html
├── app.js
├── style.css
└── tiles/
    ├── h3_r4.pmtiles
    ├── h3_r5.pmtiles
    └── h3_r6.pmtiles
```

**Key Deliverables:**

- [ ] Local preview server
  - Python `http.server` or similar for local testing
  - Verify PMTiles load correctly from `tiles/` subdirectory
  - Test all functionality before deploying

- [ ] Makefile deploy target
  - `make deploy` copies static files + PMTiles to deploy directory
  - Handles directory structure (static files at root, tiles in `tiles/`)
  - Can be run after `make pipeline-all`

- [ ] GitHub Pages configuration
  - Enable Pages in repository settings
  - Configure to serve from `gh-pages` branch or `/docs` folder
  - Verify deployment triggers on push

- [ ] Production verification
  - Test live URL in multiple browsers
  - Verify PMTiles load from GitHub Pages CDN
  - Check mobile functionality on actual device
  - Confirm all features work as in local testing

---

## Phase 6: Documentation & Polish (Not Started)

**Goal:** Complete README, enhance CI visibility, tag v1.0.0.

**Estimated Duration:** ~2 hours

**Key Deliverables:**

- [ ] CI enhancement
  - Add `dorny/test-reporter@v1` for inline test failure annotations
  - Add `py-cov-action/python-coverage-comment-action@v3` for coverage badge
  - Add Playwright browser install step (`uv run playwright install chromium`)
  - JUnit XML output (`--junitxml=test-results.xml`)
  - Proper permissions for coverage data branch
  - Reference: https://danielnouri.org/notes/2025/11/03/modern-python-ci-with-coverage-in-2025/

- [ ] README.md
  - Coverage badge at top
  - Project description (1-2 paragraphs)
  - Screenshot of the map
  - Live demo link
  - Data sources (Swedish Police API, SCB population grid)
  - Quick start instructions (`make install && make pipeline-all`)
  - License

- [ ] Category reference in README
  - Table of 8 categories with example event types
  - Explains what each category includes

- [ ] Final review
  - All tests passing
  - `make check` clean
  - Live demo working
  - README accurate and complete

- [ ] Tag v1.0.0 release
  - Create annotated git tag
  - GitHub release with changelog summary

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
- ⏳ Phase 4: Web frontend (static, no backend)
- ⏳ Phase 5: Static deployment
- ⏳ Phase 6: Documentation

**Architecture Decision:** Backend skipped - PMTiles contain complete data for visualization.

**Current Progress:** 4/6 phases complete (~65%)

**Estimated Remaining:** ~8 hours (Phase 4: 5h, Phase 5: 1h, Phase 6: 2h)

**Next Step:** Phase 4 - Web Frontend

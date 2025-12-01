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

## Architectural Decision: Hybrid Static + Dynamic API

**Decision:** PMTiles for aggregate visualization (static), FastAPI backend for event drill-down (dynamic).

**Rationale:** The map visualization works well with pre-computed PMTiles, but users need to browse and search individual events within H3 cells. This requires:
- Full-text search across event summaries and descriptions
- Flexible filtering by date range, category, and event type
- Pagination for cells with hundreds of events
- Access to complete event details including police report links

**Architecture:**
```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                              │
│  ┌──────────────────┐      ┌─────────────────────────────┐  │
│  │   Map (PMTiles)  │      │    Event Drill-Down Panel   │  │
│  │   - H3 cells     │ ───► │    - Search box             │  │
│  │   - Aggregates   │      │    - Date/category filters  │  │
│  │   - Colors       │      │    - Event list             │  │
│  └──────────────────┘      │    - Detail view            │  │
│           │                └─────────────────────────────┘  │
│           │                            │                     │
└───────────┼────────────────────────────┼─────────────────────┘
            │                            │
    Static PMTiles              Dynamic API Queries
            │                            │
┌───────────▼────────────────────────────▼─────────────────────┐
│                    FastAPI Backend                            │
│  ┌──────────────────┐      ┌─────────────────────────────┐   │
│  │  Static Files    │      │  /api/events                │   │
│  │  (PMTiles)       │      │  - H3 cell + filters        │   │
│  └──────────────────┘      │  - Full-text search (FTS)   │   │
│                            │  - Paginated results        │   │
│                            └─────────────────────────────┘   │
│                                        │                      │
│                            ┌───────────▼─────────────────┐   │
│                            │    DuckDB + events.parquet  │   │
│                            │    - FTS index on text      │   │
│                            │    - H3 cell computation    │   │
│                            └─────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
```

**Benefits of Hybrid Approach:**
- PMTiles: Fast aggregate visualization, CDN-cacheable, works offline
- API: Flexible queries, full-text search, complete event details
- Single deployment: FastAPI serves both static files and API
- DuckDB: Sub-100ms queries on 500k events, no external database needed

**Data Flow:**
1. User views map → PMTiles loaded from static files
2. User clicks H3 cell → Frontend shows aggregate stats from tile properties
3. User clicks "Browse Events" → API query with H3 cell + filters
4. User searches/filters → API returns paginated events
5. User clicks event → Full details shown inline, link to polisen.se

---

## Phase 4: Web Frontend ✅ COMPLETE

**Goal:** Interactive map with MapLibre GL JS loading PMTiles directly.

**Duration:** ~6 hours

**Outcome:** 11 E2E tests passing, interactive map with resolution switching, category filtering, and display mode toggle.

**Architecture:** Vanilla JS, no build step, CDN dependencies, responsive CSS.

```
static/
├── index.html          # Page structure and layout
├── app.js              # MapLibre + PMTiles + interactions (~520 lines)
├── style.css           # Responsive styling with mobile breakpoints
```

**Key Deliverables:**

- [x] Basic map with PMTiles loading
  - MapLibre GL JS + PMTiles protocol from unpkg CDN
  - OSM raster base layer, Sweden-centered (lat: 62.5, lon: 16.5, zoom: 5)
  - Starlette dev server with HTTP Range request support for PMTiles

- [x] H3 layer with color scale
  - Fill layer colored by `total_count` or `rate_per_10000`
  - Red sequential color scale (5 stops)
  - Cell outlines for visual clarity

- [x] Automatic resolution switching
  - Pre-load r4 and r5 PMTiles sources (r6 excluded - see Known Limitations)
  - Zoom-to-resolution mapping: z3-4→r4, z5+→r5
  - Switch layers on `zoomend` event
  - Resolution indicator in UI

- [x] Display mode toggle (Absolute/Normalized)
  - Custom toggle switch component
  - Absolute mode: color by `total_count`
  - Normalized mode: color by `rate_per_10000`
  - Dynamic legend updates with mode

- [x] Category filter dropdown
  - `<select>` with "All" + 8 category options
  - Layer filter expression based on `{category}_count > 0`
  - Filter persists across resolution changes

- [x] Click panel with cell details
  - Shows total, rate, population, category breakdown, top event types
  - Parses `type_counts` array from tile properties
  - Dismissible panel

- [x] Mobile responsiveness
  - CSS breakpoint at 768px
  - Collapsible legend (tap to expand/collapse)
  - Touch-friendly controls
  - Swipe-to-dismiss on details panel

- [x] E2E test infrastructure
  - Playwright + pytest-playwright
  - `live_server` fixture with Starlette/Uvicorn
  - Test fixtures generated via `make test-fixtures`
  - CI integration with tippecanoe installation

- [x] E2E tests (`tests/test_frontend_e2e.py`) - 11 tests
  - Map loads with canvas visible
  - PMTiles sources load (r4, r5)
  - H3 layer displays
  - Resolution switching with zoom
  - Display mode toggle
  - Category filter changes layer
  - Filter persists across resolution changes
  - Legend displays with color scale
  - Controls visible
  - Tiles actually render (queryRenderedFeatures)
  - Cell click shows details panel

**Key Improvements Made:**
- Excluded r6 from frontend due to centroid artifacts (rate inflation 2.5-4.3x)
- Excluded "Sammanfattning" editorial events from aggregation
- Added Known Limitations section to README documenting city-level coordinate issue

---

## Phase 5: Event Drill-Down Feature (Desktop-First)

**Goal:** Enable users to browse, search, and view individual events within H3 cells via a side drawer interface.

**Estimated Duration:** ~12-15 hours

**Approach:** TDD with API-first development. Build backend API with tests, then frontend with Playwright spike exploration before E2E tests.

**User Decisions (from expert panel discussion):**
- Content: Full `html_body` displayed inline with link to polisen.se
- Search: Full-text search with Swedish stemming across type, summary, html_body
- Filtering: Hierarchical categories (8) with type drill-down (~50 types)
- Date range: Presets (7d, 30d, 90d, 1y, all) + custom dual-calendar picker
- Platform: Desktop-first (side drawer), mobile adaptation in Phase 6
- Threshold: Cells with <3 events show count but disable drill-down (privacy)

**Architecture:**
```
crimecity3k/
├── api/
│   ├── __init__.py
│   ├── main.py           # FastAPI app with routes
│   ├── schemas.py        # Pydantic request/response models
│   ├── queries.py        # DuckDB query functions
│   └── fts.py            # Full-text search setup
├── sql/
│   └── events_query.sql  # Parameterized event query template
static/
├── app.js                # Extended with drill-down logic
├── components/
│   ├── side-drawer.js    # Drawer open/close, positioning
│   ├── filter-bar.js     # Date presets, category hierarchy, search
│   ├── event-list.js     # Paginated event cards
│   └── event-detail.js   # Expanded event view
```

---

### Task 5.1: DuckDB Full-Text Search Setup

**Goal:** Research and implement FTS indexing strategy for event search.

**Motivation:** Swedish stemming enables finding "stöld" when searching "stulen". DuckDB FTS extension provides this capability but requires understanding persistence behavior.

**Deliverables:**
- [ ] Research spike: Test DuckDB FTS extension behavior
  - Does FTS index persist across connections?
  - Performance with 500k events
  - Swedish stemmer availability and quality
  - Write findings in `tmp/fts_spike.py` (gitignored)

- [ ] Implement indexing strategy based on spike results
  - If persistent: Add FTS index creation to pipeline
  - If in-memory only: Build index on server startup
  - Create `crimecity3k/api/fts.py` with setup functions

- [ ] Test FTS functionality
  - Test Swedish stemming works ("stöld" matches "stulen")
  - Test multi-field search (type, summary, html_body)
  - Test search ranking (relevance ordering)

**Acceptance Criteria:**
- [ ] FTS queries return relevant results in <100ms
- [ ] Swedish word variations match appropriately
- [ ] Clear documentation of indexing approach

---

### Task 5.2: API Schema Definition

**Goal:** Define the request/response contract for the events API.

**Motivation:** Clear contracts enable parallel frontend/backend work and serve as documentation.

**Deliverables:**
- [ ] Create `crimecity3k/api/schemas.py` with Pydantic models:

```python
class EventsRequest(BaseModel):
    h3_cell: str                    # Required: H3 cell ID
    start_date: date | None         # Optional: filter start
    end_date: date | None           # Optional: filter end
    categories: list[str] | None    # Optional: category filter
    types: list[str] | None         # Optional: specific type filter
    search: str | None              # Optional: FTS query
    page: int = 1                   # Pagination
    per_page: int = 50              # Items per page (max 100)

class EventResponse(BaseModel):
    event_id: str
    datetime: datetime
    type: str
    category: str
    location_name: str
    summary: str
    html_body: str
    police_url: str                 # Full URL to polisen.se
    latitude: float
    longitude: float

class EventsListResponse(BaseModel):
    total: int
    page: int
    per_page: int
    events: list[EventResponse]

class TypeHierarchy(BaseModel):
    categories: dict[str, list[str]]  # category -> list of types
```

- [ ] Create `GET /api/events` endpoint stub in `crimecity3k/api/main.py`
- [ ] Create `GET /api/types` endpoint stub (returns category→types hierarchy)
- [ ] Create `GET /health` endpoint for deployment health checks

**Acceptance Criteria:**
- [ ] OpenAPI schema auto-generated at `/docs`
- [ ] Response models validate correctly
- [ ] Stubs return mock data for frontend development

---

### Task 5.3: API Tests (TDD Red Phase)

**Goal:** Write comprehensive API tests before implementation.

**Motivation:** Tests define expected behavior and catch edge cases early. Writing tests first forces us to think through the API contract thoroughly.

**Deliverables:**
- [ ] Create `tests/test_api_events.py` with failing tests:

```python
# Core functionality
def test_query_events_by_h3_cell_returns_results()
def test_query_events_pagination_works()
def test_query_events_returns_correct_total_count()

# Date filtering
def test_query_events_with_date_range_filters_correctly()
def test_query_events_with_start_date_only()
def test_query_events_with_end_date_only()

# Category/type filtering
def test_query_events_by_category_filters_correctly()
def test_query_events_by_multiple_categories()
def test_query_events_by_specific_type()
def test_query_events_by_category_and_type_combined()

# Full-text search
def test_query_events_with_search_term_matches_summary()
def test_query_events_with_search_term_matches_html_body()
def test_query_events_search_with_swedish_stemming()
def test_query_events_search_combined_with_filters()

# Edge cases
def test_query_events_empty_cell_returns_empty_list()
def test_query_events_invalid_h3_cell_returns_400()
def test_query_events_page_beyond_results_returns_empty()
def test_query_events_per_page_capped_at_100()

# Threshold enforcement
def test_query_events_cell_under_threshold_returns_limited_response()

# Types endpoint
def test_get_types_returns_category_hierarchy()
```

- [ ] Use pytest fixtures for test database with sample events
- [ ] Tests should import from api module and use TestClient

**Acceptance Criteria:**
- [ ] All tests written and failing (RED state)
- [ ] Tests cover all specified functionality
- [ ] Test fixtures representative of real data

---

### Task 5.4: API Implementation (TDD Green Phase)

**Goal:** Implement the events API to make all tests pass.

**Motivation:** With tests written, implementation has clear success criteria. Focus on making tests pass with minimal code.

**Deliverables:**
- [ ] Create `crimecity3k/sql/events_query.sql` template:
  - Parameterized query with H3 cell filter
  - Date range conditions (optional)
  - Category/type filtering via IN clauses
  - FTS search integration
  - Pagination with LIMIT/OFFSET
  - Total count query (separate or window function)

- [ ] Implement `crimecity3k/api/queries.py`:
  - `query_events()` function executing SQL template
  - `get_type_hierarchy()` function for category→types mapping
  - DuckDB connection management
  - H3 cell computation from lat/lon

- [ ] Complete `crimecity3k/api/main.py`:
  - FastAPI app with CORS middleware
  - `/api/events` endpoint with query parameter parsing
  - `/api/types` endpoint
  - `/health` endpoint
  - Static file serving (PMTiles, frontend assets)
  - Error handling with appropriate HTTP status codes

- [ ] Add `make serve-api` target to Makefile:
  - Starts FastAPI with uvicorn
  - Hot reload for development
  - Configurable port

**Acceptance Criteria:**
- [ ] All tests from Task 5.3 passing (GREEN state)
- [ ] API responds in <100ms for typical queries
- [ ] OpenAPI docs accurate and complete
- [ ] `make serve-api` starts server successfully

---

### Task 5.5: Frontend Spike Exploration

**Goal:** Explore UI patterns with Playwright before committing to tests.

**Motivation:** UI design benefits from experimentation. Spike scripts let us try ideas quickly without test overhead. Discoveries inform what to test.

**Deliverables:**
- [ ] Create `tmp/spike_side_drawer.py` (gitignored):
  - Open browser with Playwright
  - Inject experimental CSS for side drawer
  - Test different widths (350px, 400px, 450px)
  - Experiment with open/close animations
  - Try different positions (right, left)

- [ ] Create `tmp/spike_filter_bar.py`:
  - Experiment with date preset chip layout
  - Test category expansion interaction
  - Try search box placement options
  - Evaluate responsive behavior at different widths

- [ ] Create `tmp/spike_event_list.py`:
  - Test event card layouts
  - Experiment with expand/collapse behavior
  - Try different truncation lengths for summary
  - Test scroll behavior in drawer

- [ ] Document findings in `tmp/spike_findings.md`:
  - What worked well
  - What felt awkward
  - Recommended dimensions and behaviors
  - Screenshots if helpful

**Acceptance Criteria:**
- [ ] Spike scripts runnable and demonstrate UI concepts
- [ ] Clear recommendations for drawer width, animations, layouts
- [ ] Findings documented for reference during implementation

---

### Task 5.6: Frontend E2E Tests (TDD Red Phase)

**Goal:** Write E2E tests for drill-down functionality before implementation.

**Motivation:** E2E tests verify the complete user flow. Writing them first ensures we build what users need.

**Deliverables:**
- [ ] Add tests to `tests/test_frontend_e2e.py`:

```python
# Drawer interaction
def test_click_cell_opens_drill_down_drawer()
def test_drawer_shows_loading_state_initially()
def test_drawer_close_button_closes_drawer()
def test_click_outside_drawer_closes_it()

# Event list
def test_drawer_shows_event_list_after_loading()
def test_event_list_shows_correct_count()
def test_event_card_shows_date_type_summary()

# Filtering
def test_date_preset_filters_events()
def test_custom_date_range_filters_events()
def test_category_filter_shows_types_when_expanded()
def test_type_filter_narrows_results()
def test_search_filters_by_text()
def test_combined_filters_work_together()

# Event detail
def test_click_event_card_expands_detail()
def test_event_detail_shows_full_html_body()
def test_event_detail_has_police_report_link()
def test_police_report_link_correct_url()

# Pagination
def test_pagination_shows_page_info()
def test_pagination_next_page_loads_more()

# Threshold
def test_cell_under_threshold_shows_message_not_list()
```

- [ ] Tests use existing `live_server` fixture
- [ ] Add API mock or use test database for consistent data

**Acceptance Criteria:**
- [ ] All tests written and failing (RED state)
- [ ] Tests cover core user journeys
- [ ] Test selectors use data-testid attributes

---

### Task 5.7: Frontend Implementation

**Goal:** Build the side drawer with all components to make E2E tests pass.

**Motivation:** With API working and tests defined, frontend implementation has clear targets.

**Deliverables:**
- [ ] Update `static/index.html`:
  - Add side drawer container markup
  - Add data-testid attributes for testing
  - Include new component scripts

- [ ] Create `static/components/side-drawer.js`:
  - Drawer open/close state management
  - Animation (slide from right, 300ms ease)
  - Width: 420px (based on spike findings)
  - Close on X button, Escape key, click outside
  - Expose `window.openDrillDown(h3Cell)` for map integration

- [ ] Create `static/components/filter-bar.js`:
  - Date presets: Last 7d, 30d, 90d, 1yr, All time (chips)
  - Custom date range button → dual calendar popover
  - Category chips with expand/collapse for types
  - Search input with debounced API calls (300ms)
  - Filter state management and URL sync

- [ ] Create `static/components/event-list.js`:
  - Fetch from `/api/events` with current filters
  - Loading skeleton state
  - Event cards with: date, type badge, summary (truncated)
  - Pagination controls: "Showing 1-50 of 347" + Prev/Next
  - Empty state: "No events match your filters"
  - Error state: "Failed to load events. Try again."

- [ ] Create `static/components/event-detail.js`:
  - Expanded card view on click
  - Full `html_body` content (sanitized HTML or plain text)
  - "View Police Report" button → opens polisen.se URL
  - Back/collapse button to return to list

- [ ] Update `static/app.js`:
  - Integrate drill-down trigger on cell click
  - Pass H3 cell ID to drawer
  - Handle threshold check (disable if <3 events)

- [ ] Update `static/style.css`:
  - Side drawer styles (position, shadow, z-index)
  - Filter bar layout (flexbox chips)
  - Event card styles (hover, active states)
  - Event detail styles
  - Loading skeleton animations

**Acceptance Criteria:**
- [ ] All E2E tests from Task 5.6 passing (GREEN state)
- [ ] UI matches spike exploration findings
- [ ] Responsive at desktop widths (>1024px)
- [ ] Accessible: keyboard navigation, focus management

---

### Task 5.8: Polish and Edge Cases

**Goal:** Handle edge cases, improve loading states, ensure robustness.

**Motivation:** Production-ready code handles errors gracefully and provides feedback.

**Deliverables:**
- [ ] Loading states:
  - Skeleton cards while fetching
  - Disable filter controls during load
  - Show spinner on pagination

- [ ] Error handling:
  - API errors show user-friendly message
  - Network failures allow retry
  - Invalid H3 cell handled gracefully

- [ ] Threshold enforcement:
  - Cells with <3 events show: "X events in this area. Browse disabled for privacy."
  - Still show aggregate stats from tile properties
  - Link to "Learn more" explaining threshold

- [ ] Performance:
  - Debounce search input (300ms)
  - Cancel in-flight requests on new filter change
  - Virtual scroll if list exceeds 100 items (optional v1)

- [ ] Accessibility:
  - Drawer traps focus when open
  - Escape closes drawer
  - ARIA labels on interactive elements
  - Announce loading states to screen readers

**Acceptance Criteria:**
- [ ] All error states have user-friendly messages
- [ ] No console errors during normal usage
- [ ] Lighthouse accessibility score >90
- [ ] Works with keyboard-only navigation

---

## Phase 6: Mobile Adaptation (Bottom Sheet)

**Goal:** Adapt the drill-down experience for mobile devices using bottom sheet pattern.

**Estimated Duration:** ~6-8 hours

**Approach:** Same API backend, different UI container. Responsive detection switches between side drawer (desktop) and bottom sheet (mobile).

**Design Decisions:**
- Bottom sheet pattern matches Google Maps, Uber, native mobile map apps
- Three states: peek (100px), half (50%), full (90%)
- Swipe gestures for state transitions
- Same filter bar and event list components, reflowed for narrower width
- Breakpoint: 768px (below = mobile)

**Architecture:**
```
static/
├── components/
│   ├── side-drawer.js       # Desktop (unchanged)
│   ├── bottom-sheet.js      # NEW: Mobile container
│   ├── drill-down-content.js # NEW: Shared content (extracted)
│   ├── filter-bar.js        # Reflowed for mobile
│   ├── event-list.js        # Unchanged
│   └── event-detail.js      # Unchanged
```

---

### Task 6.1: Extract Shared Drill-Down Content

**Goal:** Refactor Phase 5 components to separate container from content.

**Motivation:** Side drawer and bottom sheet share the same content (filters, list, detail). Extract shared logic to avoid duplication.

**Deliverables:**
- [ ] Create `static/components/drill-down-content.js`:
  - Extracted filter bar, event list, event detail
  - Accepts container element as parameter
  - Handles all API calls and state management
  - Container-agnostic (works in drawer or sheet)

- [ ] Refactor `static/components/side-drawer.js`:
  - Import and use drill-down-content
  - Only handles drawer open/close, positioning
  - Passes container to content component

- [ ] Ensure all existing E2E tests still pass after refactor

**Acceptance Criteria:**
- [ ] No functional changes to desktop experience
- [ ] All Phase 5 E2E tests pass
- [ ] Clear separation of container vs content concerns

---

### Task 6.2: Bottom Sheet Component

**Goal:** Build the mobile bottom sheet container with gesture support.

**Motivation:** Bottom sheets are the native mobile pattern for progressive disclosure in map apps.

**Deliverables:**
- [ ] Create `static/components/bottom-sheet.js`:
  - Three states: peek (100px), half (50vh), full (90vh)
  - Initial state on open: half
  - Swipe up → expand to next state
  - Swipe down → collapse to previous state or close
  - Tap header → toggle between half and full
  - Close button in header
  - Backdrop overlay in full state
  - Hardware-accelerated animations (transform, not height)

- [ ] Gesture handling:
  - Touch start/move/end event listeners
  - Velocity detection for momentum
  - Snap to nearest state on release
  - Prevent scroll interference (handle vs content)

- [ ] Visual design:
  - Drag handle indicator at top
  - Rounded top corners
  - Shadow for depth
  - Safe area inset for notched phones

**Acceptance Criteria:**
- [ ] Smooth 60fps animations
- [ ] Natural gesture feel (momentum, snap)
- [ ] Works on iOS Safari and Android Chrome
- [ ] No scroll conflicts with content

---

### Task 6.3: Responsive Layout Integration

**Goal:** Automatically switch between side drawer and bottom sheet based on viewport.

**Motivation:** Users shouldn't need to choose - the app should adapt.

**Deliverables:**
- [ ] Update `static/app.js`:
  - Detect viewport width on load and resize
  - Below 768px → use bottom sheet
  - Above 768px → use side drawer
  - Handle orientation changes

- [ ] Update filter bar layout for mobile:
  - Stack date presets vertically or wrap
  - Full-width search input
  - Category chips scroll horizontally
  - Compact spacing

- [ ] Update event card layout for mobile:
  - Full width cards
  - Larger touch targets (44px minimum)
  - Adjusted typography

**Acceptance Criteria:**
- [ ] Seamless transition when resizing browser
- [ ] Correct container used at each breakpoint
- [ ] No layout jumps or flicker

---

### Task 6.4: Mobile E2E Tests

**Goal:** Test mobile-specific behaviors with Playwright mobile emulation.

**Motivation:** Mobile has unique interactions (gestures, viewport) that need dedicated tests.

**Deliverables:**
- [ ] Add mobile tests to `tests/test_frontend_e2e.py`:

```python
@pytest.mark.mobile
class TestMobileE2E:
    # Use Playwright's mobile device emulation

    def test_mobile_shows_bottom_sheet_not_drawer()
    def test_bottom_sheet_opens_in_half_state()
    def test_swipe_up_expands_to_full()
    def test_swipe_down_collapses_or_closes()
    def test_tap_drag_handle_toggles_state()
    def test_content_scrollable_in_full_state()
    def test_filter_bar_mobile_layout()
    def test_event_cards_full_width()
    def test_orientation_change_maintains_state()
```

- [ ] Configure Playwright for mobile emulation:
  - iPhone 12 viewport (390x844)
  - Touch events enabled
  - Consider testing Android viewport too

**Acceptance Criteria:**
- [ ] All mobile tests pass
- [ ] Tests run in CI with mobile emulation
- [ ] Coverage of gesture interactions

---

### Task 6.5: Touch Gesture Refinement

**Goal:** Polish gesture handling for production quality.

**Motivation:** Gesture quality makes or breaks mobile UX. Users expect native-feeling interactions.

**Deliverables:**
- [ ] Momentum scrolling:
  - Track touch velocity
  - Apply inertia on release
  - Decelerate naturally

- [ ] Overscroll behavior:
  - Rubber-band effect at sheet edges
  - Pull-to-refresh style feedback (visual only)

- [ ] Conflict resolution:
  - Horizontal swipe → don't intercept (let content scroll)
  - Vertical swipe on drag handle → sheet gesture
  - Vertical swipe on content → scroll content (unless at top)

- [ ] iOS Safari fixes:
  - Prevent bounce scroll on body
  - Handle safe areas (notch, home indicator)
  - Test with actual device

**Acceptance Criteria:**
- [ ] Gestures feel native on iOS and Android
- [ ] No accidental sheet dismissal when scrolling content
- [ ] Works correctly on actual mobile devices (not just emulator)

---

### Task 6.6: Mobile Polish

**Goal:** Final polish for mobile experience.

**Motivation:** Details matter for perceived quality.

**Deliverables:**
- [ ] Performance optimization:
  - Reduce repaints during gestures
  - Lazy load event detail content
  - Optimize for low-end devices

- [ ] Visual polish:
  - Consistent spacing with iOS/Android conventions
  - Proper font sizes for readability
  - Touch feedback (ripple or highlight)

- [ ] Accessibility on mobile:
  - VoiceOver/TalkBack compatible
  - Gesture alternatives for accessibility users
  - Focus management across states

- [ ] PWA considerations (optional):
  - Add to home screen support
  - Standalone display mode
  - Theme color for status bar

**Acceptance Criteria:**
- [ ] Smooth experience on 3-year-old phone
- [ ] No accessibility violations on mobile
- [ ] Feels like a native app

---

## Phase 7: Container Deployment

**Goal:** Deploy the application using containerized deployment with zero-downtime updates.

**Estimated Duration:** ~4-5 hours

**Approach:** Follow proven deployment patterns: Podman containers, systemd user services, Makefile automation. Caddy reverse proxy managed separately on server.

**Target Server:** Configure `DEPLOY_SERVER` in Makefile (e.g., `user@server`)
- Assumes Ubuntu 24.04 or similar with Podman and Caddy pre-installed
- Port 8000 may be in use by other applications
- CrimeCity3K will use port **8001** to avoid conflicts

**Architecture:**
```
Containerfile
├── Base: python:3.13-slim
├── System deps: curl, ca-certificates
├── Install: uv via pip, then uv pip install --system
├── Copy: source code, static files, data
├── Expose: 8000 (internal), mapped to 8001 on host
└── CMD: uvicorn with --proxy-headers for Caddy

Makefile targets:
├── build-container     # Build image with git SHA tag
├── upload-container    # SCP tarball to server, load image
├── deploy-container    # Stop old, start new, verify health
├── deploy             # All three in sequence
├── deploy-status      # Check running container
├── deploy-logs        # Tail container logs
└── install-service    # Copy systemd service file

Server stack (shared infrastructure):
├── Ubuntu 24.04 LTS
├── Podman 4.9.3 rootless
├── Caddy 2.10.2 (system service, auto HTTPS)
├── Systemd user session (lingering enabled)
└── SSH access configured
```

---

### Task 7.1: Containerfile Creation

**Goal:** Create a production-ready container image.

**Motivation:** Containers provide reproducible, isolated deployments. Following established patterns reduces debugging time.

**Deliverables:**
- [ ] Create `Containerfile`:
  ```dockerfile
  # CrimeCity3K - Container Image
  # Self-contained deployment with Python 3.13, application code, and data

  FROM python:3.13-slim

  # Set working directory
  WORKDIR /app

  # Install system dependencies
  # - curl: for container health checks
  # - ca-certificates: for HTTPS connections (DuckDB extensions, external APIs)
  RUN apt-get update && \
      apt-get install -y --no-install-recommends \
          curl \
          ca-certificates \
      && rm -rf /var/lib/apt/lists/*

  # Install uv for Python dependency management
  RUN pip install --no-cache-dir uv==0.4.30

  # Copy project files
  COPY pyproject.toml README.md config.toml ./
  COPY crimecity3k/ ./crimecity3k/
  COPY static/ ./static/

  # Copy data files (PMTiles + events parquet)
  COPY data/tiles/pmtiles/ ./data/tiles/pmtiles/
  COPY data/events.parquet ./data/

  # Install Python dependencies
  # Use uv to install from pyproject.toml without virtualenv (container isolation)
  RUN uv pip install --system --no-cache -e .

  # Expose application port
  EXPOSE 8000

  # Health check: verify API is responding
  HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
      CMD curl -f http://localhost:8000/health || exit 1

  # Run FastAPI application with uvicorn
  # --proxy-headers: read X-Forwarded-For from Caddy
  # --forwarded-allow-ips '*': trust proxy (safe since bound to 127.0.0.1)
  CMD ["uvicorn", "crimecity3k.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
  ```

- [ ] Add `.containerignore` file:
  ```
  .git
  .venv
  __pycache__
  *.pyc
  tmp/
  tests/
  .pytest_cache
  .mypy_cache
  .ruff_cache
  *.tar
  ```

- [ ] Test local container build and run

**Acceptance Criteria:**
- [ ] `podman build` succeeds
- [ ] Container starts and serves on port 8000
- [ ] Health check passes (`curl http://localhost:8000/health`)
- [ ] Image size reasonable (<1GB)

---

### Task 7.2: Makefile Deployment Targets

**Goal:** Automate the build-upload-deploy cycle.

**Motivation:** One command deployment reduces errors and documents the process.

**Deliverables:**
- [ ] Add deployment configuration variables to Makefile:
  ```makefile
  DEPLOY_SERVER := user@server
  DEPLOY_DIR := ~/crimecity3k-deploy
  DEPLOY_IMAGE_NAME := crimecity3k
  DEPLOY_CONTAINER_NAME := crimecity3k
  DEPLOY_GIT_SHA := $(shell git rev-parse --short HEAD)
  DEPLOY_TIMESTAMP := $(shell date +%Y%m%d)
  DEPLOY_TAG := $(DEPLOY_GIT_SHA)-$(DEPLOY_TIMESTAMP)
  ```

- [ ] Add `build-container` target:
  - Build with git SHA tag
  - Tag as :latest
  - Save to tarball

- [ ] Add `upload-container` target:
  - SCP tarball to server
  - Load image with podman

- [ ] Add `deploy-container` target:
  - Stop existing container
  - Remove old container
  - Tag new image as :production
  - Run new container with port mapping
  - Wait for health check

- [ ] Add `deploy` meta-target:
  - Runs build → upload → deploy in sequence

- [ ] Add `deploy-status` and `deploy-logs` targets

**Acceptance Criteria:**
- [ ] `make deploy` works end-to-end
- [ ] Health check verification before declaring success
- [ ] Clear output showing progress and version

---

### Task 7.3: Systemd User Service

**Goal:** Run container as a systemd user service for auto-restart and boot persistence.

**Motivation:** Systemd provides process supervision, logging, and automatic restart on failure.

**Deliverables:**
- [ ] Create `deployment/crimecity3k.service`:
  ```ini
  [Unit]
  Description=CrimeCity3K - Swedish Police Events Map
  After=network-online.target
  Wants=network-online.target

  [Service]
  Type=simple
  Restart=always
  RestartSec=10s
  TimeoutStartSec=60s
  TimeoutStopSec=30s

  # Remove existing container if present (handles upgrades)
  ExecStartPre=-/usr/bin/podman stop crimecity3k
  ExecStartPre=-/usr/bin/podman rm crimecity3k

  # Start container
  # - Uses :production tag (updated by deployment)
  # - Port 8001 on host (8000 internal) to avoid conflicts with other services
  # - Named container for easy management
  ExecStart=/usr/bin/podman run \
      --name crimecity3k \
      --rm \
      -p 127.0.0.1:8001:8000 \
      localhost/crimecity3k:production

  # Stop container gracefully
  ExecStop=/usr/bin/podman stop -t 10 crimecity3k

  # Container health checks will cause restart if unhealthy
  RestartForceExitStatus=0

  [Install]
  WantedBy=default.target
  ```

- [ ] Add `install-service` Makefile target:
  - Copy service file to `~/.config/systemd/user/`
  - Reload systemd daemon
  - Print enable/start instructions

**Acceptance Criteria:**
- [ ] Service starts on boot
- [ ] Automatic restart on container crash
- [ ] Logs accessible via `journalctl --user -u crimecity3k`
- [ ] ExecStartPre handles existing container gracefully

---

### Task 7.4: Manual Server Configuration (One-Time)

**Goal:** Document and execute the one-time server setup steps not automated by Makefile.

**Motivation:** Some configuration (DNS, Caddy, service enablement) requires manual steps. Document these clearly for reproducibility.

**Context:** Production server already has Podman, Caddy, and lingering configured. CrimeCity3K reuses this shared infrastructure.

**Deliverables:**

- [ ] **DNS Configuration:**
  - Create A record: `your-domain.example.com` → server IP
  - Caddy will automatically obtain Let's Encrypt certificate
  - Verify DNS propagation before proceeding

- [ ] **Update Caddy Configuration** (on server as root):
  ```bash
  sudo nano /etc/caddy/Caddyfile
  ```

  Add new site block:
  ```caddyfile
  # CrimeCity3K - Swedish Police Events Map
  your-domain.example.com {
      # Reverse proxy to local container (port 8001)
      reverse_proxy localhost:8001

      # Gzip compression for better performance
      encode gzip

      # Logging to systemd journal
      log

      # Security headers
      header {
          X-Frame-Options SAMEORIGIN
          X-Content-Type-Options nosniff
          Referrer-Policy strict-origin-when-cross-origin
      }
  }
  ```

  Reload Caddy:
  ```bash
  sudo systemctl reload caddy
  ```

- [ ] **Create Deployment Directory:**
  ```bash
  ssh $DEPLOY_SERVER 'mkdir -p ~/crimecity3k-deploy'
  ```

- [ ] **Enable Systemd Service** (after first deploy):
  ```bash
  # Install service file (via make install-service)
  make install-service

  # On server: enable and start
  ssh $DEPLOY_SERVER 'systemctl --user daemon-reload'
  ssh $DEPLOY_SERVER 'systemctl --user enable crimecity3k'
  ssh $DEPLOY_SERVER 'systemctl --user start crimecity3k'
  ```

- [ ] **Verify Setup:**
  ```bash
  # Check Caddy status
  ssh $DEPLOY_SERVER 'sudo systemctl status caddy'

  # Check service status
  ssh $DEPLOY_SERVER 'systemctl --user status crimecity3k'

  # Test health endpoint (via SSH tunnel)
  ssh $DEPLOY_SERVER 'curl http://localhost:8001/health'

  # Test public URL (replace with your domain)
  curl https://your-domain.example.com/health
  ```

**Server Prerequisites (if not already configured):**
- [x] Podman 4.9.3 installed
- [x] Caddy 2.10.2 installed and running
- [x] User lingering enabled (`loginctl enable-linger $USER`)
- [x] SSH access configured

**Acceptance Criteria:**
- [ ] DNS resolves to server IP
- [ ] HTTPS certificate automatically provisioned by Caddy
- [ ] `https://your-domain.example.com/health` returns healthy status
- [ ] Service auto-restarts on server reboot

---

### Task 7.5: CI/CD Integration (Optional)

**Goal:** Automate deployment on push to main branch.

**Motivation:** Continuous deployment reduces manual steps and ensures latest code is live.

**Deliverables:**
- [ ] Add GitHub Actions workflow `deploy.yml`:
  - Trigger on push to main
  - Build container in CI
  - Upload to server via SSH
  - Deploy container
  - Verify health check

- [ ] Configure secrets:
  - SSH private key
  - Server hostname
  - Deploy user

- [ ] Add deployment status badge to README

**Acceptance Criteria:**
- [ ] Push to main triggers deployment
- [ ] Deployment failure notifies maintainer
- [ ] Rollback possible by reverting commit

---

## Phase 8: Documentation & Polish

**Goal:** Complete documentation, enhance CI visibility, prepare for public release.

**Estimated Duration:** ~3-4 hours

**Approach:** Document what exists, don't over-document what might change.

---

### Task 8.1: README Enhancement

**Goal:** Update README to reflect all features including drill-down.

**Deliverables:**
- [ ] Update feature list:
  - Add event drill-down capability
  - Mention full-text search
  - Note mobile support

- [ ] Add screenshots:
  - Map overview with H3 cells
  - Side drawer with event list
  - Mobile bottom sheet view
  - Event detail view

- [ ] Update Quick Start:
  - Include API server command
  - Note data requirements

- [ ] Add API documentation section:
  - Link to OpenAPI docs at `/docs`
  - Brief endpoint descriptions

- [ ] Update Architecture diagram:
  - Show API + frontend flow
  - Note PMTiles vs API paths

**Acceptance Criteria:**
- [ ] README accurately describes current state
- [ ] Screenshots are up-to-date
- [ ] Clear path from clone to running

---

### Task 8.2: CI Enhancement

**Goal:** Improve CI feedback and coverage visibility.

**Deliverables:**
- [ ] Add test annotations:
  - `dorny/test-reporter@v1` for inline failure display
  - JUnit XML output from pytest

- [ ] Add coverage reporting:
  - Coverage badge in README
  - Coverage comment on PRs
  - Trend tracking

- [ ] Ensure E2E tests run in CI:
  - Playwright browser install
  - Test fixtures generation
  - Both desktop and mobile tests

**Acceptance Criteria:**
- [ ] Test failures show inline in PR
- [ ] Coverage badge accurate and updated
- [ ] CI catches regressions reliably

---

### Task 8.3: Known Limitations Update

**Goal:** Document new limitations discovered during development.

**Deliverables:**
- [ ] Update Known Limitations section:
  - FTS search limitations (if any discovered)
  - Mobile browser compatibility notes
  - Performance characteristics

- [ ] Add Troubleshooting section if needed

**Acceptance Criteria:**
- [ ] Users can self-diagnose common issues
- [ ] Limitations are honest and helpful

---

### Task 8.4: Release Preparation

**Goal:** Prepare for tagged release.

**Deliverables:**
- [ ] Final review:
  - All tests passing
  - `make check` clean
  - Live demo working
  - Documentation accurate

- [ ] Version tagging:
  - Update version in pyproject.toml (if present)
  - Create annotated git tag v2.0.0
  - Write release notes

- [ ] GitHub Release:
  - Changelog summary
  - Migration notes from v1 (if applicable)
  - Link to live demo

**Acceptance Criteria:**
- [ ] Clean release with no known critical bugs
- [ ] Release notes helpful for users
- [ ] Demo site live and functional

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

CrimeCity3K v2 is complete when:
- ✅ Phase 0: Foundation (11 tests, CI working)
- ✅ Phase 1: Population pipeline (16 tests, 3 resolutions)
- ✅ Phase 2: Event aggregation (24 tests, category filtering)
- ✅ Phase 3: GeoJSON + PMTiles (16 tests, full tile pipeline)
- ✅ Phase 4: Web frontend (11 E2E tests, map visualization)
- ⏳ Phase 5: Event drill-down (desktop side drawer, FastAPI backend)
- ⏳ Phase 6: Mobile adaptation (bottom sheet, gestures)
- ⏳ Phase 7: Container deployment (Podman, systemd)
- ⏳ Phase 8: Documentation & polish

**Architecture Evolution:**
- v1 (Phases 0-4): Static PMTiles visualization, no backend
- v2 (Phases 5-8): Hybrid static + dynamic API for event drill-down

**Current Progress:** 5/8 phases complete (~55%)

**Estimated Remaining:** ~25-30 hours
- Phase 5: 12-15h (API + frontend)
- Phase 6: 6-8h (mobile adaptation)
- Phase 7: 4-5h (deployment)
- Phase 8: 3-4h (documentation)

**Next Step:** Phase 5, Task 5.1 - DuckDB Full-Text Search Setup

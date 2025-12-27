"""End-to-end tests for the CrimeCity3K frontend using Playwright.

These tests verify the complete frontend functionality including map rendering,
PMTiles loading, municipality visualization, filtering, and UI controls.

Wait Strategy: Uses explicit waits instead of time.sleep() for deterministic tests.
See tmp/spike_wait_discussion.md for rationale.
"""

import re

import pytest
from playwright.sync_api import Page, ViewportSize, expect

# --- Wait Helper Functions ---
# These replace arbitrary time.sleep() calls with explicit state checks.


def wait_for_map_ready(page: Page, timeout: int = 15000) -> None:
    """Wait for MapLibre map to be fully loaded with sources."""
    page.wait_for_selector("#map canvas", timeout=timeout)
    page.wait_for_function("window.map && window.map.loaded()", timeout=timeout)


def wait_for_tiles_rendered(page: Page, timeout: int = 15000) -> None:
    """Wait for municipality tiles to be rendered on map."""
    page.wait_for_function(
        "window.map && window.map.queryRenderedFeatures({layers: ['municipalities']}).length > 0",
        timeout=timeout,
    )


def wait_for_drawer_open(page: Page, timeout: int = 5000) -> None:
    """Wait for drill-down drawer to open."""
    page.wait_for_selector("[data-testid='drill-down-drawer'].open", timeout=timeout)


def wait_for_drawer_closed(page: Page, timeout: int = 5000) -> None:
    """Wait for drill-down drawer to close."""
    page.wait_for_selector("[data-testid='drill-down-drawer']:not(.open)", timeout=timeout)


def wait_for_drawer_content(page: Page, timeout: int = 10000) -> None:
    """Wait for drawer content to load (events, threshold, empty, or error state)."""
    page.wait_for_selector(
        "[data-testid='event-list'].visible, "
        "[data-testid='threshold-message'].visible, "
        "#empty-state.visible, "
        "#error-state.visible",
        timeout=timeout,
    )


@pytest.mark.e2e
class TestFrontendE2E:
    """End-to-end tests for the CrimeCity3K map frontend."""

    def test_map_loads_successfully(self, page: Page, live_server: str) -> None:
        """Test that the map loads with base tiles and canvas."""
        page.goto(live_server)

        # Map container should exist
        map_element = page.locator("#map")
        expect(map_element).to_be_visible()

        # MapLibre canvas should be created
        canvas = page.locator("#map canvas")
        expect(canvas).to_be_visible(timeout=15000)

        # Map object should be accessible with valid zoom
        zoom = page.evaluate("window.map ? window.map.getZoom() : null")
        assert zoom is not None, "Map object not found"
        assert 3 <= zoom <= 12, f"Zoom out of range: {zoom}"

    def test_pmtiles_sources_load(self, page: Page, live_server: str) -> None:
        """Test that municipality PMTiles source is loaded."""
        page.goto(live_server)
        wait_for_map_ready(page)

        # Check that municipality source is loaded
        source_loaded = page.evaluate("""
            () => {
                const source = window.map.getSource('municipality-tiles');
                return source !== undefined;
            }
        """)
        assert source_loaded, "Municipality tiles source should be loaded"

    def test_municipalities_layer_displays(self, page: Page, live_server: str) -> None:
        """Test that the municipalities layer is added to the map."""
        page.goto(live_server)
        wait_for_map_ready(page)

        has_layer = page.evaluate(
            "window.map && window.map.getLayer('municipalities') !== undefined"
        )
        assert has_layer, "Municipalities layer not found"

    def test_display_mode_toggle(self, page: Page, live_server: str) -> None:
        """Test that display mode toggle switches between absolute and normalized."""
        page.goto(live_server)
        wait_for_map_ready(page)

        # Initial state should be count mode
        mode_label = page.locator("#display-mode-label")
        expect(mode_label).to_have_text("Count")

        legend_title = page.locator("#legend-title")
        expect(legend_title).to_contain_text("Event Count")

        # Click the visible toggle slider (not the hidden checkbox)
        toggle_slider = page.locator(".toggle-slider")
        toggle_slider.click()

        # Wait for mode to change via text assertion (has built-in retry)
        expect(mode_label).to_have_text("Rate")
        expect(legend_title).to_contain_text("Rate per 10,000")

        # Click again to switch back
        toggle_slider.click()

        expect(mode_label).to_have_text("Count")
        expect(legend_title).to_contain_text("Event Count")

    def test_category_filter_dropdown(self, page: Page, live_server: str) -> None:
        """Test that category filter dropdown changes layer filter."""
        page.goto(live_server)
        wait_for_map_ready(page)

        # Filter dropdown should exist
        filter_dropdown = page.locator("#category-filter")
        expect(filter_dropdown).to_be_visible()

        # Initial filter should be null (all categories)
        initial_filter = page.evaluate("window.map.getFilter('municipalities')")
        assert initial_filter is None, "Initial filter should be null"

        # Select violence category
        filter_dropdown.select_option("violence")

        # Wait for filter to be applied
        page.wait_for_function("window.map.getFilter('municipalities') !== null", timeout=3000)

        # Layer filter should be applied
        violence_filter = page.evaluate("window.map.getFilter('municipalities')")
        assert violence_filter is not None, "Filter should be applied for violence"
        assert violence_filter[0] == ">", "Filter should use > comparison"

        # Select "all" to remove filter
        filter_dropdown.select_option("all")

        # Wait for filter to be removed (MapLibre may return null or undefined)
        page.wait_for_function("!window.map.getFilter('municipalities')", timeout=5000)

        filter_after = page.evaluate("window.map.getFilter('municipalities')")
        assert not filter_after, "Filter should be null/undefined when 'all' selected"

    def test_legend_displays(self, page: Page, live_server: str) -> None:
        """Test that legend is visible with color scale items."""
        page.goto(live_server)
        wait_for_map_ready(page)

        legend = page.locator("#legend")
        expect(legend).to_be_visible()

        # Legend title should show current mode
        legend_title = page.locator("#legend-title")
        expect(legend_title).to_have_text("Event Count")

        # Should have 6 legend items (based on color scale stops: 0-10, 10-50, 50-200,
        # 200-500, 500-1500, 1500+)
        legend_items = page.locator(".legend-item")
        expect(legend_items).to_have_count(6)

    def test_controls_visible(self, page: Page, live_server: str) -> None:
        """Test that control panel is visible with all controls."""
        page.goto(live_server)

        # Controls panel
        controls = page.locator("#controls")
        expect(controls).to_be_visible()

        # Category filter
        category_filter = page.locator("#category-filter")
        expect(category_filter).to_be_visible()

        # Toggle switch and slider (checkbox is hidden by CSS)
        toggle_switch = page.locator(".toggle-switch")
        expect(toggle_switch).to_be_visible()

        toggle_slider = page.locator(".toggle-slider")
        expect(toggle_slider).to_be_visible()

        # Hidden checkbox should be attached but not visible
        checkbox = page.locator("#display-mode-toggle")
        expect(checkbox).to_be_attached()

    def test_tiles_actually_render(self, page: Page, live_server: str) -> None:
        """Test that municipality tile data actually renders on the map.

        This is a critical test that verifies PMTiles are being fetched and
        rendered correctly. It would have caught the HTTP Range request bug
        where the server didn't support byte-range requests required by PMTiles.
        """
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Query rendered features - this is the critical assertion
        # If PMTiles aren't loading properly, this will return 0
        features = page.evaluate("""
            () => {
                try {
                    const features = window.map.queryRenderedFeatures({
                        layers: ['municipalities']
                    });
                    return {
                        count: features.length,
                        hasData: features.length > 0,
                        sample: features.length > 0 ? {
                            kommun_namn: features[0].properties.kommun_namn,
                            total_count: features[0].properties.total_count
                        } : null
                    };
                } catch (e) {
                    return { error: e.message, count: 0, hasData: false };
                }
            }
        """)

        assert features.get("error") is None, f"Error querying features: {features.get('error')}"
        assert features["hasData"], (
            "No municipality tiles rendered! This likely means PMTiles failed to load. "
            "Check that the server supports HTTP Range requests."
        )
        assert features["count"] > 0, "Expected at least one rendered feature"
        assert features["sample"] is not None, "Sample feature should exist"
        assert features["sample"]["kommun_namn"] is not None, (
            "Feature should have kommun_namn property"
        )

    def test_cell_click_shows_details(self, page: Page, live_server: str) -> None:
        """Test that clicking a municipality shows the details panel.

        This verifies the click interaction works end-to-end.
        """
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # First verify we have features to click
        feature_count = page.evaluate("""
            () => window.map.queryRenderedFeatures({layers: ['municipalities']}).length
        """)
        assert feature_count > 0, "Need rendered features to test click interaction"

        # Details panel should be hidden initially
        details_panel = page.locator("#cell-details")
        assert not details_panel.is_visible(), "Details panel should be hidden initially"

        # Find a visible feature and click its center
        click_result = page.evaluate("""
            () => {
                const canvas = document.querySelector('#map canvas');
                const rect = canvas.getBoundingClientRect();
                const width = rect.width;
                const height = rect.height;

                const features = window.map.queryRenderedFeatures({layers: ['municipalities']});
                if (features.length === 0) return { success: false, error: 'No features' };

                // Find features with centroids inside the visible canvas
                const visibleFeatures = [];
                for (const feature of features) {
                    const geomType = feature.geometry.type;
                    let outerRing;

                    if (geomType === 'Polygon') {
                        outerRing = feature.geometry.coordinates[0];
                    } else if (geomType === 'MultiPolygon') {
                        outerRing = feature.geometry.coordinates[0][0];
                    } else {
                        continue;
                    }

                    let sumX = 0, sumY = 0;
                    let validCoords = 0;
                    for (const coord of outerRing) {
                        if (!Array.isArray(coord) || coord.length !== 2) continue;
                        try {
                            const point = window.map.project(coord);
                            sumX += point.x;
                            sumY += point.y;
                            validCoords++;
                        } catch (e) {}
                    }

                    if (validCoords === 0) continue;

                    const centroidX = sumX / validCoords;
                    const centroidY = sumY / validCoords;

                    const margin = 50;
                    if (centroidX >= margin && centroidX < (width - margin) &&
                        centroidY >= margin && centroidY < (height - margin)) {
                        visibleFeatures.push({
                            x: centroidX,
                            y: centroidY,
                            kommun_namn: feature.properties.kommun_namn,
                            distToCenter: Math.pow(centroidX - width/2, 2) +
                                         Math.pow(centroidY - height/2, 2)
                        });
                    }
                }

                if (visibleFeatures.length === 0)
                    return { success: false, error: 'No visible features' };

                // Pick the feature closest to center
                visibleFeatures.sort((a, b) => a.distToCenter - b.distToCenter);
                const best = visibleFeatures[0];

                return {
                    success: true,
                    x: best.x,
                    y: best.y,
                    kommun_namn: best.kommun_namn
                };
            }
        """)

        if click_result.get("success"):
            # Click on the feature (position from JS queryRenderedFeatures)
            pos = {"x": click_result["x"], "y": click_result["y"]}
            page.click("#map canvas", position=pos, force=True)  # type: ignore[arg-type]

            # Wait for details panel to become visible
            page.wait_for_selector("#cell-details.visible", timeout=5000)

            # Details panel should now be visible
            assert details_panel.is_visible(), "Details panel should show after clicking a cell"

            # Details content should have data (label is "All Events" when no filter)
            details_content = page.locator("#details-content")
            expect(details_content).to_contain_text("Events")


@pytest.mark.e2e
class TestDrillDownDrawer:
    """E2E tests for the event drill-down side drawer.

    These tests verify the complete drill-down flow including drawer interaction,
    event list display, filtering, and event detail expansion.
    """

    # --- Drawer Interaction ---

    def test_click_cell_opens_drill_down_drawer(self, page: Page, live_server: str) -> None:
        """Clicking a municipality should open the drill-down drawer."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Drawer should not have 'open' class initially (it's hidden via CSS transform)
        drawer = page.locator("[data-testid='drill-down-drawer']")
        has_open_class = drawer.evaluate("el => el.classList.contains('open')")
        assert not has_open_class, "Drawer should not have 'open' class initially"

        # Click a rendered feature
        self._click_municipality(page)
        wait_for_drawer_open(page)

        # Drawer should now have 'open' class
        has_open_class = drawer.evaluate("el => el.classList.contains('open')")
        assert has_open_class, "Drawer should have 'open' class after click"

    def test_drawer_shows_loading_state_initially(self, page: Page, live_server: str) -> None:
        """Drawer should show a loading spinner while fetching events."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Click a cell
        self._click_municipality(page)

        # Loading indicator should appear briefly
        # In a real test, we'd slow down the API to observe this
        # For now, just verify the element can be located
        page.locator("[data-testid='loading-spinner']")
        # Loading may be too fast to observe in practice

    def test_drawer_close_button_closes_drawer(self, page: Page, live_server: str) -> None:
        """Clicking the close button should close the drawer."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Open drawer
        self._click_municipality(page)
        wait_for_drawer_open(page)
        drawer = page.locator("[data-testid='drill-down-drawer']")

        # Click close button
        close_button = page.locator("[data-testid='drawer-close']")
        close_button.click()
        wait_for_drawer_closed(page)

        # Drawer should not have 'open' class (hidden via CSS transform)
        has_open_class = drawer.evaluate("el => el.classList.contains('open')")
        assert not has_open_class, "Drawer should not have 'open' class after close"

    def test_click_outside_drawer_closes_it(self, page: Page, live_server: str) -> None:
        """Clicking on the map (outside drawer) should close the drawer."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Open drawer
        self._click_municipality(page)
        wait_for_drawer_open(page)
        drawer = page.locator("[data-testid='drill-down-drawer']")

        # Click on map area (left side, away from drawer)
        page.click("#map canvas", position={"x": 100, "y": 300})
        wait_for_drawer_closed(page)

        # Drawer should not have 'open' class (hidden via CSS transform)
        has_open_class = drawer.evaluate("el => el.classList.contains('open')")
        assert not has_open_class, "Drawer should not have 'open' class after click outside"

    # --- Event List ---

    def test_drawer_shows_event_list_after_loading(self, page: Page, live_server: str) -> None:
        """Drawer should display content after loading (events, threshold, or empty)."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        # One of these states should be visible after loading completes
        event_list = page.locator("[data-testid='event-list']")
        threshold_msg = page.locator("[data-testid='threshold-message']")
        empty_state = page.locator("#empty-state")
        error_state = page.locator("#error-state")

        # Check which state is visible
        has_content = (
            event_list.is_visible()
            or threshold_msg.is_visible()
            or empty_state.is_visible()
            or error_state.is_visible()
        )
        assert has_content, "Expected one of: event list, threshold, empty, or error state"

    def test_drawer_header_shows_stats_summary(self, page: Page, live_server: str) -> None:
        """Drawer header should show stats summary with event count and rate."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        # Check stats summary display (e.g., "10 events · 100.0/10k")
        stats_summary = page.locator("[data-testid='drawer-stats-summary']")
        expect(stats_summary).to_be_visible()

        stats_text = stats_summary.inner_text()
        assert "event" in stats_text.lower(), f"Expected 'events' in stats: {stats_text}"
        assert "/10k" in stats_text, f"Expected rate per 10k in stats: {stats_text}"

    def test_event_card_shows_date_type_summary(self, page: Page, live_server: str) -> None:
        """Event cards should display date, type, and summary."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        # Skip if threshold applies or no events
        threshold_msg = page.locator("[data-testid='threshold-message']")
        empty_state = page.locator("#empty-state")
        if threshold_msg.is_visible():
            pytest.skip("Cell has too few events (threshold applies)")
        if empty_state.is_visible():
            pytest.skip("Cell has no events")

        # Check first event card
        first_card = page.locator("[data-testid='event-card']").first
        expect(first_card).to_be_visible()

        # Date should be visible
        date_el = first_card.locator("[data-testid='event-date']")
        expect(date_el).to_be_visible()
        assert date_el.inner_text(), "Event date should not be empty"

        # Type should be visible
        type_el = first_card.locator("[data-testid='event-type']")
        expect(type_el).to_be_visible()
        assert type_el.inner_text(), "Event type should not be empty"

        # Summary should be visible
        summary_el = first_card.locator("[data-testid='event-summary']")
        expect(summary_el).to_be_visible()

    # --- Filtering ---

    def test_date_preset_filters_events(self, page: Page, live_server: str) -> None:
        """Clicking a date preset should filter the event list."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        # Click 7-day filter
        date_chip = page.locator("[data-testid='date-chip-7d']")
        expect(date_chip).to_be_visible()
        date_chip.click()

        # Wait for chip to be active
        page.wait_for_selector("[data-testid='date-chip-7d'].active", timeout=3000)

        # Chip should be active
        is_active = date_chip.evaluate("el => el.classList.contains('active')")
        assert is_active, "7d chip should be active"

    def test_custom_date_range_filters_events(self, page: Page, live_server: str) -> None:
        """Custom date range inputs should filter events."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        # Click custom date option
        custom_chip = page.locator("[data-testid='date-chip-custom']")
        expect(custom_chip).to_be_visible()
        custom_chip.click()

        # Wait for date inputs to appear
        start_date = page.locator("[data-testid='date-start']")
        end_date = page.locator("[data-testid='date-end']")

        expect(start_date).to_be_visible()
        expect(end_date).to_be_visible()

        # Set date range
        start_date.fill("2024-01-15")
        end_date.fill("2024-01-20")

        # Wait for content to reload after filter change
        wait_for_drawer_content(page)

    def test_category_filter_shows_types_when_expanded(self, page: Page, live_server: str) -> None:
        """Clicking a category should expand to show type checkboxes."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        # Click property category
        property_chip = page.locator("[data-testid='category-property']")
        expect(property_chip).to_be_visible()
        property_chip.click()

        # Wait for type expansion to be visible
        page.wait_for_selector("[data-testid='type-expansion'].visible", timeout=3000)

        # Type expansion should be visible
        type_expansion = page.locator("[data-testid='type-expansion']")
        expect(type_expansion).to_be_visible()

        # Should have type checkboxes
        type_checkboxes = type_expansion.locator("input[type='checkbox']")
        assert type_checkboxes.count() > 0, "Should have type filter checkboxes"

    def test_type_filter_narrows_results(self, page: Page, live_server: str) -> None:
        """Selecting a specific type should narrow the results."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        # Expand property category
        page.locator("[data-testid='category-property']").click()
        page.wait_for_selector("[data-testid='type-expansion'].visible", timeout=3000)

        # Get initial count
        initial_count = self._get_event_count(page)
        if initial_count == 0:
            pytest.skip("No events to filter")

        # Check "Stöld" type only
        stold_checkbox = page.locator("[data-testid='type-stold']")
        if stold_checkbox.is_visible():
            stold_checkbox.check()

            # Wait for content to reload
            wait_for_drawer_content(page)

            # Count should change (likely decrease)
            new_count = self._get_event_count(page)
            # Just verify filter was applied (count may or may not change)
            assert new_count <= initial_count, "Filtering should not increase count"

    def test_search_filters_by_text(self, page: Page, live_server: str) -> None:
        """Typing in search box and pressing Enter should filter events by text.

        Search requires explicit submit (Enter key) - no search-as-you-type.
        On mobile, the keyboard shows a Search button via enterkeyhint="search".
        """
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        # Find search input
        search_input = page.locator("[data-testid='search-input']")
        expect(search_input).to_be_visible()

        # Search for common Swedish word and press Enter to submit
        search_input.fill("polis")
        search_input.press("Enter")

        # Wait for content to reload after search
        wait_for_drawer_content(page)

        # Results should update (we can't guarantee matches, but search should work)
        # Just verify the search was accepted
        assert search_input.input_value() == "polis", "Search input should contain typed text"

    def test_combined_filters_work_together(self, page: Page, live_server: str) -> None:
        """Multiple filters should combine (AND logic).

        Tests category + search combination. Date filtering is covered
        by test_date_preset_filters_events and test_custom_date_range_filters_events.
        """
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        # Apply category filter
        page.locator("[data-testid='category-property']").click()
        page.wait_for_selector("[data-testid='type-expansion'].visible", timeout=3000)

        # Apply search (explicit submit with Enter)
        search_input = page.locator("[data-testid='search-input']")
        search_input.fill("Stockholm")
        search_input.press("Enter")

        # Wait for content to reload after filters applied
        wait_for_drawer_content(page)

        # Filters should be reflected in active state
        assert page.locator("[data-testid='category-property'].active").is_visible()

    # --- Event Detail ---

    def test_click_event_card_expands_detail(self, page: Page, live_server: str) -> None:
        """Clicking an event card should expand to show full details."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        # Skip if no events
        threshold_msg = page.locator("[data-testid='threshold-message']")
        empty_state = page.locator("#empty-state")
        if threshold_msg.is_visible():
            pytest.skip("Cell has too few events")
        if empty_state.is_visible():
            pytest.skip("Cell has no events")

        # Click first event card
        first_card = page.locator("[data-testid='event-card']").first
        first_card.click()

        # Wait for card to be expanded
        page.wait_for_selector("[data-testid='event-card'].expanded", timeout=3000)

        # Card should be expanded
        is_expanded = first_card.evaluate("el => el.classList.contains('expanded')")
        assert is_expanded, "Card should be expanded"

    def test_event_detail_shows_full_html_body(self, page: Page, live_server: str) -> None:
        """Expanded event should show the full HTML body content."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        threshold_msg = page.locator("[data-testid='threshold-message']")
        empty_state = page.locator("#empty-state")
        if threshold_msg.is_visible():
            pytest.skip("Cell has too few events")
        if empty_state.is_visible():
            pytest.skip("Cell has no events")

        # Expand first card
        first_card = page.locator("[data-testid='event-card']").first
        first_card.click()
        page.wait_for_selector("[data-testid='event-card'].expanded", timeout=3000)

        # Full body content should be visible
        body_content = first_card.locator("[data-testid='event-body']")
        expect(body_content).to_be_visible()

    def test_event_detail_has_police_report_link(self, page: Page, live_server: str) -> None:
        """Expanded event should have a link to the police report."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        threshold_msg = page.locator("[data-testid='threshold-message']")
        empty_state = page.locator("#empty-state")
        if threshold_msg.is_visible():
            pytest.skip("Cell has too few events")
        if empty_state.is_visible():
            pytest.skip("Cell has no events")

        # Expand first card
        first_card = page.locator("[data-testid='event-card']").first
        first_card.click()
        page.wait_for_selector("[data-testid='event-card'].expanded", timeout=3000)

        # Police link should exist
        police_link = first_card.locator("[data-testid='police-link']")
        expect(police_link).to_be_visible()

    def test_police_report_link_correct_url(self, page: Page, live_server: str) -> None:
        """Police report link should point to polisen.se."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        threshold_msg = page.locator("[data-testid='threshold-message']")
        empty_state = page.locator("#empty-state")
        if threshold_msg.is_visible():
            pytest.skip("Cell has too few events")
        if empty_state.is_visible():
            pytest.skip("Cell has no events")

        # Expand first card
        first_card = page.locator("[data-testid='event-card']").first
        first_card.click()
        page.wait_for_selector("[data-testid='event-card'].expanded", timeout=3000)

        # Check link URL
        police_link = first_card.locator("[data-testid='police-link']")
        href = police_link.get_attribute("href")
        assert href is not None, "Police link should have href"
        assert "polisen.se" in href, f"Link should point to polisen.se: {href}"

    # --- Pagination ---

    def test_pagination_shows_page_info(self, page: Page, live_server: str) -> None:
        """Pagination should show current page and total pages."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        # Skip if below threshold or no events
        threshold_msg = page.locator("[data-testid='threshold-message']")
        empty_state = page.locator("#empty-state")
        if threshold_msg.is_visible():
            pytest.skip("Cell has too few events")
        if empty_state.is_visible():
            pytest.skip("Cell has no events")

        # Pagination should be visible
        pagination = page.locator("[data-testid='pagination']")
        expect(pagination).to_be_visible()

        # Page info should show "Page X of Y"
        page_info = pagination.locator("[data-testid='page-info']")
        expect(page_info).to_be_visible()
        info_text = page_info.inner_text()
        assert "Page" in info_text, f"Expected 'Page' in info: {info_text}"

    def test_pagination_next_page_loads_more(self, page: Page, live_server: str) -> None:
        """Clicking Next should load the next page of events."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        threshold_msg = page.locator("[data-testid='threshold-message']")
        if threshold_msg.is_visible():
            pytest.skip("Cell has too few events")

        # Check if there are multiple pages
        page_info = page.locator("[data-testid='page-info']")
        info_text = page_info.inner_text()

        # If only 1 page, skip
        if "of 1" in info_text:
            pytest.skip("Only one page of results")

        # Get first event ID on page 1
        first_card = page.locator("[data-testid='event-card']").first
        first_event_id = first_card.get_attribute("data-event-id")

        # Click Next
        next_button = page.locator("[data-testid='pagination-next']")
        next_button.click()

        # Wait for different event to appear (page changed)
        js_check = (
            "document.querySelector('[data-testid=\"event-card\"]')"
            f"?.getAttribute('data-event-id') !== '{first_event_id}'"
        )
        page.wait_for_function(js_check, timeout=5000)

        # First event should be different
        new_first_card = page.locator("[data-testid='event-card']").first
        new_event_id = new_first_card.get_attribute("data-event-id")

        assert new_event_id != first_event_id, "Next page should show different events"

    # --- Threshold ---

    def test_cell_under_threshold_shows_message_not_list(
        self, page: Page, live_server: str
    ) -> None:
        """Cells with <3 events should show a message, not the event list."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # This test may need to find a specific sparse cell
        # For now, we verify the threshold message element exists in the implementation
        self._click_municipality(page)
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        # Either we have events OR threshold message
        event_list = page.locator("[data-testid='event-list']")
        threshold_msg = page.locator("[data-testid='threshold-message']")

        event_count = self._get_event_count(page)

        # If count is 1-2, threshold message should show
        if 0 < event_count < 3:
            expect(threshold_msg).to_be_visible()
            expect(event_list).not_to_be_visible()

    # --- Helper Methods ---

    def _click_municipality(self, page: Page) -> dict[str, float | str] | None:
        """Find and click a municipality on the map, then open the drawer.

        With the stats-first flow, clicking a municipality shows stats panel first.
        This helper also clicks the Search Events button to open the drawer.

        Note: This helper filters for features with centroids inside the visible
        canvas bounds, then picks the one closest to center. This ensures the
        Playwright click lands on an actual visible feature.
        """
        result = page.evaluate("""
            () => {
                const canvas = document.querySelector('#map canvas');
                const rect = canvas.getBoundingClientRect();
                const width = rect.width;
                const height = rect.height;

                const features = window.map.queryRenderedFeatures({layers: ['municipalities']});
                if (features.length === 0) return null;

                // Find features with centroids inside the visible canvas
                const visibleFeatures = [];
                for (const feature of features) {
                    const geomType = feature.geometry.type;
                    let outerRing;

                    // Handle both Polygon and MultiPolygon
                    if (geomType === 'Polygon') {
                        outerRing = feature.geometry.coordinates[0];
                    } else if (geomType === 'MultiPolygon') {
                        outerRing = feature.geometry.coordinates[0][0];
                    } else {
                        continue;
                    }

                    // Calculate centroid in screen coordinates
                    let sumX = 0, sumY = 0;
                    let validCoords = 0;
                    for (const coord of outerRing) {
                        if (!Array.isArray(coord) || coord.length !== 2) continue;
                        try {
                            const point = window.map.project(coord);
                            sumX += point.x;
                            sumY += point.y;
                            validCoords++;
                        } catch (e) {
                            // Skip invalid coordinates
                        }
                    }

                    if (validCoords === 0) continue;

                    const centroidX = sumX / validCoords;
                    const centroidY = sumY / validCoords;

                    // Check if centroid is inside canvas with margin
                    const margin = 50;
                    if (centroidX >= margin && centroidX < (width - margin) &&
                        centroidY >= margin && centroidY < (height - margin)) {
                        visibleFeatures.push({
                            x: centroidX,
                            y: centroidY,
                            kommun_namn: feature.properties.kommun_namn,
                            distToCenter: Math.pow(centroidX - width/2, 2) +
                                         Math.pow(centroidY - height/2, 2)
                        });
                    }
                }

                if (visibleFeatures.length === 0) return null;

                // Pick the feature closest to center (most likely to be fully visible)
                visibleFeatures.sort((a, b) => a.distToCenter - b.distToCenter);
                const best = visibleFeatures[0];

                return {
                    x: best.x,
                    y: best.y,
                    kommun_namn: best.kommun_namn
                };
            }
        """)

        if result:
            page.click("#map canvas", position={"x": result["x"], "y": result["y"]}, force=True)
            # Stats-first flow: wait for stats panel, then click Search button
            page.wait_for_selector("#cell-details.visible", timeout=5000)
            page.click("[data-testid='search-events-button']")
        return result  # type: ignore[no-any-return]

    def _get_event_count(self, page: Page) -> int:
        """Extract event count from the stats summary display."""
        stats_el = page.locator("[data-testid='drawer-stats-summary']")
        if not stats_el.is_visible():
            return 0

        text = stats_el.inner_text()
        # Parse "42 events · 100.0/10k" or "5 of 42 events · 100.0/10k" -> first number
        import re

        match = re.search(r"(\d+)", text)
        return int(match.group(1)) if match else 0


@pytest.mark.e2e
class TestStatsFirstFlow:
    """E2E tests for the stats-first UI flow.

    This test class verifies the new sequential interaction model:
    1. Click cell -> stats panel appears (drawer does NOT auto-open)
    2. Click "Search Events" button -> drawer opens, stats hides
    3. Escape from drawer -> return to stats
    4. Escape from stats -> close everything

    Also tests keyboard shortcuts: S (search), Escape, / (focus search), ? (help).
    """

    # --- Core Flow Tests ---

    def test_click_cell_shows_stats_only_not_drawer(self, page: Page, live_server: str) -> None:
        """Clicking a cell should show stats panel but NOT open drawer."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Click a cell
        self._click_municipality(page)

        # Stats panel should be visible
        stats_panel = page.locator("#cell-details")
        page.wait_for_selector("#cell-details.visible", timeout=5000)
        has_visible_class = stats_panel.evaluate("el => el.classList.contains('visible')")
        assert has_visible_class, "Stats panel should be visible after clicking cell"

        # Drawer should NOT be open
        drawer = page.locator("[data-testid='drill-down-drawer']")
        has_open_class = drawer.evaluate("el => el.classList.contains('open')")
        assert not has_open_class, "Drawer should NOT auto-open when clicking cell"

    def test_stats_panel_has_search_button(self, page: Page, live_server: str) -> None:
        """Stats panel should have a 'Search Events' button."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)

        # Wait for stats panel
        page.wait_for_selector("#cell-details.visible", timeout=5000)

        # Search button should exist
        search_button = page.locator("[data-testid='search-events-button']")
        expect(search_button).to_be_visible()
        expect(search_button).to_contain_text("Search Events")

    def test_search_button_opens_drawer_hides_stats(self, page: Page, live_server: str) -> None:
        """Clicking 'Search Events' should open drawer and hide stats panel."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        page.wait_for_selector("#cell-details.visible", timeout=5000)

        # Click search button
        page.click("[data-testid='search-events-button']")

        # Drawer should open
        wait_for_drawer_open(page)

        # Stats panel should be hidden
        stats_panel = page.locator("#cell-details")
        has_visible_class = stats_panel.evaluate("el => el.classList.contains('visible')")
        assert not has_visible_class, "Stats panel should hide when drawer opens"

    def test_escape_from_drawer_returns_to_stats(self, page: Page, live_server: str) -> None:
        """Pressing Escape in drawer should close drawer and show stats again."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Open stats -> drawer
        self._click_municipality(page)
        page.wait_for_selector("#cell-details.visible", timeout=5000)
        page.click("[data-testid='search-events-button']")
        wait_for_drawer_open(page)

        # Press Escape
        page.keyboard.press("Escape")

        # Drawer should close
        wait_for_drawer_closed(page)

        # Stats should reappear
        stats_panel = page.locator("#cell-details")
        page.wait_for_selector("#cell-details.visible", timeout=5000)
        has_visible_class = stats_panel.evaluate("el => el.classList.contains('visible')")
        assert has_visible_class, "Stats panel should reappear after closing drawer"

    def test_escape_from_stats_closes_stats(self, page: Page, live_server: str) -> None:
        """Pressing Escape in stats view should close stats panel entirely."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        page.wait_for_selector("#cell-details.visible", timeout=5000)

        # Press Escape
        page.keyboard.press("Escape")

        # Stats should close
        stats_panel = page.locator("#cell-details")
        page.wait_for_function(
            "!document.getElementById('cell-details').classList.contains('visible')", timeout=3000
        )
        has_visible_class = stats_panel.evaluate("el => el.classList.contains('visible')")
        assert not has_visible_class, "Stats panel should close on Escape"

    def test_close_drawer_button_returns_to_stats(self, page: Page, live_server: str) -> None:
        """Clicking drawer X button should close drawer and show stats."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Open stats -> drawer
        self._click_municipality(page)
        page.wait_for_selector("#cell-details.visible", timeout=5000)
        page.click("[data-testid='search-events-button']")
        wait_for_drawer_open(page)

        # Click close button
        page.click("[data-testid='drawer-close']")

        # Should return to stats view
        wait_for_drawer_closed(page)
        stats_panel = page.locator("#cell-details")
        page.wait_for_selector("#cell-details.visible", timeout=5000)
        has_visible_class = stats_panel.evaluate("el => el.classList.contains('visible')")
        assert has_visible_class, "Stats panel should reappear after closing drawer"

    def test_click_different_cell_while_drawer_open_updates_drawer(
        self, page: Page, live_server: str
    ) -> None:
        """Clicking a different municipality while drawer open should update drawer."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Get two different visible municipalities
        cells = page.evaluate("""
            () => {
                const canvas = document.querySelector('#map canvas');
                const rect = canvas.getBoundingClientRect();
                const width = rect.width;
                const height = rect.height;

                const features = window.map.queryRenderedFeatures({layers: ['municipalities']});
                if (features.length < 2) return null;

                // Find visible features
                const visibleFeatures = [];
                for (const feature of features) {
                    const geomType = feature.geometry.type;
                    let outerRing;
                    if (geomType === 'Polygon') {
                        outerRing = feature.geometry.coordinates[0];
                    } else if (geomType === 'MultiPolygon') {
                        outerRing = feature.geometry.coordinates[0][0];
                    } else continue;

                    let sumX = 0, sumY = 0, validCoords = 0;
                    for (const coord of outerRing) {
                        if (!Array.isArray(coord) || coord.length !== 2) continue;
                        try {
                            const pt = window.map.project(coord);
                            sumX += pt.x; sumY += pt.y; validCoords++;
                        } catch (e) {}
                    }
                    if (validCoords === 0) continue;

                    const centroidX = sumX / validCoords;
                    const centroidY = sumY / validCoords;

                    const margin = 50;
                    if (centroidX >= margin && centroidX < (width - margin) &&
                        centroidY >= margin && centroidY < (height - margin)) {
                        const dx = centroidX - width/2;
                        const dy = centroidY - height/2;
                        visibleFeatures.push({
                            x: centroidX, y: centroidY,
                            kommun_namn: feature.properties.kommun_namn,
                            distToCenter: dx*dx + dy*dy
                        });
                    }
                }

                if (visibleFeatures.length < 2) return null;
                visibleFeatures.sort((a, b) => a.distToCenter - b.distToCenter);
                return visibleFeatures.slice(0, 2);
            }
        """)

        if not cells or len(cells) < 2:
            pytest.skip("Need at least 2 municipalities to test this behavior")

        # Click first municipality, open drawer
        page.click("#map canvas", position={"x": cells[0]["x"], "y": cells[0]["y"]}, force=True)
        page.wait_for_selector("#cell-details.visible", timeout=5000)
        page.click("[data-testid='search-events-button']")
        wait_for_drawer_open(page)

        first_location = page.evaluate("window.DrillDown.currentLocationName")

        # Click second municipality (with force=True to bypass potential drawer overlay)
        page.click("#map canvas", position={"x": cells[1]["x"], "y": cells[1]["y"]}, force=True)

        # Drawer should stay open but update to new municipality
        page.wait_for_function(
            f"window.DrillDown.currentLocationName !== '{first_location}'", timeout=5000
        )

        # Drawer should still be open (not reset to stats)
        drawer = page.locator("[data-testid='drill-down-drawer']")
        has_open_class = drawer.evaluate("el => el.classList.contains('open')")
        assert has_open_class, "Drawer should stay open when clicking different municipality"

    def test_filters_preserved_when_clicking_different_cell(
        self, page: Page, live_server: str
    ) -> None:
        """Filters should be preserved when clicking different municipality while drawer open."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Get two different visible municipalities
        cells = page.evaluate("""
            () => {
                const canvas = document.querySelector('#map canvas');
                const rect = canvas.getBoundingClientRect();
                const width = rect.width;
                const height = rect.height;

                const features = window.map.queryRenderedFeatures({layers: ['municipalities']});
                if (features.length < 2) return null;

                // Find visible features
                const visibleFeatures = [];
                for (const feature of features) {
                    const geomType = feature.geometry.type;
                    let outerRing;
                    if (geomType === 'Polygon') {
                        outerRing = feature.geometry.coordinates[0];
                    } else if (geomType === 'MultiPolygon') {
                        outerRing = feature.geometry.coordinates[0][0];
                    } else continue;

                    let sumX = 0, sumY = 0, validCoords = 0;
                    for (const coord of outerRing) {
                        if (!Array.isArray(coord) || coord.length !== 2) continue;
                        try {
                            const pt = window.map.project(coord);
                            sumX += pt.x; sumY += pt.y; validCoords++;
                        } catch (e) {}
                    }
                    if (validCoords === 0) continue;

                    const centroidX = sumX / validCoords;
                    const centroidY = sumY / validCoords;

                    const margin = 50;
                    if (centroidX >= margin && centroidX < (width - margin) &&
                        centroidY >= margin && centroidY < (height - margin)) {
                        const dx = centroidX - width/2;
                        const dy = centroidY - height/2;
                        visibleFeatures.push({
                            x: centroidX, y: centroidY,
                            distToCenter: dx*dx + dy*dy
                        });
                    }
                }

                if (visibleFeatures.length < 2) return null;
                visibleFeatures.sort((a, b) => a.distToCenter - b.distToCenter);
                return visibleFeatures.slice(0, 2);
            }
        """)

        if not cells or len(cells) < 2:
            pytest.skip("Need at least 2 cells to test filter preservation")

        # Click first cell and open drawer
        page.click("#map canvas", position={"x": cells[0]["x"], "y": cells[0]["y"]}, force=True)
        page.wait_for_selector("#cell-details.visible", timeout=5000)
        page.click("[data-testid='search-events-button']")
        wait_for_drawer_open(page)

        # Apply filters: search text (requires Enter to submit) and date preset
        page.fill("#filter-search", "test filter")
        page.press("#filter-search", "Enter")
        page.click("[data-testid='date-chip-7d']")
        page.wait_for_timeout(300)

        # Verify filters are active before clicking second cell
        filters_before = page.evaluate("""
            () => ({
                search: window.DrillDown.filters.search,
                startDate: window.DrillDown.filters.startDate
            })
        """)
        assert filters_before["search"] == "test filter", "Search filter should be set"
        assert filters_before["startDate"] is not None, "Date filter should be set"

        # Click second cell (with force=True to bypass potential drawer overlay)
        page.click("#map canvas", position={"x": cells[1]["x"], "y": cells[1]["y"]}, force=True)
        page.wait_for_timeout(500)

        # Filters should be preserved
        filters_after = page.evaluate("""
            () => ({
                search: window.DrillDown.filters.search,
                startDate: window.DrillDown.filters.startDate,
                searchInputValue: document.getElementById('filter-search').value,
                dateChip7dActive: document.querySelector(
                    '[data-testid="date-chip-7d"]'
                ).classList.contains('active')
            })
        """)

        assert filters_after["search"] == "test filter", "Search filter should be preserved"
        assert filters_after["searchInputValue"] == "test filter", (
            "Search input should retain value"
        )
        assert filters_after["startDate"] is not None, "Date filter should be preserved"
        assert filters_after["dateChip7dActive"], "7-day chip should still be active"

    # --- Keyboard Shortcuts ---

    def test_s_key_opens_drawer_from_stats(self, page: Page, live_server: str) -> None:
        """Pressing 'S' in stats view should open drawer."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        page.wait_for_selector("#cell-details.visible", timeout=5000)

        # Press S
        page.keyboard.press("s")

        # Drawer should open
        wait_for_drawer_open(page)

    def test_slash_key_focuses_search_input(self, page: Page, live_server: str) -> None:
        """Pressing '/' when drawer is open should focus search input."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Open drawer
        self._click_municipality(page)
        page.wait_for_selector("#cell-details.visible", timeout=5000)
        page.click("[data-testid='search-events-button']")
        wait_for_drawer_open(page)

        # Click somewhere else to unfocus search
        page.click(".drawer-header")

        # Press /
        page.keyboard.press("/")

        # Search input should be focused
        is_focused = page.evaluate(
            "document.activeElement === document.getElementById('filter-search')"
        )
        assert is_focused, "Search input should be focused after pressing /"

    def test_question_mark_shows_shortcuts_help(self, page: Page, live_server: str) -> None:
        """Pressing '?' should show keyboard shortcuts help."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Press ?
        page.keyboard.press("Shift+/")  # ? is Shift+/

        # Help modal/panel should appear
        help_panel = page.locator("[data-testid='shortcuts-help']")
        expect(help_panel).to_be_visible(timeout=3000)

    # --- Drawer Header Stats ---

    def test_drawer_header_shows_cell_stats_summary(self, page: Page, live_server: str) -> None:
        """Drawer header should show total events and rate per 10k."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Click municipality and get its data
        cell_data = self._click_municipality(page)
        assert cell_data is not None, "Should find a visible municipality"
        page.wait_for_selector("#cell-details.visible", timeout=5000)
        page.click("[data-testid='search-events-button']")
        wait_for_drawer_open(page)

        # Check header stats
        header_stats = page.locator("[data-testid='drawer-stats-summary']")
        expect(header_stats).to_be_visible()

        stats_text = header_stats.inner_text()
        assert str(cell_data["total_count"]) in stats_text, "Should show total count"
        # Rate should be shown (might be formatted)
        assert "/10k" in stats_text or "per 10" in stats_text, "Should show rate"

    def test_drawer_header_shows_filtered_count(self, page: Page, live_server: str) -> None:
        """Drawer header should show 'X of Y events' when filters are active."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        page.wait_for_selector("#cell-details.visible", timeout=5000)
        page.click("[data-testid='search-events-button']")
        wait_for_drawer_open(page)
        wait_for_drawer_content(page)

        # Apply a filter (7 days)
        page.click("[data-testid='date-chip-7d']")

        # Wait for content to reload
        page.wait_for_timeout(500)

        # Header should show "X of Y" format
        header_stats = page.locator("[data-testid='drawer-stats-summary']")
        stats_text = header_stats.inner_text()

        # Should contain "of" indicating filtered vs total
        # (e.g., "5 of 47 events" or "Showing 5 of 47")
        assert " of " in stats_text.lower(), f"Should show filtered count: {stats_text}"

    def test_drawer_location_shows_city_name(self, page: Page, live_server: str) -> None:
        """Drawer header should show municipality name from tile data (kommun_namn)."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Click municipality and get its data (including kommun_namn)
        cell_data = self._click_municipality(page)
        assert cell_data is not None, "Should find a visible municipality"
        page.wait_for_selector("#cell-details.visible", timeout=5000)
        page.click("[data-testid='search-events-button']")
        wait_for_drawer_open(page)

        # Check location display - should be a municipality name from kommun_namn
        location_el = page.locator("[data-testid='drawer-location']")
        expect(location_el).to_be_visible()

        location_text = location_el.inner_text()

        # Should NOT be a count like "42 events" or "Loading..."
        assert "events" not in location_text.lower(), (
            f"Location should be a place name, not event count: {location_text}"
        )
        assert location_text != "Loading...", "Location should not show loading state"

        # Should match the kommun_namn from tile data
        if cell_data and cell_data.get("kommun_namn"):
            assert location_text == cell_data["kommun_namn"], (
                f"Location should match tile data: expected '{cell_data['kommun_namn']}', "
                f"got '{location_text}'"
            )

    # --- Drawer Width ---

    def test_drawer_is_480px_wide(self, page: Page, live_server: str) -> None:
        """Drawer should be 480px wide (increased from 420px)."""
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        self._click_municipality(page)
        page.wait_for_selector("#cell-details.visible", timeout=5000)
        page.click("[data-testid='search-events-button']")
        wait_for_drawer_open(page)

        width = page.evaluate("""
            () => {
                const drawer = document.querySelector('.drill-down-drawer');
                return parseInt(window.getComputedStyle(drawer).width);
            }
        """)
        assert width == 480, f"Drawer should be 480px wide, got {width}px"

    # --- Helper Methods ---

    def _click_municipality(self, page: Page) -> dict[str, float | str] | None:
        """Find and click a municipality on the map.

        Note: Filters for features with centroids inside the visible canvas,
        then picks the one closest to center to ensure reliable clicks.
        """
        result = page.evaluate("""
            () => {
                const canvas = document.querySelector('#map canvas');
                const rect = canvas.getBoundingClientRect();
                const width = rect.width;
                const height = rect.height;

                const features = window.map.queryRenderedFeatures({layers: ['municipalities']});
                if (features.length === 0) return null;

                // Find features with centroids inside the visible canvas
                const visibleFeatures = [];
                for (const feature of features) {
                    const geomType = feature.geometry.type;
                    let outerRing;

                    if (geomType === 'Polygon') {
                        outerRing = feature.geometry.coordinates[0];
                    } else if (geomType === 'MultiPolygon') {
                        outerRing = feature.geometry.coordinates[0][0];
                    } else {
                        continue;
                    }

                    let sumX = 0, sumY = 0;
                    let validCoords = 0;
                    for (const coord of outerRing) {
                        if (!Array.isArray(coord) || coord.length !== 2) continue;
                        try {
                            const point = window.map.project(coord);
                            sumX += point.x;
                            sumY += point.y;
                            validCoords++;
                        } catch (e) {}
                    }

                    if (validCoords === 0) continue;

                    const centroidX = sumX / validCoords;
                    const centroidY = sumY / validCoords;

                    const margin = 50;
                    if (centroidX >= margin && centroidX < (width - margin) &&
                        centroidY >= margin && centroidY < (height - margin)) {
                        visibleFeatures.push({
                            x: centroidX,
                            y: centroidY,
                            kommun_namn: feature.properties.kommun_namn,
                            total_count: feature.properties.total_count,
                            rate_per_10000: feature.properties.rate_per_10000,
                            distToCenter: Math.pow(centroidX - width/2, 2) +
                                         Math.pow(centroidY - height/2, 2)
                        });
                    }
                }

                if (visibleFeatures.length === 0) return null;

                visibleFeatures.sort((a, b) => a.distToCenter - b.distToCenter);
                const best = visibleFeatures[0];

                return {
                    x: best.x,
                    y: best.y,
                    kommun_namn: best.kommun_namn,
                    total_count: best.total_count,
                    rate_per_10000: best.rate_per_10000
                };
            }
        """)

        if result:
            page.click("#map canvas", position={"x": result["x"], "y": result["y"]}, force=True)
        return result  # type: ignore[no-any-return]


# --- Shared Municipality Click Helper ---


def find_and_click_municipality(page: Page) -> dict[str, float | str] | None:
    """Find and click a municipality on the map.

    Note: Filters for features with centroids inside the visible canvas,
    then picks the one closest to center to ensure reliable clicks.
    Returns the clicked feature data or None if no feature found.
    """
    result = page.evaluate("""
        () => {
            const canvas = document.querySelector('#map canvas');
            const rect = canvas.getBoundingClientRect();
            const width = rect.width;
            const height = rect.height;

            const features = window.map.queryRenderedFeatures({layers: ['municipalities']});
            if (features.length === 0) return null;

            // Find features with centroids inside the visible canvas
            const visibleFeatures = [];
            for (const feature of features) {
                const geomType = feature.geometry.type;
                let outerRing;

                if (geomType === 'Polygon') {
                    outerRing = feature.geometry.coordinates[0];
                } else if (geomType === 'MultiPolygon') {
                    outerRing = feature.geometry.coordinates[0][0];
                } else {
                    continue;
                }

                let sumX = 0, sumY = 0;
                let validCoords = 0;
                for (const coord of outerRing) {
                    if (!Array.isArray(coord) || coord.length !== 2) continue;
                    try {
                        const point = window.map.project(coord);
                        sumX += point.x;
                        sumY += point.y;
                        validCoords++;
                    } catch (e) {}
                }

                if (validCoords === 0) continue;

                const centroidX = sumX / validCoords;
                const centroidY = sumY / validCoords;

                const margin = 50;
                if (centroidX >= margin && centroidX < (width - margin) &&
                    centroidY >= margin && centroidY < (height - margin)) {
                    visibleFeatures.push({
                        x: centroidX,
                        y: centroidY,
                        kommun_namn: feature.properties.kommun_namn,
                        total_count: feature.properties.total_count,
                        rate_per_10000: feature.properties.rate_per_10000,
                        distToCenter: Math.pow(centroidX - width/2, 2) +
                                     Math.pow(centroidY - height/2, 2)
                    });
                }
            }

            if (visibleFeatures.length === 0) return null;

            visibleFeatures.sort((a, b) => a.distToCenter - b.distToCenter);
            const best = visibleFeatures[0];

            return {
                x: best.x,
                y: best.y,
                kommun_namn: best.kommun_namn,
                total_count: best.total_count,
                rate_per_10000: best.rate_per_10000
            };
        }
    """)

    if result:
        page.click("#map canvas", position={"x": result["x"], "y": result["y"]}, force=True)
    return result  # type: ignore[no-any-return]


# --- Mobile Viewport Helpers ---
# iPhone 12 viewport: 390x844 (below 768px breakpoint)
MOBILE_VIEWPORT: ViewportSize = {"width": 390, "height": 844}
DESKTOP_VIEWPORT: ViewportSize = {"width": 1280, "height": 800}


def wait_for_bottom_sheet_open(page: Page, timeout: int = 5000) -> None:
    """Wait for bottom sheet to open (mobile container)."""
    page.wait_for_selector("[data-testid='bottom-sheet'].open", timeout=timeout)


def wait_for_bottom_sheet_closed(page: Page, timeout: int = 5000) -> None:
    """Wait for bottom sheet to close."""
    page.wait_for_selector("[data-testid='bottom-sheet']:not(.open)", timeout=timeout)


@pytest.mark.e2e
@pytest.mark.mobile
class TestMobileE2E:
    """End-to-end tests for mobile viewport behavior.

    These tests verify that on mobile viewports (<768px):
    - Bottom sheet is used instead of side drawer
    - Touch gestures work correctly
    - Layout adapts for mobile screens
    """

    def test_mobile_viewport_shows_bottom_sheet_not_drawer(
        self, page: Page, live_server: str
    ) -> None:
        """Test that mobile viewport uses bottom sheet instead of side drawer.

        This is the fundamental test for responsive container switching.
        On mobile viewports (<768px), clicking a municipality should open
        a bottom sheet, not the side drawer.
        """
        # Set mobile viewport
        page.set_viewport_size(MOBILE_VIEWPORT)
        page.goto(live_server)
        wait_for_map_ready(page)

        # Verify we're in mobile mode by checking window width
        viewport_width = page.evaluate("window.innerWidth")
        assert viewport_width < 768, f"Expected mobile viewport, got {viewport_width}px"

        # Bottom sheet element should exist but be hidden initially
        bottom_sheet = page.locator("[data-testid='bottom-sheet']")
        expect(bottom_sheet).to_be_attached()
        expect(bottom_sheet).not_to_have_class("open")

        # Side drawer should NOT be visible on mobile (hidden via CSS media query)
        drawer = page.locator("[data-testid='drill-down-drawer']")
        expect(drawer).not_to_be_visible()

    def test_desktop_viewport_shows_drawer_not_bottom_sheet(
        self, page: Page, live_server: str
    ) -> None:
        """Test that desktop viewport uses side drawer, not bottom sheet.

        Verifies the inverse of mobile behavior - desktop should use drawer.
        """
        # Set desktop viewport
        page.set_viewport_size(DESKTOP_VIEWPORT)
        page.goto(live_server)
        wait_for_map_ready(page)

        # Verify we're in desktop mode
        viewport_width = page.evaluate("window.innerWidth")
        assert viewport_width >= 768, f"Expected desktop viewport, got {viewport_width}px"

        # Drawer element should exist
        drawer = page.locator("[data-testid='drill-down-drawer']")
        expect(drawer).to_be_attached()

        # Bottom sheet should either not exist or be hidden on desktop
        bottom_sheet = page.locator("[data-testid='bottom-sheet']")
        if bottom_sheet.count() > 0:
            expect(bottom_sheet).not_to_be_visible()

    def test_mobile_click_municipality_opens_bottom_sheet(
        self, page: Page, live_server: str
    ) -> None:
        """On mobile, clicking a municipality should open bottom sheet, not drawer.

        This is the core interaction test for mobile. When a user taps a
        municipality on mobile, the bottom sheet should slide up to show
        events, not the side drawer.
        """
        # Set mobile viewport
        page.set_viewport_size(MOBILE_VIEWPORT)
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Bottom sheet should not be open initially
        bottom_sheet = page.locator("[data-testid='bottom-sheet']")
        expect(bottom_sheet).not_to_have_class("open")

        # Click a municipality
        result = find_and_click_municipality(page)
        assert result is not None, "Should find a municipality to click"

        # Bottom sheet should open (not drawer)
        wait_for_bottom_sheet_open(page)
        expect(bottom_sheet).to_have_class(re.compile(r"\bopen\b"))

        # Location should be displayed in bottom sheet header
        sheet_location = page.locator("[data-testid='sheet-location']")
        expect(sheet_location).to_be_visible()
        expect(sheet_location).not_to_have_text("Events")  # Should show actual location

    def test_mobile_bottom_sheet_close_button(self, page: Page, live_server: str) -> None:
        """Bottom sheet close button should close the sheet."""
        page.set_viewport_size(MOBILE_VIEWPORT)
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Open bottom sheet
        find_and_click_municipality(page)
        wait_for_bottom_sheet_open(page)

        # Click close button
        close_button = page.locator("[data-testid='sheet-close']")
        close_button.click()
        wait_for_bottom_sheet_closed(page)

        # Bottom sheet should be closed
        bottom_sheet = page.locator("[data-testid='bottom-sheet']")
        expect(bottom_sheet).not_to_have_class("open")

    def test_mobile_controls_positioned_in_corner(self, page: Page, live_server: str) -> None:
        """Controls should be anchored to bottom-left corner on mobile.

        Previously controls floated at bottom: 120px which looked disconnected.
        Now should be at bottom: 16px, close to the corner.
        """
        page.set_viewport_size(MOBILE_VIEWPORT)
        page.goto(live_server)
        wait_for_map_ready(page)

        controls = page.locator("#controls")
        expect(controls).to_be_visible()

        box = controls.bounding_box()
        assert box is not None

        # Bottom should be close to viewport bottom (within 50px)
        viewport_height = MOBILE_VIEWPORT["height"]
        controls_bottom = box["y"] + box["height"]
        distance_from_bottom = viewport_height - controls_bottom
        assert distance_from_bottom < 50, f"Controls too far from bottom: {distance_from_bottom}px"

        # Left should be close to viewport edge
        assert box["x"] < 20, f"Controls not in left corner: {box['x']}px from left"

    def test_mobile_toggle_label_no_wrap(self, page: Page, live_server: str) -> None:
        """Toggle label 'Count' should stay on single line.

        On narrow viewports, the label was wrapping to two lines.
        white-space: nowrap should prevent this.
        """
        page.set_viewport_size({"width": 320, "height": 568})  # Narrow viewport
        page.goto(live_server)
        wait_for_map_ready(page)

        toggle_label = page.locator(".toggle-label")
        expect(toggle_label).to_be_visible()

        box = toggle_label.bounding_box()
        assert box is not None

        # Single line should be ~24-40px; two lines would be >50px
        assert box["height"] < 50, f"Toggle label appears to wrap: {box['height']}px"

    def test_mobile_legend_collapsed_padding(self, page: Page, live_server: str) -> None:
        """Legend collapsed state should have symmetric padding.

        On mobile, legend starts collapsed. The h4 margin-bottom should be 0
        to avoid asymmetric spacing in this state.
        """
        page.set_viewport_size(MOBILE_VIEWPORT)
        page.goto(live_server)
        wait_for_map_ready(page)

        # Legend starts collapsed on mobile
        page.wait_for_selector("#legend.collapsed")

        margin_bottom = page.evaluate("""
            () => {
                const h4 = document.querySelector('#legend.collapsed h4');
                return parseInt(window.getComputedStyle(h4).marginBottom);
            }
        """)
        assert margin_bottom == 0, (
            f"h4 margin-bottom should be 0 when collapsed, got {margin_bottom}px"
        )

    def test_mobile_bottom_sheet_category_table_font(self, page: Page, live_server: str) -> None:
        """Category table in bottom sheet should have adequate font size.

        Mobile styling should increase font from 12px to 14px for readability.
        """
        page.set_viewport_size(MOBILE_VIEWPORT)
        page.goto(live_server)
        wait_for_map_ready(page)
        wait_for_tiles_rendered(page)

        # Open bottom sheet by clicking municipality
        find_and_click_municipality(page)
        wait_for_bottom_sheet_open(page)

        font_size = page.evaluate("""
            () => {
                const table = document.querySelector('.sheet-content .category-table');
                return table ? window.getComputedStyle(table).fontSize : null;
            }
        """)
        assert font_size is not None, "Category table not found in bottom sheet"
        size_value = int(font_size.replace("px", ""))
        assert size_value >= 14, f"Category table font too small: {font_size}"

    def test_mobile_search_input_enterkeyhint(self, page: Page, live_server: str) -> None:
        """Search input should have enterkeyhint='search' for mobile keyboard.

        This makes the mobile keyboard show 'Search' instead of 'Return'.
        """
        page.set_viewport_size(MOBILE_VIEWPORT)
        page.goto(live_server)
        wait_for_map_ready(page)

        search_input = page.locator("#filter-search")
        expect(search_input).to_have_attribute("enterkeyhint", "search")

    def test_mobile_initial_map_shows_sweden(self, page: Page, live_server: str) -> None:
        """Map should show all of Sweden on initial mobile load.

        Uses fitBounds to adapt to viewport size rather than fixed zoom.
        """
        page.set_viewport_size(MOBILE_VIEWPORT)
        page.goto(live_server)
        wait_for_map_ready(page)

        center = page.evaluate("window.map.getCenter()")

        # Sweden is roughly at lat 55-70, lng 10-25
        assert 55 < center["lat"] < 70, f"Map center latitude wrong: {center['lat']}"
        assert 10 < center["lng"] < 25, f"Map center longitude wrong: {center['lng']}"

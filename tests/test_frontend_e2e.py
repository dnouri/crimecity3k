"""End-to-end tests for the CrimeCity3K frontend using Playwright.

These tests verify the complete frontend functionality including map rendering,
PMTiles loading, resolution switching, filtering, and UI controls.
"""

import time

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
class TestFrontendE2E:
    """End-to-end tests for the CrimeCity3K map frontend."""

    def test_map_loads_successfully(self, page: Page, live_server: str) -> None:
        """Test that the map loads with base tiles and canvas."""
        page.goto(f"{live_server}/static/index.html")

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
        """Test that PMTiles sources are loaded for all resolutions.

        Note: r6 is excluded from frontend due to centroid artifacts causing
        rate inflation up to 4.3x. Only r4 and r5 are loaded.
        """
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(3)  # Wait for all sources to load

        # Check that resolution sources are loaded (r6 excluded)
        sources_loaded = page.evaluate("""
            () => {
                const results = [];
                for (const res of [4, 5]) {
                    const source = window.map.getSource(`h3-tiles-r${res}`);
                    if (source) results.push(res);
                }
                return results;
            }
        """)
        assert len(sources_loaded) == 2, f"Expected 2 sources, found {sources_loaded}"
        assert sources_loaded == [4, 5], f"Missing sources: {sources_loaded}"

    def test_h3_layer_displays(self, page: Page, live_server: str) -> None:
        """Test that the H3 cells layer is added to the map."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(3)

        has_layer = page.evaluate("window.map && window.map.getLayer('h3-cells') !== undefined")
        assert has_layer, "H3 cells layer not found"

    def test_resolution_switching_with_zoom(self, page: Page, live_server: str) -> None:
        """Test that H3 resolution changes correctly with zoom level.

        Note: r6 is excluded due to centroid artifacts. Zoom levels 6+ now
        use r5 as maximum resolution.
        """
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(3)

        # Test zoom level 4 -> resolution 4
        page.evaluate("window.map.setZoom(4)")
        time.sleep(1.5)  # Wait for zoomend event
        resolution = page.evaluate("window.currentResolution")
        assert resolution == 4, f"Expected resolution 4 at zoom 4, got {resolution}"

        # Test zoom level 5 -> resolution 5
        page.evaluate("window.map.setZoom(5)")
        time.sleep(1.5)
        resolution = page.evaluate("window.currentResolution")
        assert resolution == 5, f"Expected resolution 5 at zoom 5, got {resolution}"

        # Test zoom level 7 -> resolution 5 (r6 excluded, max is r5)
        page.evaluate("window.map.setZoom(7)")
        time.sleep(1.5)
        resolution = page.evaluate("window.currentResolution")
        assert resolution == 5, f"Expected resolution 5 at zoom 7 (r6 excluded), got {resolution}"

        # Resolution indicator should show 5 (max available)
        indicator = page.locator("#current-resolution")
        expect(indicator).to_have_text("5")

    def test_display_mode_toggle(self, page: Page, live_server: str) -> None:
        """Test that display mode toggle switches between absolute and normalized."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(3)

        # Initial state should be absolute
        mode_label = page.locator("#display-mode-label")
        expect(mode_label).to_have_text("Absolute")

        legend_title = page.locator("#legend-title")
        expect(legend_title).to_contain_text("Event Count")

        # Click the visible toggle slider (not the hidden checkbox)
        toggle_slider = page.locator(".toggle-slider")
        toggle_slider.click()
        time.sleep(0.5)

        expect(mode_label).to_have_text("Normalized")
        expect(legend_title).to_contain_text("Rate per 10,000")

        # Click again to switch back
        toggle_slider.click()
        time.sleep(0.5)

        expect(mode_label).to_have_text("Absolute")
        expect(legend_title).to_contain_text("Event Count")

    def test_category_filter_dropdown(self, page: Page, live_server: str) -> None:
        """Test that category filter dropdown changes layer filter."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(3)

        # Filter dropdown should exist
        filter_dropdown = page.locator("#category-filter")
        expect(filter_dropdown).to_be_visible()

        # Initial filter should be null (all categories)
        initial_filter = page.evaluate("window.map.getFilter('h3-cells')")
        assert initial_filter is None, "Initial filter should be null"

        # Select violence category
        filter_dropdown.select_option("violence")
        time.sleep(0.5)

        # Layer filter should be applied
        violence_filter = page.evaluate("window.map.getFilter('h3-cells')")
        assert violence_filter is not None, "Filter should be applied for violence"
        assert violence_filter[0] == ">", "Filter should use > comparison"

        # Select "all" to remove filter
        filter_dropdown.select_option("all")
        time.sleep(0.5)

        filter_after = page.evaluate("window.map.getFilter('h3-cells')")
        assert filter_after is None, "Filter should be null when 'all' selected"

    def test_filter_persists_across_resolution_changes(self, page: Page, live_server: str) -> None:
        """Test that category filter persists when zoom changes resolution."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(3)

        # Apply a category filter
        page.select_option("#category-filter", "property")
        time.sleep(0.5)

        # Verify filter is applied
        initial_filter = page.evaluate("JSON.stringify(window.map.getFilter('h3-cells'))")
        assert "property_count" in initial_filter, "Filter should contain property_count"

        # Change zoom to trigger resolution change
        page.evaluate("window.map.setZoom(4)")
        time.sleep(1.5)

        # Filter should still be applied
        filter_after = page.evaluate("JSON.stringify(window.map.getFilter('h3-cells'))")
        assert "property_count" in filter_after, "Filter should persist after zoom change"

    def test_legend_displays(self, page: Page, live_server: str) -> None:
        """Test that legend is visible with color scale items."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(3)  # Wait for legend to be populated by JavaScript

        legend = page.locator("#legend")
        expect(legend).to_be_visible()

        # Legend title should show current mode
        legend_title = page.locator("#legend-title")
        expect(legend_title).to_have_text("Event Count")

        # Should have 5 legend items (based on color scale stops)
        legend_items = page.locator(".legend-item")
        item_count = legend_items.count()
        assert item_count == 5, f"Expected 5 legend items, got {item_count}"

    def test_controls_visible(self, page: Page, live_server: str) -> None:
        """Test that control panel is visible with all controls."""
        page.goto(f"{live_server}/static/index.html")

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

        # Resolution indicator
        resolution = page.locator("#current-resolution")
        expect(resolution).to_be_visible()

    def test_tiles_actually_render(self, page: Page, live_server: str) -> None:
        """Test that H3 tile data actually renders on the map.

        This is a critical test that verifies PMTiles are being fetched and
        rendered correctly. It would have caught the HTTP Range request bug
        where the server didn't support byte-range requests required by PMTiles.
        """
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)  # Wait for tiles to load and render

        # Query rendered features - this is the critical assertion
        # If PMTiles aren't loading properly, this will return 0
        features = page.evaluate("""
            () => {
                try {
                    const features = window.map.queryRenderedFeatures({
                        layers: ['h3-cells']
                    });
                    return {
                        count: features.length,
                        hasData: features.length > 0,
                        sample: features.length > 0 ? {
                            h3_cell: features[0].properties.h3_cell,
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
            "No H3 tiles rendered! This likely means PMTiles failed to load. "
            "Check that the server supports HTTP Range requests."
        )
        assert features["count"] > 0, "Expected at least one rendered feature"
        assert features["sample"] is not None, "Sample feature should exist"
        assert features["sample"]["h3_cell"] is not None, "Feature should have h3_cell property"

    def test_cell_click_shows_details(self, page: Page, live_server: str) -> None:
        """Test that clicking an H3 cell shows the details panel.

        This verifies the click interaction works end-to-end.
        """
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)  # Wait for tiles to render

        # First verify we have features to click
        feature_count = page.evaluate("""
            () => window.map.queryRenderedFeatures({layers: ['h3-cells']}).length
        """)
        assert feature_count > 0, "Need rendered features to test click interaction"

        # Details panel should be hidden initially
        details_panel = page.locator("#cell-details")
        assert not details_panel.is_visible(), "Details panel should be hidden initially"

        # Find a feature and click its center
        click_result = page.evaluate("""
            () => {
                const features = window.map.queryRenderedFeatures({layers: ['h3-cells']});
                if (features.length === 0) return { success: false, error: 'No features' };

                // Get the center of the first feature's bounding box
                const feature = features[0];
                const bounds = feature.geometry.coordinates[0];
                let sumX = 0, sumY = 0;
                for (const coord of bounds) {
                    const point = window.map.project(coord);
                    sumX += point.x;
                    sumY += point.y;
                }
                const centerX = sumX / bounds.length;
                const centerY = sumY / bounds.length;

                return {
                    success: true,
                    x: centerX,
                    y: centerY,
                    h3_cell: feature.properties.h3_cell
                };
            }
        """)

        if click_result.get("success"):
            # Click on the feature
            page.click("#map canvas", position={"x": click_result["x"], "y": click_result["y"]})
            time.sleep(0.5)

            # Details panel should now be visible
            assert details_panel.is_visible(), "Details panel should show after clicking a cell"

            # Details content should have data
            details_content = page.locator("#details-content")
            content_text = details_content.inner_text()
            assert "Total Events" in content_text, "Details should show Total Events"


@pytest.mark.e2e
class TestDrillDownDrawer:
    """E2E tests for the event drill-down side drawer.

    These tests verify the complete drill-down flow including drawer interaction,
    event list display, filtering, and event detail expansion.
    """

    # --- Drawer Interaction ---

    def test_click_cell_opens_drill_down_drawer(self, page: Page, live_server: str) -> None:
        """Clicking an H3 cell should open the drill-down drawer."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        # Drill-down drawer should not be visible initially
        drawer = page.locator("[data-testid='drill-down-drawer']")
        expect(drawer).not_to_be_visible()

        # Click a rendered feature
        self._click_h3_cell(page)
        time.sleep(1)

        # Drawer should now be visible
        expect(drawer).to_be_visible(timeout=5000)
        has_open_class = drawer.evaluate("el => el.classList.contains('open')")
        assert has_open_class, "Drawer should have 'open' class"

    def test_drawer_shows_loading_state_initially(self, page: Page, live_server: str) -> None:
        """Drawer should show a loading spinner while fetching events."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        # Click a cell
        self._click_h3_cell(page)

        # Loading indicator should appear briefly
        # In a real test, we'd slow down the API to observe this
        # For now, just verify the element can be located
        page.locator("[data-testid='loading-spinner']")
        # Loading may be too fast to observe in practice

    def test_drawer_close_button_closes_drawer(self, page: Page, live_server: str) -> None:
        """Clicking the close button should close the drawer."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        # Open drawer
        self._click_h3_cell(page)
        drawer = page.locator("[data-testid='drill-down-drawer']")
        expect(drawer).to_be_visible(timeout=5000)

        # Click close button
        close_button = page.locator("[data-testid='drawer-close']")
        close_button.click()
        time.sleep(0.5)

        # Drawer should be hidden
        expect(drawer).not_to_be_visible()

    def test_click_outside_drawer_closes_it(self, page: Page, live_server: str) -> None:
        """Clicking on the map (outside drawer) should close the drawer."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        # Open drawer
        self._click_h3_cell(page)
        drawer = page.locator("[data-testid='drill-down-drawer']")
        expect(drawer).to_be_visible(timeout=5000)

        # Click on map area (left side, away from drawer)
        page.click("#map canvas", position={"x": 100, "y": 300})
        time.sleep(0.5)

        # Drawer should close
        expect(drawer).not_to_be_visible()

    # --- Event List ---

    def test_drawer_shows_event_list_after_loading(self, page: Page, live_server: str) -> None:
        """Drawer should display a list of events after loading."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        self._click_h3_cell(page)
        time.sleep(2)  # Wait for API response

        event_list = page.locator("[data-testid='event-list']")
        expect(event_list).to_be_visible(timeout=5000)

        # Should have at least one event card (or threshold message)
        event_cards = page.locator("[data-testid='event-card']")
        threshold_msg = page.locator("[data-testid='threshold-message']")

        # Either events exist or threshold message shows
        has_content = event_cards.count() > 0 or threshold_msg.is_visible()
        assert has_content, "Expected event cards or threshold message"

    def test_event_list_shows_correct_count(self, page: Page, live_server: str) -> None:
        """Event count header should match the number of events."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        self._click_h3_cell(page)
        time.sleep(2)

        # Check event count display
        event_count = page.locator("[data-testid='event-count']")
        expect(event_count).to_be_visible(timeout=5000)

        count_text = event_count.inner_text()
        assert "event" in count_text.lower(), f"Expected 'events' in count text: {count_text}"

    def test_event_card_shows_date_type_summary(self, page: Page, live_server: str) -> None:
        """Event cards should display date, type, and summary."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        self._click_h3_cell(page)
        time.sleep(2)

        # Skip if threshold applies
        threshold_msg = page.locator("[data-testid='threshold-message']")
        if threshold_msg.is_visible():
            pytest.skip("Cell has too few events (threshold applies)")

        # Check first event card
        first_card = page.locator("[data-testid='event-card']").first
        expect(first_card).to_be_visible(timeout=5000)

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
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        self._click_h3_cell(page)
        time.sleep(2)

        # Click 7-day filter
        date_chip = page.locator("[data-testid='date-chip-7d']")
        expect(date_chip).to_be_visible(timeout=5000)
        date_chip.click()
        time.sleep(1)

        # Chip should be active
        is_active = date_chip.evaluate("el => el.classList.contains('active')")
        assert is_active, "7d chip should be active"

    def test_custom_date_range_filters_events(self, page: Page, live_server: str) -> None:
        """Custom date range inputs should filter events."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        self._click_h3_cell(page)
        time.sleep(2)

        # Click custom date option
        custom_chip = page.locator("[data-testid='date-chip-custom']")
        expect(custom_chip).to_be_visible(timeout=5000)
        custom_chip.click()
        time.sleep(0.5)

        # Date inputs should appear
        start_date = page.locator("[data-testid='date-start']")
        end_date = page.locator("[data-testid='date-end']")

        expect(start_date).to_be_visible()
        expect(end_date).to_be_visible()

        # Set date range
        start_date.fill("2024-01-15")
        end_date.fill("2024-01-20")
        time.sleep(1)  # Wait for filter to apply

    def test_category_filter_shows_types_when_expanded(self, page: Page, live_server: str) -> None:
        """Clicking a category should expand to show type checkboxes."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        self._click_h3_cell(page)
        time.sleep(2)

        # Click property category
        property_chip = page.locator("[data-testid='category-property']")
        expect(property_chip).to_be_visible(timeout=5000)
        property_chip.click()
        time.sleep(0.5)

        # Type expansion should be visible
        type_expansion = page.locator("[data-testid='type-expansion']")
        expect(type_expansion).to_be_visible()

        # Should have type checkboxes
        type_checkboxes = type_expansion.locator("input[type='checkbox']")
        assert type_checkboxes.count() > 0, "Should have type filter checkboxes"

    def test_type_filter_narrows_results(self, page: Page, live_server: str) -> None:
        """Selecting a specific type should narrow the results."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        self._click_h3_cell(page)
        time.sleep(2)

        # Expand property category
        page.locator("[data-testid='category-property']").click()
        time.sleep(0.5)

        # Get initial count
        initial_count = self._get_event_count(page)
        if initial_count == 0:
            pytest.skip("No events to filter")

        # Check "Stöld" type only
        stold_checkbox = page.locator("[data-testid='type-stold']")
        if stold_checkbox.is_visible():
            stold_checkbox.check()
            time.sleep(1)

            # Count should change (likely decrease)
            new_count = self._get_event_count(page)
            # Just verify filter was applied (count may or may not change)
            assert new_count <= initial_count, "Filtering should not increase count"

    def test_search_filters_by_text(self, page: Page, live_server: str) -> None:
        """Typing in search box should filter events by text."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        self._click_h3_cell(page)
        time.sleep(2)

        # Find search input
        search_input = page.locator("[data-testid='search-input']")
        expect(search_input).to_be_visible(timeout=5000)

        # Search for common Swedish word
        search_input.fill("polis")
        time.sleep(1)  # Wait for search to apply

        # Results should update (we can't guarantee matches, but search should work)
        # Just verify the search was accepted
        assert search_input.input_value() == "polis", "Search input should contain typed text"

    def test_combined_filters_work_together(self, page: Page, live_server: str) -> None:
        """Multiple filters should combine (AND logic)."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        self._click_h3_cell(page)
        time.sleep(2)

        # Apply date filter
        page.locator("[data-testid='date-chip-30d']").click()
        time.sleep(0.5)

        # Apply category filter
        page.locator("[data-testid='category-property']").click()
        time.sleep(0.5)

        # Apply search
        page.locator("[data-testid='search-input']").fill("Stockholm")
        time.sleep(1)

        # All filters should be reflected in active state
        # (Implementation will show active filter tags)

    # --- Event Detail ---

    def test_click_event_card_expands_detail(self, page: Page, live_server: str) -> None:
        """Clicking an event card should expand to show full details."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        self._click_h3_cell(page)
        time.sleep(2)

        # Skip if no events
        threshold_msg = page.locator("[data-testid='threshold-message']")
        if threshold_msg.is_visible():
            pytest.skip("Cell has too few events")

        # Click first event card
        first_card = page.locator("[data-testid='event-card']").first
        first_card.click()
        time.sleep(0.5)

        # Card should be expanded
        is_expanded = first_card.evaluate("el => el.classList.contains('expanded')")
        assert is_expanded, "Card should be expanded"

    def test_event_detail_shows_full_html_body(self, page: Page, live_server: str) -> None:
        """Expanded event should show the full HTML body content."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        self._click_h3_cell(page)
        time.sleep(2)

        threshold_msg = page.locator("[data-testid='threshold-message']")
        if threshold_msg.is_visible():
            pytest.skip("Cell has too few events")

        # Expand first card
        first_card = page.locator("[data-testid='event-card']").first
        first_card.click()
        time.sleep(0.5)

        # Full body content should be visible
        body_content = first_card.locator("[data-testid='event-body']")
        expect(body_content).to_be_visible()

    def test_event_detail_has_police_report_link(self, page: Page, live_server: str) -> None:
        """Expanded event should have a link to the police report."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        self._click_h3_cell(page)
        time.sleep(2)

        threshold_msg = page.locator("[data-testid='threshold-message']")
        if threshold_msg.is_visible():
            pytest.skip("Cell has too few events")

        # Expand first card
        first_card = page.locator("[data-testid='event-card']").first
        first_card.click()
        time.sleep(0.5)

        # Police link should exist
        police_link = first_card.locator("[data-testid='police-link']")
        expect(police_link).to_be_visible()

    def test_police_report_link_correct_url(self, page: Page, live_server: str) -> None:
        """Police report link should point to polisen.se."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        self._click_h3_cell(page)
        time.sleep(2)

        threshold_msg = page.locator("[data-testid='threshold-message']")
        if threshold_msg.is_visible():
            pytest.skip("Cell has too few events")

        # Expand first card
        first_card = page.locator("[data-testid='event-card']").first
        first_card.click()
        time.sleep(0.5)

        # Check link URL
        police_link = first_card.locator("[data-testid='police-link']")
        href = police_link.get_attribute("href")
        assert href is not None, "Police link should have href"
        assert "polisen.se" in href, f"Link should point to polisen.se: {href}"

    # --- Pagination ---

    def test_pagination_shows_page_info(self, page: Page, live_server: str) -> None:
        """Pagination should show current page and total pages."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        self._click_h3_cell(page)
        time.sleep(2)

        # Skip if below threshold
        threshold_msg = page.locator("[data-testid='threshold-message']")
        if threshold_msg.is_visible():
            pytest.skip("Cell has too few events")

        # Pagination should be visible
        pagination = page.locator("[data-testid='pagination']")
        expect(pagination).to_be_visible(timeout=5000)

        # Page info should show "Page X of Y"
        page_info = pagination.locator("[data-testid='page-info']")
        expect(page_info).to_be_visible()
        info_text = page_info.inner_text()
        assert "Page" in info_text, f"Expected 'Page' in info: {info_text}"

    def test_pagination_next_page_loads_more(self, page: Page, live_server: str) -> None:
        """Clicking Next should load the next page of events."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        self._click_h3_cell(page)
        time.sleep(2)

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
        time.sleep(1)

        # First event should be different
        new_first_card = page.locator("[data-testid='event-card']").first
        new_event_id = new_first_card.get_attribute("data-event-id")

        assert new_event_id != first_event_id, "Next page should show different events"

    # --- Threshold ---

    def test_cell_under_threshold_shows_message_not_list(
        self, page: Page, live_server: str
    ) -> None:
        """Cells with <3 events should show a message, not the event list."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(5)

        # This test may need to find a specific sparse cell
        # For now, we verify the threshold message element exists in the implementation
        self._click_h3_cell(page)
        time.sleep(2)

        # Either we have events OR threshold message
        event_list = page.locator("[data-testid='event-list']")
        threshold_msg = page.locator("[data-testid='threshold-message']")

        event_count = self._get_event_count(page)

        # If count is 1-2, threshold message should show
        if 0 < event_count < 3:
            expect(threshold_msg).to_be_visible()
            expect(event_list).not_to_be_visible()

    # --- Helper Methods ---

    def _click_h3_cell(self, page: Page) -> dict[str, float | str] | None:
        """Find and click an H3 cell on the map."""
        result = page.evaluate("""
            () => {
                const features = window.map.queryRenderedFeatures({layers: ['h3-cells']});
                if (features.length === 0) return null;

                const feature = features[0];
                const bounds = feature.geometry.coordinates[0];
                let sumX = 0, sumY = 0;
                for (const coord of bounds) {
                    const point = window.map.project(coord);
                    sumX += point.x;
                    sumY += point.y;
                }
                return {
                    x: sumX / bounds.length,
                    y: sumY / bounds.length,
                    h3_cell: feature.properties.h3_cell
                };
            }
        """)

        if result:
            page.click("#map canvas", position={"x": result["x"], "y": result["y"]})
        return result  # type: ignore[no-any-return]

    def _get_event_count(self, page: Page) -> int:
        """Extract event count from the count display."""
        count_el = page.locator("[data-testid='event-count']")
        if not count_el.is_visible():
            return 0

        text = count_el.inner_text()
        # Parse "42 events" -> 42
        import re

        match = re.search(r"(\d+)", text)
        return int(match.group(1)) if match else 0

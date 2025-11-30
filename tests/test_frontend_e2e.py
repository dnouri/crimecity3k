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
        """Test that PMTiles sources are loaded for all resolutions."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(3)  # Wait for all sources to load

        # Check that resolution sources are loaded
        sources_loaded = page.evaluate("""
            () => {
                const results = [];
                for (const res of [4, 5, 6]) {
                    const source = window.map.getSource(`h3-tiles-r${res}`);
                    if (source) results.push(res);
                }
                return results;
            }
        """)
        assert len(sources_loaded) == 3, f"Expected 3 sources, found {sources_loaded}"
        assert sources_loaded == [4, 5, 6], f"Missing sources: {sources_loaded}"

    def test_h3_layer_displays(self, page: Page, live_server: str) -> None:
        """Test that the H3 cells layer is added to the map."""
        page.goto(f"{live_server}/static/index.html")
        page.wait_for_selector("#map canvas", timeout=15000)
        time.sleep(3)

        has_layer = page.evaluate("window.map && window.map.getLayer('h3-cells') !== undefined")
        assert has_layer, "H3 cells layer not found"

    def test_resolution_switching_with_zoom(self, page: Page, live_server: str) -> None:
        """Test that H3 resolution changes correctly with zoom level."""
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

        # Test zoom level 7 -> resolution 6
        page.evaluate("window.map.setZoom(7)")
        time.sleep(1.5)
        resolution = page.evaluate("window.currentResolution")
        assert resolution == 6, f"Expected resolution 6 at zoom 7, got {resolution}"

        # Resolution indicator should update
        indicator = page.locator("#current-resolution")
        expect(indicator).to_have_text("6")

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

/**
 * CrimeCity3K - Interactive Swedish Police Events Map
 *
 * Displays crime events aggregated to H3 hexagonal cells with
 * population normalization. Data from Swedish Police API and SCB.
 */

// Register PMTiles protocol for MapLibre
const protocol = new pmtiles.Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);

// Configuration
const CONFIG = {
    // Sweden center coordinates
    center: [16.5, 62.5],
    initialZoom: 5,

    // H3 resolution to zoom level mapping
    // Note: r6 removed due to centroid artifacts - all city events report at
    // single coordinates, causing rate inflation up to 4.3x at fine resolutions.
    // r5 (~250km² cells) provides adequate detail while capturing metro populations.
    // R4 at zoom 3-5, R5 at zoom 6+ (switched earlier to avoid crowded R5 at low zoom)
    zoomToResolution: {
        3: 4,
        4: 4,
        5: 4,
        6: 5,
        7: 5,
        8: 5,
        9: 5,
        10: 5,
        11: 5,
        12: 5
    },

    // Available resolutions (r6 excluded - see note above)
    resolutions: [4, 5],

    // PMTiles path (relative to server root)
    tilesPath: '/data/tiles/pmtiles',

    // Tile version for cache busting (bump when tile schema changes)
    tileVersion: 2,

    // Color scale for absolute counts (red sequential)
    // Buckets: 0-10, 10-50, 50-200, 200-500, 500-1500, 1500+
    absoluteColors: {
        stops: [0, 10, 50, 200, 500, 1500],
        colors: ['#fee5d9', '#fcae91', '#fb6a4a', '#de2d26', '#a50f15', '#67000d']
    },

    // Color scale for normalized rates (per 10,000)
    normalizedColors: {
        stops: [0, 50, 200, 500, 2000],
        colors: ['#fee5d9', '#fcae91', '#fb6a4a', '#de2d26', '#a50f15']
    },

    // Category display names
    categories: {
        traffic: 'Traffic',
        property: 'Property',
        violence: 'Violence',
        narcotics: 'Narcotics',
        fraud: 'Fraud',
        public_order: 'Public Order',
        weapons: 'Weapons',
        other: 'Other'
    }
};

// State
let currentResolution = null;
let currentFilter = 'all';
let displayMode = 'absolute';
const loadedSources = {};

// Stats-first UI state
let currentCellData = null;  // { h3_cell, properties, locationName }
let viewState = 'none';      // 'none' | 'stats' | 'drawer'

// Make state accessible for E2E tests
window.currentResolution = null;
window.displayMode = 'absolute';

// Initialize map
const map = new maplibregl.Map({
    container: 'map',
    style: {
        version: 8,
        sources: {
            'osm': {
                type: 'raster',
                tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
                tileSize: 256,
                attribution: '&copy; <a href="https://openstreetmap.org">OpenStreetMap</a>'
            }
        },
        layers: [{
            id: 'osm',
            type: 'raster',
            source: 'osm'
        }]
    },
    center: CONFIG.center,
    zoom: CONFIG.initialZoom,
    maxZoom: 12,
    minZoom: 3
});

// Expose map for E2E tests
window.map = map;

/**
 * Get the color expression for the current display mode and filter.
 */
function getColorExpression() {
    const colors = displayMode === 'absolute'
        ? CONFIG.absoluteColors
        : CONFIG.normalizedColors;

    const field = displayMode === 'absolute'
        ? getCountField()
        : 'rate_per_10000';

    // Build expression dynamically to handle different numbers of stops
    const expression = [
        'interpolate',
        ['linear'],
        ['coalesce', ['get', field], 0]
    ];

    for (let i = 0; i < colors.stops.length; i++) {
        expression.push(colors.stops[i], colors.colors[i]);
    }

    return expression;
}

/**
 * Get the count field based on current filter.
 */
function getCountField() {
    if (currentFilter === 'all') {
        return 'total_count';
    }
    return `${currentFilter}_count`;
}

/**
 * Build filter expression for MapLibre layer.
 */
function getFilterExpression() {
    if (currentFilter === 'all') {
        return null;
    }
    const field = `${currentFilter}_count`;
    return ['>', ['get', field], 0];
}

/**
 * Load all PMTiles sources.
 */
function loadAllSources() {
    let loadCount = 0;

    for (const res of CONFIG.resolutions) {
        const sourceId = `h3-tiles-r${res}`;
        const url = `pmtiles://${CONFIG.tilesPath}/h3_r${res}.pmtiles?v=${CONFIG.tileVersion}`;

        try {
            map.addSource(sourceId, {
                type: 'vector',
                url: url
            });
            loadedSources[res] = true;
            loadCount++;
        } catch (error) {
            console.error(`Failed to load PMTiles for resolution ${res}:`, error);
            loadedSources[res] = false;
        }
    }

    return loadCount > 0;
}

/**
 * Get best available resolution for a zoom level.
 */
function getBestResolutionForZoom(zoom) {
    const targetRes = CONFIG.zoomToResolution[Math.floor(zoom)] || 4;

    if (loadedSources[targetRes]) {
        return targetRes;
    }

    // Fallback to nearest available
    let bestRes = null;
    let minDiff = Infinity;

    for (const res of CONFIG.resolutions) {
        if (loadedSources[res]) {
            const diff = Math.abs(res - targetRes);
            if (diff < minDiff) {
                minDiff = diff;
                bestRes = res;
            }
        }
    }

    return bestRes;
}

/**
 * Add H3 cells layer for a resolution.
 */
function addH3Layer(resolution) {
    const layerId = 'h3-cells';
    const sourceId = `h3-tiles-r${resolution}`;

    const layerConfig = {
        id: layerId,
        type: 'fill',
        source: sourceId,
        'source-layer': 'h3_cells',
        paint: {
            'fill-color': getColorExpression(),
            'fill-opacity': 0.7,
            'fill-outline-color': 'rgba(0, 0, 0, 0.1)'
        }
    };

    const filterExpr = getFilterExpression();
    if (filterExpr) {
        layerConfig.filter = filterExpr;
    }

    map.addLayer(layerConfig);
}

/**
 * Switch to a new resolution.
 */
function switchToResolution(newRes) {
    if (currentResolution === newRes) {
        return;
    }

    // Remove existing layer
    if (map.getLayer('h3-cells')) {
        map.removeLayer('h3-cells');
    }

    // Add new layer
    addH3Layer(newRes);

    // Update state
    currentResolution = newRes;
    window.currentResolution = newRes;

    // Update UI
    document.getElementById('current-resolution').textContent = newRes;

    // Re-register event handlers
    registerLayerEventHandlers();
}

/**
 * Register mouse/click handlers for the H3 layer.
 */
function registerLayerEventHandlers() {
    // Cursor change on hover
    map.on('mouseenter', 'h3-cells', () => {
        map.getCanvas().style.cursor = 'pointer';
    });

    map.on('mouseleave', 'h3-cells', () => {
        map.getCanvas().style.cursor = '';
    });

    // Click to show details
    map.on('click', 'h3-cells', (e) => {
        if (e.features.length > 0) {
            showCellDetails(e.features[0].properties);
        }
    });

    // Click outside (on map, not on features) to hide details
    map.on('click', (e) => {
        const features = map.queryRenderedFeatures(e.point, { layers: ['h3-cells'] });
        if (features.length === 0) {
            // Only close if not clicking inside the drawer
            const drawer = document.getElementById('drill-down-drawer');
            if (drawer && !drawer.contains(e.originalEvent.target)) {
                hideCellDetails();
            }
        }
    });
}

/**
 * Show cell details panel with stats and Search Events button.
 * Does NOT auto-open drill-down drawer (stats-first flow).
 */
function showCellDetails(props) {
    const h3Cell = props.h3_cell;
    // Use dominant_location from tile data (most common location in this cell)
    const locationName = props.dominant_location || 'Unknown location';

    // Store current cell data for later use
    currentCellData = {
        h3_cell: h3Cell,
        properties: props,
        locationName: locationName
    };

    // If drawer is already open, update it directly (Option B behavior)
    if (viewState === 'drawer' && DrillDown && DrillDown.isOpen()) {
        DrillDown.open(h3Cell, locationName, props);
        return;
    }

    // Update stats panel content
    const content = document.getElementById('details-content');
    const panel = document.getElementById('cell-details');

    // Set title to location name
    document.getElementById('details-title').textContent = locationName;

    // Basic stats
    let html = '<div class="detail-row">';
    html += '<span class="detail-label">Total Events</span>';
    html += `<span class="detail-value">${props.total_count?.toLocaleString() || 0}</span>`;
    html += '</div>';

    html += '<div class="detail-row">';
    html += '<span class="detail-label">Rate per 10k</span>';
    html += `<span class="detail-value">${props.rate_per_10000?.toFixed(1) || '0.0'}</span>`;
    html += '</div>';

    html += '<div class="detail-row">';
    html += '<span class="detail-label">Population</span>';
    html += `<span class="detail-value">${Math.round(props.population || 0).toLocaleString()}</span>`;
    html += '</div>';

    // Category breakdown
    html += '<div class="category-breakdown">';
    html += '<h5>By Category</h5>';

    for (const [key, name] of Object.entries(CONFIG.categories)) {
        const count = props[`${key}_count`] || 0;
        if (count > 0) {
            html += '<div class="category-bar">';
            html += `<span class="category-name">${name}</span>`;
            html += `<span class="category-count">${count.toLocaleString()}</span>`;
            html += '</div>';
        }
    }
    html += '</div>';

    // Top event types
    let typeCounts = props.type_counts;
    if (typeCounts) {
        // Parse if string (PMTiles may serialize arrays as strings)
        if (typeof typeCounts === 'string') {
            try {
                typeCounts = JSON.parse(typeCounts);
            } catch {
                typeCounts = [];
            }
        }

        if (Array.isArray(typeCounts) && typeCounts.length > 0) {
            html += '<div class="top-types">';
            html += '<h5>Top Event Types</h5>';

            const topTypes = typeCounts.slice(0, 8);
            for (const item of topTypes) {
                html += '<div class="type-item">';
                html += `<span class="type-name">${item.type}</span>`;
                html += `<span class="type-count">${item.count}</span>`;
                html += '</div>';
            }
            html += '</div>';
        }
    }

    // Search Events button
    html += '<div class="search-events-action">';
    html += '<button id="search-events-button" data-testid="search-events-button" class="search-events-button">';
    html += 'Search Events →';
    html += '</button>';
    html += '</div>';

    content.innerHTML = html;
    panel.classList.add('visible');
    viewState = 'stats';

    // Bind click handler for Search Events button
    document.getElementById('search-events-button').addEventListener('click', openDrawerFromStats);
}

/**
 * Open drill-down drawer from stats view.
 */
function openDrawerFromStats() {
    if (!currentCellData || !DrillDown) return;

    // Hide stats panel
    document.getElementById('cell-details').classList.remove('visible');

    // Open drawer
    DrillDown.open(
        currentCellData.h3_cell,
        currentCellData.locationName,
        currentCellData.properties
    );
    viewState = 'drawer';
}

/**
 * Hide cell details panel and reset state.
 */
function hideCellDetails() {
    document.getElementById('cell-details').classList.remove('visible');
    viewState = 'none';
    currentCellData = null;

    // Also close drill-down drawer if open
    if (DrillDown && DrillDown.isOpen()) {
        DrillDown.close(false);  // false = don't return to stats
    }
}

/**
 * Update legend based on current display mode.
 */
function updateLegend() {
    const title = document.getElementById('legend-title');
    const items = document.getElementById('legend-items');

    const colors = displayMode === 'absolute'
        ? CONFIG.absoluteColors
        : CONFIG.normalizedColors;

    title.textContent = displayMode === 'absolute'
        ? 'Event Count'
        : 'Rate per 10,000';

    let html = '';
    for (let i = 0; i < colors.stops.length; i++) {
        const label = i === colors.stops.length - 1
            ? `${colors.stops[i]}+`
            : `${colors.stops[i]}-${colors.stops[i + 1]}`;

        html += '<div class="legend-item">';
        html += `<div class="legend-color" style="background: ${colors.colors[i]};"></div>`;
        html += `<span class="legend-label">${label}</span>`;
        html += '</div>';
    }

    items.innerHTML = html;
}

/**
 * Update layer paint based on current settings.
 */
function updateLayerPaint() {
    if (map.getLayer('h3-cells')) {
        map.setPaintProperty('h3-cells', 'fill-color', getColorExpression());
    }
}

/**
 * Update layer filter based on current category.
 */
function updateLayerFilter() {
    if (!map.getLayer('h3-cells')) return;

    const filterExpr = getFilterExpression();
    if (filterExpr) {
        map.setFilter('h3-cells', filterExpr);
    } else {
        map.setFilter('h3-cells', null);
    }

    // Also update paint since we might be showing different count field
    updateLayerPaint();
}

/**
 * Initialize mobile-specific interactions.
 */
function initMobileInteractions() {
    const isMobile = window.matchMedia('(max-width: 768px)').matches;
    if (!isMobile) return;

    // Collapsible legend
    const legend = document.getElementById('legend');
    const legendTitle = legend.querySelector('h4');

    if (legendTitle && !legend.dataset.initialized) {
        legend.classList.add('collapsed');
        legend.dataset.initialized = 'true';

        legendTitle.addEventListener('click', (e) => {
            e.stopPropagation();
            legend.classList.toggle('collapsed');
        });
    }

    // Swipe to dismiss details panel
    const panel = document.getElementById('cell-details');
    let startY = 0;
    let currentY = 0;
    let isDragging = false;

    panel.addEventListener('touchstart', (e) => {
        startY = e.touches[0].clientY;
        isDragging = true;
        panel.style.transition = 'none';
    }, { passive: true });

    panel.addEventListener('touchmove', (e) => {
        if (!isDragging) return;
        currentY = e.touches[0].clientY;
        const deltaY = currentY - startY;

        if (deltaY > 0) {
            panel.style.transform = `translateY(${deltaY}px)`;
        }
    }, { passive: true });

    panel.addEventListener('touchend', () => {
        if (!isDragging) return;
        isDragging = false;
        panel.style.transition = 'transform 0.3s ease-out';

        const deltaY = currentY - startY;
        if (deltaY > 100) {
            hideCellDetails();
        }
        panel.style.transform = '';
        startY = 0;
        currentY = 0;
    }, { passive: true });
}

// Event handlers
document.getElementById('display-mode-toggle').addEventListener('change', (e) => {
    displayMode = e.target.checked ? 'normalized' : 'absolute';
    window.displayMode = displayMode;

    document.getElementById('display-mode-label').textContent =
        displayMode === 'absolute' ? 'Absolute' : 'Normalized';

    updateLegend();
    updateLayerPaint();
});

document.getElementById('category-filter').addEventListener('change', (e) => {
    currentFilter = e.target.value;
    updateLayerFilter();
});

document.getElementById('close-details').addEventListener('click', hideCellDetails);

// ============================================
// KEYBOARD SHORTCUTS
// ============================================

/**
 * Global keyboard shortcuts handler.
 * - S: Open search from stats view
 * - Escape: Close current panel / go back
 * - /: Focus search input (when drawer open)
 * - ?: Show shortcuts help
 */
document.addEventListener('keydown', (e) => {
    // Don't intercept when typing in an input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        // But allow Escape from inputs
        if (e.key !== 'Escape') return;
    }

    const shortcutsHelp = document.getElementById('shortcuts-help');
    const shortcutsVisible = shortcutsHelp.classList.contains('visible');

    // ? - Show shortcuts help
    if (e.key === '?' || (e.shiftKey && e.key === '/')) {
        e.preventDefault();
        if (shortcutsVisible) {
            hideShortcutsHelp();
        } else {
            showShortcutsHelp();
        }
        return;
    }

    // Escape - context dependent
    if (e.key === 'Escape') {
        // First close shortcuts help if open
        if (shortcutsVisible) {
            hideShortcutsHelp();
            return;
        }

        // Then handle based on view state
        if (viewState === 'drawer' && DrillDown && DrillDown.isOpen()) {
            DrillDown.close();  // Returns to stats (Option A)
        } else if (viewState === 'stats') {
            hideCellDetails();
        }
        return;
    }

    // S - Open search from stats view
    if (e.key === 's' || e.key === 'S') {
        if (viewState === 'stats' && currentCellData) {
            e.preventDefault();
            openDrawerFromStats();
        }
        return;
    }

    // / - Focus search input (when drawer open)
    if (e.key === '/') {
        if (viewState === 'drawer' && DrillDown && DrillDown.isOpen()) {
            e.preventDefault();
            DrillDown.elements.searchInput.focus();
        }
        return;
    }
});

/**
 * Show keyboard shortcuts help modal.
 */
function showShortcutsHelp() {
    document.getElementById('shortcuts-help').classList.add('visible');
}

/**
 * Hide keyboard shortcuts help modal.
 */
function hideShortcutsHelp() {
    document.getElementById('shortcuts-help').classList.remove('visible');
}

// Shortcuts help close button
document.getElementById('shortcuts-close').addEventListener('click', hideShortcutsHelp);

// ============================================
// DRILL-DOWN DRAWER MODULE
// ============================================

const DrillDown = {
    // State
    currentH3Cell: null,
    cellProps: null,         // Cell properties for header stats display
    cellTotalEvents: 0,      // Total events in cell (for "X of Y" display)
    currentPage: 1,
    perPage: 10,
    totalEvents: 0,          // Filtered/current total
    filters: {
        search: '',
        startDate: null,
        endDate: null,
        categories: [],
        types: []
    },
    debounceTimer: null,
    abortController: null,

    // DOM Elements (cached on init)
    elements: {},

    /**
     * Initialize drill-down drawer functionality.
     */
    init() {
        this.cacheElements();
        this.bindEvents();
    },

    /**
     * Cache DOM element references.
     */
    cacheElements() {
        this.elements = {
            drawer: document.getElementById('drill-down-drawer'),
            closeBtn: document.getElementById('drawer-close'),
            location: document.getElementById('drawer-location'),
            statsSummary: document.getElementById('drawer-stats-summary'),
            searchInput: document.getElementById('filter-search'),
            dateChips: document.querySelectorAll('.date-chips .filter-chip'),
            customDateRange: document.getElementById('custom-date-range'),
            dateStart: document.getElementById('date-start'),
            dateEnd: document.getElementById('date-end'),
            categoryChips: document.querySelectorAll('.category-chips .filter-chip'),
            typeExpansion: document.getElementById('type-expansion'),
            loadingSpinner: document.getElementById('loading-spinner'),
            thresholdMessage: document.getElementById('threshold-message'),
            eventList: document.getElementById('event-list'),
            emptyState: document.getElementById('empty-state'),
            errorState: document.getElementById('error-state'),
            retryButton: document.getElementById('retry-button'),
            pagination: document.getElementById('pagination'),
            pageInfo: document.getElementById('page-info'),
            prevBtn: document.getElementById('pagination-prev'),
            nextBtn: document.getElementById('pagination-next')
        };
    },

    /**
     * Bind event listeners.
     */
    bindEvents() {
        // Close button
        this.elements.closeBtn.addEventListener('click', () => this.close());

        // Note: Escape key is handled globally in the keyboard shortcuts section

        // Search input (debounced)
        this.elements.searchInput.addEventListener('input', (e) => {
            this.debounce(() => {
                this.filters.search = e.target.value;
                this.currentPage = 1;
                this.fetchEvents();
            }, 300);
        });

        // Date chips
        this.elements.dateChips.forEach(chip => {
            chip.addEventListener('click', () => this.handleDateChipClick(chip));
        });

        // Custom date inputs
        this.elements.dateStart.addEventListener('change', () => this.handleCustomDateChange());
        this.elements.dateEnd.addEventListener('change', () => this.handleCustomDateChange());

        // Category chips
        this.elements.categoryChips.forEach(chip => {
            chip.addEventListener('click', () => this.handleCategoryClick(chip));
        });

        // Retry button
        this.elements.retryButton.addEventListener('click', () => this.fetchEvents());

        // Pagination
        this.elements.prevBtn.addEventListener('click', () => this.goToPage(this.currentPage - 1));
        this.elements.nextBtn.addEventListener('click', () => this.goToPage(this.currentPage + 1));
    },

    /**
     * Open drawer for a specific H3 cell.
     * @param {string} h3Cell - The H3 cell ID
     * @param {string} locationName - Display name for the location
     * @param {object} cellProps - Cell properties (total_count, rate_per_10000, etc.)
     */
    open(h3Cell, locationName = 'Events', cellProps = null) {
        // Only reset filters when opening fresh (not when switching cells)
        const isAlreadyOpen = this.isOpen();

        this.currentH3Cell = h3Cell;
        this.cellProps = cellProps;
        this.cellTotalEvents = cellProps?.total_count || 0;
        this.currentPage = 1;

        if (!isAlreadyOpen) {
            this.resetFilters();
        }

        this.elements.location.textContent = locationName;
        this.elements.drawer.classList.add('open');

        // Update header stats summary
        this.updateHeaderStats();

        // Focus management - focus search input after drawer opens
        setTimeout(() => {
            this.elements.searchInput.focus();
        }, 100);

        this.fetchEvents();
    },

    /**
     * Close the drawer.
     * @param {boolean} returnToStats - If true, show stats panel again (Option A behavior)
     */
    close(returnToStats = true) {
        this.elements.drawer.classList.remove('open');

        if (returnToStats && currentCellData) {
            // Return to stats view (Option A)
            document.getElementById('cell-details').classList.add('visible');
            viewState = 'stats';
        } else {
            // Full close
            this.currentH3Cell = null;
            this.cellProps = null;
            viewState = 'none';
        }
    },

    /**
     * Check if drawer is open.
     */
    isOpen() {
        return this.elements.drawer.classList.contains('open');
    },

    /**
     * Reset all filters to defaults.
     */
    resetFilters() {
        this.filters = {
            search: '',
            startDate: null,
            endDate: null,
            categories: [],
            types: []
        };
        this.elements.searchInput.value = '';

        // Reset date chips
        this.elements.dateChips.forEach(c => c.classList.remove('active'));
        document.querySelector('[data-testid="date-chip-all"]').classList.add('active');
        this.elements.customDateRange.classList.remove('visible');

        // Reset category chips
        this.elements.categoryChips.forEach(c => c.classList.remove('active'));
        document.querySelector('[data-testid="category-all"]').classList.add('active');
        this.elements.typeExpansion.classList.remove('visible');
        this.elements.typeExpansion.innerHTML = '';
    },

    /**
     * Handle date chip click.
     */
    handleDateChipClick(chip) {
        // Remove active from all date chips
        this.elements.dateChips.forEach(c => c.classList.remove('active'));
        chip.classList.add('active');

        const days = chip.dataset.days;
        const isCustom = chip.dataset.testid === 'date-chip-custom';

        if (isCustom) {
            this.elements.customDateRange.classList.add('visible');
            return; // Don't fetch yet, wait for date input
        }

        this.elements.customDateRange.classList.remove('visible');

        if (days) {
            const end = new Date();
            const start = new Date();
            start.setDate(start.getDate() - parseInt(days));
            this.filters.startDate = start.toISOString().split('T')[0];
            this.filters.endDate = end.toISOString().split('T')[0];
        } else {
            this.filters.startDate = null;
            this.filters.endDate = null;
        }

        this.currentPage = 1;
        this.fetchEvents();
    },

    /**
     * Handle custom date range change.
     */
    handleCustomDateChange() {
        const start = this.elements.dateStart.value;
        const end = this.elements.dateEnd.value;

        if (start && end) {
            this.filters.startDate = start;
            this.filters.endDate = end;
            this.currentPage = 1;
            this.fetchEvents();
        }
    },

    /**
     * Handle category chip click.
     */
    handleCategoryClick(chip) {
        const category = chip.dataset.category;

        if (category === 'all') {
            // Reset to all categories
            this.elements.categoryChips.forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            this.filters.categories = [];
            this.elements.typeExpansion.classList.remove('visible');
        } else {
            // Toggle single category
            document.querySelector('[data-testid="category-all"]').classList.remove('active');

            if (chip.classList.contains('active')) {
                chip.classList.remove('active');
                this.filters.categories = this.filters.categories.filter(c => c !== category);
            } else {
                chip.classList.add('active');
                this.filters.categories.push(category);
            }

            // Show type expansion for selected category
            if (this.filters.categories.length === 1) {
                this.showTypeExpansion(this.filters.categories[0]);
            } else {
                this.elements.typeExpansion.classList.remove('visible');
            }

            // If no categories selected, reset to all
            if (this.filters.categories.length === 0) {
                document.querySelector('[data-testid="category-all"]').classList.add('active');
            }
        }

        this.currentPage = 1;
        this.fetchEvents();
    },

    /**
     * Show type expansion for a category.
     */
    async showTypeExpansion(category) {
        try {
            const response = await fetch('/api/types');
            const data = await response.json();
            const types = data.categories[category] || [];

            if (types.length === 0) {
                this.elements.typeExpansion.classList.remove('visible');
                return;
            }

            let html = '';
            types.forEach(type => {
                const typeId = type.toLowerCase().replace(/[^a-z]/g, '');
                html += `
                    <div class="type-checkbox">
                        <input type="checkbox" id="type-${typeId}" data-testid="type-${typeId}" data-type="${type}" checked>
                        <label for="type-${typeId}">${type}</label>
                    </div>
                `;
            });

            this.elements.typeExpansion.innerHTML = html;
            this.elements.typeExpansion.classList.add('visible');

            // Bind checkbox events
            this.elements.typeExpansion.querySelectorAll('input').forEach(checkbox => {
                checkbox.addEventListener('change', () => this.handleTypeChange());
            });
        } catch (error) {
            console.error('Failed to load types:', error);
        }
    },

    /**
     * Handle type checkbox change.
     */
    handleTypeChange() {
        const checked = this.elements.typeExpansion.querySelectorAll('input:checked');
        this.filters.types = Array.from(checked).map(cb => cb.dataset.type);
        this.currentPage = 1;
        this.fetchEvents();
    },

    /**
     * Go to a specific page.
     */
    goToPage(page) {
        if (page < 1) return;
        const maxPage = Math.ceil(this.totalEvents / this.perPage);
        if (page > maxPage) return;

        this.currentPage = page;
        this.fetchEvents();
    },

    /**
     * Fetch events from API.
     */
    async fetchEvents() {
        if (!this.currentH3Cell) return;

        // Cancel any in-flight request
        if (this.abortController) {
            this.abortController.abort();
        }
        this.abortController = new AbortController();

        this.showState('loading');

        try {
            const params = new URLSearchParams({
                h3_cell: this.currentH3Cell,
                page: this.currentPage,
                per_page: this.perPage
            });

            if (this.filters.search) {
                params.append('search', this.filters.search);
            }
            if (this.filters.startDate) {
                params.append('start_date', this.filters.startDate);
            }
            if (this.filters.endDate) {
                params.append('end_date', this.filters.endDate);
            }
            this.filters.categories.forEach(cat => {
                params.append('categories', cat);
            });
            this.filters.types.forEach(type => {
                params.append('types', type);
            });

            const response = await fetch(`/api/events?${params}`, {
                signal: this.abortController.signal
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            this.totalEvents = data.total;

            this.updateEventCount(data.total);
            this.renderEvents(data);
        } catch (error) {
            // Ignore abort errors
            if (error.name === 'AbortError') {
                return;
            }
            console.error('Failed to fetch events:', error);
            this.showState('error');
        }
    },

    /**
     * Update event count and header stats.
     */
    updateEventCount(count) {
        // Update header stats with filtered count
        this.updateHeaderStats(count);
    },

    /**
     * Update header stats summary display.
     * Shows "X of Y events · Z/10k" format, where X is filtered count, Y is cell total.
     */
    updateHeaderStats(filteredCount = null) {
        const statsEl = this.elements.statsSummary;
        if (!statsEl) return;

        const rate = this.cellProps?.rate_per_10000?.toFixed(1) || '0.0';
        const cellTotal = this.cellTotalEvents;

        // Check if any filters are active
        const hasActiveFilters = this.filters.search ||
            this.filters.startDate ||
            this.filters.endDate ||
            this.filters.categories.length > 0 ||
            this.filters.types.length > 0;

        let text;
        if (filteredCount !== null && hasActiveFilters && filteredCount !== cellTotal) {
            // Show filtered vs total
            text = `${filteredCount} of ${cellTotal} events · ${rate}/10k`;
        } else {
            // Show total only
            text = `${cellTotal} events · ${rate}/10k`;
        }

        statsEl.textContent = text;
    },

    /**
     * Show a specific state (loading, threshold, events, empty, error).
     */
    showState(state) {
        // Hide all states
        this.elements.loadingSpinner.classList.remove('visible');
        this.elements.thresholdMessage.classList.remove('visible');
        this.elements.eventList.classList.remove('visible');
        this.elements.emptyState.classList.remove('visible');
        this.elements.errorState.classList.remove('visible');
        this.elements.pagination.classList.remove('visible');

        switch (state) {
            case 'loading':
                this.elements.loadingSpinner.classList.add('visible');
                break;
            case 'threshold':
                this.elements.thresholdMessage.classList.add('visible');
                break;
            case 'events':
                this.elements.eventList.classList.add('visible');
                this.elements.pagination.classList.add('visible');
                break;
            case 'empty':
                this.elements.emptyState.classList.add('visible');
                break;
            case 'error':
                this.elements.errorState.classList.add('visible');
                break;
        }
    },

    /**
     * Render events to the list.
     */
    renderEvents(data) {
        const { events, total, page, per_page } = data;

        // Check threshold (total > 0 but events empty means below threshold)
        if (total > 0 && events.length === 0) {
            this.showState('threshold');
            return;
        }

        // Empty state
        if (total === 0) {
            this.showState('empty');
            return;
        }

        // Render event cards
        let html = '';
        events.forEach(event => {
            html += this.renderEventCard(event);
        });
        this.elements.eventList.innerHTML = html;

        // Bind card click events
        this.elements.eventList.querySelectorAll('.event-card').forEach(card => {
            card.addEventListener('click', () => this.toggleCardExpansion(card));
        });

        // Update pagination
        const maxPage = Math.ceil(total / per_page);
        this.elements.pageInfo.textContent = `Page ${page} of ${maxPage}`;
        this.elements.prevBtn.disabled = page <= 1;
        this.elements.nextBtn.disabled = page >= maxPage;

        this.showState('events');
    },

    /**
     * Render a single event card.
     */
    renderEventCard(event) {
        const date = new Date(event.event_datetime);
        const dateStr = date.toLocaleDateString('sv-SE') + ' ' +
                       date.toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit' });

        const summary = event.summary || '';
        const bodyContent = event.html_body || event.summary || 'No additional details available.';

        return `
            <div class="event-card ${event.category}" data-testid="event-card" data-event-id="${event.event_id}">
                <div class="event-meta">
                    <span class="event-date" data-testid="event-date">${dateStr}</span>
                    <span class="event-type" data-testid="event-type">${event.type}</span>
                </div>
                <div class="event-location">${event.location_name}</div>
                <div class="event-summary" data-testid="event-summary">${summary}</div>
                <div class="event-body" data-testid="event-body">${bodyContent}</div>
                <div class="event-actions">
                    <a href="${event.police_url}" target="_blank" rel="noopener" class="police-link" data-testid="police-link">
                        📋 View Police Report
                    </a>
                </div>
            </div>
        `;
    },

    /**
     * Toggle event card expansion.
     */
    toggleCardExpansion(card) {
        // Collapse any other expanded cards
        this.elements.eventList.querySelectorAll('.event-card.expanded').forEach(c => {
            if (c !== card) c.classList.remove('expanded');
        });

        // Toggle this card
        card.classList.toggle('expanded');
    },

    /**
     * Debounce utility.
     */
    debounce(fn, delay) {
        clearTimeout(this.debounceTimer);
        this.debounceTimer = setTimeout(fn, delay);
    }
};

// Expose for map integration and testing
window.DrillDown = DrillDown;
window.openDrillDown = (h3Cell, locationName) => DrillDown.open(h3Cell, locationName);

// Map load handler
map.on('load', () => {
    // Initialize drill-down drawer
    DrillDown.init();

    // Initialize mobile interactions
    initMobileInteractions();
    window.addEventListener('resize', initMobileInteractions);

    // Load PMTiles sources
    if (!loadAllSources()) {
        console.error('Failed to load PMTiles');
        return;
    }

    // Initialize legend
    updateLegend();

    // Set initial resolution
    const initialRes = getBestResolutionForZoom(map.getZoom());
    if (initialRes) {
        switchToResolution(initialRes);
    }

    // Handle zoom changes
    map.on('zoomend', () => {
        const targetRes = getBestResolutionForZoom(map.getZoom());
        if (targetRes && targetRes !== currentResolution) {
            switchToResolution(targetRes);
        }
    });
});

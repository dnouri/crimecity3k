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

    // Sweden bounding box [west, south, east, north]
    // Used for fitBounds on initial load to adapt to viewport size
    swedenBounds: [[10.0, 55.0], [24.5, 69.5]],

    // PMTiles path (relative to server root)
    tilesPath: '/data/tiles/pmtiles',

    // Tile version for cache busting (bump when tile schema changes)
    tileVersion: 3,

    // Color scale for absolute counts (red sequential)
    // Category-specific stops based on actual data distributions
    absoluteColors: {
        colors: ['#fee5d9', '#fcae91', '#fb6a4a', '#de2d26', '#a50f15', '#67000d'],
        stops: {
            all:          [0, 10, 50, 200, 500, 1500],
            traffic:      [0, 5, 20, 80, 200, 500],
            property:     [0, 5, 15, 60, 150, 400],
            violence:     [0, 2, 8, 30, 80, 200],
            narcotics:    [0, 2, 8, 30, 80, 200],
            fraud:        [0, 1, 5, 15, 40, 100],
            public_order: [0, 2, 10, 40, 100, 300],
            weapons:      [0, 1, 4, 15, 40, 100],
            other:        [0, 10, 40, 150, 400, 1000]
        }
    },

    // Color scale for normalized rates (per 10,000)
    // Category-specific stops based on actual data distributions
    normalizedColors: {
        colors: ['#fee5d9', '#fcae91', '#fb6a4a', '#de2d26', '#a50f15', '#67000d'],
        stops: {
            all:          [0, 25, 50, 100, 150, 250],
            traffic:      [0, 5, 10, 15, 25, 50],
            property:     [0, 2, 5, 10, 15, 35],
            violence:     [0, 2, 4, 6, 10, 15],
            narcotics:    [0, 1, 2, 5, 10, 15],
            fraud:        [0, 0.5, 1, 2, 3, 5],
            public_order: [0, 3, 5, 8, 12, 25],
            weapons:      [0, 0.5, 1, 2, 4, 8],
            other:        [0, 15, 30, 50, 100, 200]
        }
    },

    // Minimum population for reliable per-capita rates in normalized mode
    // Municipalities below this threshold are shown in gray
    minPopulationForNormalized: 5000,

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
let currentFilter = 'all';
let displayMode = 'absolute';
let sourceLoaded = false;

// Stats-first UI state
let currentCellData = null;  // { locationName, properties }
let viewState = 'none';      // 'none' | 'stats' | 'drawer' | 'sheet'

// Hover state for desktop municipality highlighting (stores kommun_namn)
let hoveredMunicipalityId = null;

/**
 * Check if viewport is mobile (<768px).
 */
function isMobile() {
    return window.innerWidth < 768;
}

// Make state accessible for E2E tests
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
                tileSize: 256
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
    minZoom: 3,
    attributionControl: false  // We include attribution in the legend footer
});

// Expose map for E2E tests
window.map = map;

/**
 * Get the value expression for color interpolation.
 * In absolute mode: use count field directly
 * In normalized mode: compute (count * 10000) / population
 */
function getValueExpression() {
    const countField = getCountField();

    if (displayMode === 'absolute') {
        return ['coalesce', ['get', countField], 0];
    }

    // Normalized mode: compute rate per 10,000 dynamically
    // This correctly handles category filters by using the filtered count
    return [
        '/',
        ['*', ['coalesce', ['get', countField], 0], 10000],
        ['max', ['coalesce', ['get', 'population'], 1], 1]  // Avoid division by zero
    ];
}

/**
 * Get the color expression for the current display mode and filter.
 * In normalized mode, municipalities below population threshold are shown in gray.
 */
function getColorExpression() {
    const colorConfig = getColorConfig();

    // Build base interpolate expression
    const interpolateExpr = [
        'interpolate',
        ['linear'],
        getValueExpression()
    ];

    for (let i = 0; i < colorConfig.stops.length; i++) {
        interpolateExpr.push(colorConfig.stops[i], colorConfig.colors[i]);
    }

    // In normalized mode, gray out small populations (rates are unreliable)
    if (displayMode === 'normalized') {
        return [
            'case',
            ['<', ['coalesce', ['get', 'population'], 0], CONFIG.minPopulationForNormalized],
            '#e0e0e0',  // Gray for small populations
            interpolateExpr
        ];
    }

    return interpolateExpr;
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
 * Compute rate per 10,000 for the current category filter.
 * JavaScript equivalent of getValueExpression() for normalized mode.
 * @param {object} props - Feature properties with count and population fields
 * @returns {number} - Rate per 10,000 residents
 */
function getCurrentRate(props) {
    const countField = getCountField();
    const count = props[countField] || 0;
    const population = Math.max(props.population || 1, 1);
    return (count * 10000) / population;
}

/**
 * Compute rate per 10,000 for a specific category.
 * @param {object} props - Feature properties
 * @param {string} categoryKey - Category key (e.g., 'fraud', 'violence')
 * @returns {number} - Rate per 10,000 residents
 */
function getCategoryRate(props, categoryKey) {
    const count = props[`${categoryKey}_count`] || 0;
    const population = Math.max(props.population || 1, 1);
    return (count * 10000) / population;
}

/**
 * Render category breakdown table HTML.
 * Shared between stats panel and bottom sheet.
 * @param {object} props - Feature properties with category counts
 * @param {object} options - { showTotalRow: boolean }
 * @returns {string} - HTML string for category breakdown
 */
function renderCategoryBreakdownTable(props, options = {}) {
    const { showTotalRow = false } = options;

    let html = '<div class="category-breakdown">';
    html += '<table class="category-table">';
    html += '<thead><tr>';
    html += '<th scope="col">Category</th>';
    html += '<th scope="col" class="num">Count</th>';
    html += '<th scope="col" class="num">per 10k</th>';
    html += '</tr></thead>';
    html += '<tbody>';

    let totalCount = 0;
    for (const [key, name] of Object.entries(CONFIG.categories)) {
        const count = props[`${key}_count`] || 0;
        if (count > 0) {
            totalCount += count;
            const rate = getCategoryRate(props, key);
            html += '<tr>';
            html += `<td>${name}</td>`;
            html += `<td class="num">${count.toLocaleString()}</td>`;
            html += `<td class="num">${rate.toFixed(1)}</td>`;
            html += '</tr>';
        }
    }
    html += '</tbody>';

    if (showTotalRow) {
        const totalRate = getCurrentRate(props);
        html += '<tfoot><tr class="total-row">';
        html += '<td>Total</td>';
        html += `<td class="num">${totalCount.toLocaleString()}</td>`;
        html += `<td class="num">${totalRate.toFixed(1)}</td>`;
        html += '</tr></tfoot>';
    }

    html += '</table>';
    html += '</div>';

    return html;
}

/**
 * Get color configuration for current display mode and category.
 * Single source of truth for both map paint and legend.
 */
function getColorConfig() {
    const category = currentFilter;
    const colorConfig = displayMode === 'absolute'
        ? CONFIG.absoluteColors
        : CONFIG.normalizedColors;

    const stops = colorConfig.stops[category] || colorConfig.stops.all;
    return {
        stops: stops,
        colors: colorConfig.colors
    };
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
 * Load municipality PMTiles source.
 */
function loadMunicipalitySource() {
    const sourceId = 'municipality-tiles';
    const url = `pmtiles://${CONFIG.tilesPath}/municipalities.pmtiles?v=${CONFIG.tileVersion}`;

    try {
        map.addSource(sourceId, {
            type: 'vector',
            url: url
        });
        sourceLoaded = true;
        return true;
    } catch (error) {
        console.error('Failed to load municipality PMTiles:', error);
        sourceLoaded = false;
        return false;
    }
}

/**
 * Add municipalities layer.
 */
function addMunicipalityLayer() {
    const layerId = 'municipalities';
    const sourceId = 'municipality-tiles';

    const layerConfig = {
        id: layerId,
        type: 'fill',
        source: sourceId,
        'source-layer': 'municipalities',
        paint: {
            'fill-color': getColorExpression(),
            'fill-opacity': 0.7,
            'fill-outline-color': 'rgba(0, 0, 0, 0.3)'
        }
    };

    const filterExpr = getFilterExpression();
    if (filterExpr) {
        layerConfig.filter = filterExpr;
    }

    map.addLayer(layerConfig);

    // Add hover highlight layer (line) for desktop - uses filter-based approach
    map.addLayer({
        id: 'municipalities-hover',
        type: 'line',
        source: sourceId,
        'source-layer': 'municipalities',
        paint: {
            'line-color': '#0d6efd',
            'line-width': 3
        },
        filter: ['==', ['get', 'kommun_namn'], '']  // Initially matches nothing
    });

    // Add selected highlight layer (line) - shows which municipality's details are displayed
    map.addLayer({
        id: 'municipalities-selected',
        type: 'line',
        source: sourceId,
        'source-layer': 'municipalities',
        paint: {
            'line-color': '#0d9488',  // Teal - complements red choropleth
            'line-width': 3
        },
        filter: ['==', ['get', 'kommun_namn'], '']  // Initially matches nothing
    });

    // Register event handlers once
    registerLayerEventHandlers();
}

/**
 * Register mouse/click handlers for the municipalities layer.
 */
function registerLayerEventHandlers() {
    // Cursor change on hover
    map.on('mouseenter', 'municipalities', () => {
        map.getCanvas().style.cursor = 'pointer';
    });

    map.on('mouseleave', 'municipalities', () => {
        map.getCanvas().style.cursor = '';
        // Clear hover highlight on desktop
        if (!isMobile() && hoveredMunicipalityId !== null) {
            map.setFilter('municipalities-hover', ['==', ['get', 'kommun_namn'], '']);
            hoveredMunicipalityId = null;
        }
    });

    // Track hover for highlight effect (desktop only)
    map.on('mousemove', 'municipalities', (e) => {
        if (isMobile() || e.features.length === 0) return;

        const feature = e.features[0];
        const municipalityName = feature.properties.kommun_namn;

        // Skip if no name or already hovering same municipality
        if (!municipalityName || hoveredMunicipalityId === municipalityName) return;

        // Skip hover effect if this municipality is already selected (shows orange outline)
        const isSelected = currentCellData && currentCellData.locationName === municipalityName;
        if (isSelected) {
            // Clear any previous hover
            if (hoveredMunicipalityId !== null) {
                map.setFilter('municipalities-hover', ['==', ['get', 'kommun_namn'], '']);
                hoveredMunicipalityId = null;
            }
            return;
        }

        // Update hover layer filter to highlight this municipality
        hoveredMunicipalityId = municipalityName;
        map.setFilter('municipalities-hover', ['==', ['get', 'kommun_namn'], municipalityName]);
    });

    // Click to show details
    map.on('click', 'municipalities', (e) => {
        if (e.features.length > 0) {
            showMunicipalityDetails(e.features[0].properties);
        }
    });

    // Click outside (on map, not on features) to hide details
    map.on('click', (e) => {
        const features = map.queryRenderedFeatures(e.point, { layers: ['municipalities'] });
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
 * Show municipality details panel with stats and Search Events button.
 * Does NOT auto-open drill-down drawer (stats-first flow).
 * On mobile, opens bottom sheet instead of stats panel.
 */
function showMunicipalityDetails(props) {
    // Use kommun_namn from municipality tiles
    const locationName = props.kommun_namn || 'Unknown municipality';

    // Store current cell data for later use
    currentCellData = {
        locationName: locationName,
        properties: props
    };

    // Update selected municipality outline on map
    if (map.getLayer('municipalities-selected')) {
        map.setFilter('municipalities-selected', ['==', ['get', 'kommun_namn'], locationName]);
    }

    // Mobile: use bottom sheet
    if (isMobile()) {
        BottomSheet.open(locationName, props);
        return;
    }

    // If drawer is already open, update it directly
    if (viewState === 'drawer' && DrillDown && DrillDown.isOpen()) {
        DrillDown.open(locationName, props);
        return;
    }

    const content = document.getElementById('details-content');
    const panel = document.getElementById('cell-details');

    document.getElementById('details-title').textContent = locationName;

    const population = props.population || 0;
    const isSmallPopulation = population < CONFIG.minPopulationForNormalized;

    let html = '<div class="detail-row">';
    html += '<span class="detail-label">Rate per 10k</span>';
    html += `<span class="detail-value">${getCurrentRate(props).toFixed(1)}</span>`;
    html += '</div>';

    // Warn about unreliable rates in normalized mode for small populations
    if (displayMode === 'normalized' && isSmallPopulation) {
        html += '<div class="rate-warning">';
        html += 'Rate may be unreliable due to small population';
        html += '</div>';
    }

    html += '<div class="detail-row">';
    html += '<span class="detail-label">Population</span>';
    html += `<span class="detail-value">${Math.round(population).toLocaleString()}</span>`;
    html += '</div>';

    html += renderCategoryBreakdownTable(props, { showTotalRow: true });

    html += '<div class="search-events-action">';
    html += '<button id="search-events-button" data-testid="search-events-button" class="search-events-button">';
    html += 'Search Events →';
    html += '</button>';
    html += '</div>';

    content.innerHTML = html;
    panel.classList.add('visible');
    viewState = 'stats';

    document.getElementById('search-events-button').addEventListener('click', openDrawerFromStats);
}

/**
 * Open drill-down drawer from stats view.
 */
function openDrawerFromStats() {
    if (!currentCellData || !DrillDown) return;

    // Hide stats panel
    document.getElementById('cell-details').classList.remove('visible');

    // Open drawer with location name
    DrillDown.open(
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

    // Clear selected municipality outline on map
    if (map.getLayer('municipalities-selected')) {
        map.setFilter('municipalities-selected', ['==', ['get', 'kommun_namn'], '']);
    }

    // Also close drill-down drawer if open
    if (DrillDown && DrillDown.isOpen()) {
        DrillDown.close(false);  // false = don't return to stats
    }
}

/**
 * Update legend based on current display mode and category.
 */
function updateLegend() {
    const title = document.getElementById('legend-title');
    const items = document.getElementById('legend-items');
    const colorConfig = getColorConfig();

    title.textContent = displayMode === 'absolute'
        ? 'Event Count'
        : 'Rate per 10,000';

    let html = '';
    for (let i = 0; i < colorConfig.stops.length; i++) {
        const label = i === colorConfig.stops.length - 1
            ? `${colorConfig.stops[i]}+`
            : `${colorConfig.stops[i]}-${colorConfig.stops[i + 1]}`;

        html += '<div class="legend-item">';
        html += `<div class="legend-color" style="background: ${colorConfig.colors[i]};"></div>`;
        html += `<span class="legend-label">${label}</span>`;
        html += '</div>';
    }

    // In normalized mode, add footnote about grayed-out small populations
    if (displayMode === 'normalized') {
        const threshold = (CONFIG.minPopulationForNormalized / 1000).toFixed(0);
        html += '<div class="legend-footnote">';
        html += '<div class="legend-color" style="background: #e0e0e0;"></div>';
        html += `<span class="legend-label">Pop. &lt; ${threshold}k</span>`;
        html += '</div>';
    }

    items.innerHTML = html;
}

/**
 * Update layer paint based on current settings.
 */
function updateLayerPaint() {
    if (map.getLayer('municipalities')) {
        map.setPaintProperty('municipalities', 'fill-color', getColorExpression());
    }
}

/**
 * Update layer filter based on current category.
 */
function updateLayerFilter() {
    if (!map.getLayer('municipalities')) return;

    const filterExpr = getFilterExpression();
    if (filterExpr) {
        map.setFilter('municipalities', filterExpr);
    } else {
        map.setFilter('municipalities', null);
    }
    // Note: municipalities-hover layer filter is managed by mouse events, not here

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
        displayMode === 'absolute' ? 'Count' : 'Rate';

    updateLegend();
    updateLayerPaint();
});

document.getElementById('category-filter').addEventListener('change', (e) => {
    currentFilter = e.target.value;
    updateLayerFilter();
    updateLegend();  // Legend stops change per category in normalized mode
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
        if (viewState === 'sheet' && BottomSheet && BottomSheet.isOpen()) {
            BottomSheet.close();
        } else if (viewState === 'drawer' && DrillDown && DrillDown.isOpen()) {
            DrillDown.close();  // Returns to stats view
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
    currentLocationName: null,
    cellProps: null,         // Municipality properties for header stats display
    cellTotalEvents: 0,      // Total events in municipality (for "X of Y" display)
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

        // Search on Enter key (immediate, bypasses debounce)
        this.elements.searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                // Cancel any pending debounced search
                if (this.debounceTimer) {
                    clearTimeout(this.debounceTimer);
                    this.debounceTimer = null;
                }
                // Trigger immediate search
                this.filters.search = e.target.value;
                this.currentPage = 1;
                this.fetchEvents();
                // Blur to close mobile keyboard
                e.target.blur();
            }
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
     * Open drawer for a specific municipality.
     * @param {string} locationName - Municipality name for display and API queries
     * @param {object} cellProps - Municipality properties (total_count, rate_per_10000, etc.)
     */
    open(locationName, cellProps = null) {
        // Only reset filters when opening fresh (not when switching)
        const isAlreadyOpen = this.isOpen();

        this.currentLocationName = locationName;
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
     * @param {boolean} returnToStats - If true, show stats panel again
     */
    close(returnToStats = true) {
        this.elements.drawer.classList.remove('open');

        if (returnToStats && currentCellData) {
            // Return to stats view
            document.getElementById('cell-details').classList.add('visible');
            viewState = 'stats';
        } else {
            // Full close
            this.currentLocationName = null;
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
        if (!this.currentLocationName) return;

        // Cancel any in-flight request
        if (this.abortController) {
            this.abortController.abort();
        }
        this.abortController = new AbortController();

        this.showState('loading');

        try {
            const params = new URLSearchParams({
                location_name: this.currentLocationName,
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

        const rate = this.cellProps ? getCurrentRate(this.cellProps).toFixed(1) : '0.0';
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
     * Show a specific state (loading, events, empty, error).
     */
    showState(state) {
        // Hide all states
        this.elements.loadingSpinner.classList.remove('visible');
        this.elements.eventList.classList.remove('visible');
        this.elements.emptyState.classList.remove('visible');
        this.elements.errorState.classList.remove('visible');
        this.elements.pagination.classList.remove('visible');

        switch (state) {
            case 'loading':
                this.elements.loadingSpinner.classList.add('visible');
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
window.openDrillDown = (locationName, props) => DrillDown.open(locationName, props);

// ============================================
// BOTTOM SHEET MODULE (Mobile)
// ============================================

const BottomSheet = {
    // State
    currentLocationName: null,
    cellProps: null,

    // DOM Elements (cached on init)
    elements: {},

    /**
     * Initialize bottom sheet functionality.
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
            sheet: document.getElementById('bottom-sheet'),
            closeBtn: document.getElementById('sheet-close'),
            location: document.getElementById('sheet-location'),
            content: document.getElementById('sheet-content')
        };
    },

    /**
     * Bind event listeners.
     */
    bindEvents() {
        // Close button
        this.elements.closeBtn.addEventListener('click', () => this.close());

        // Swipe-to-dismiss touch gesture
        this.bindSwipeGesture();
    },

    /**
     * Bind swipe-to-dismiss gesture for the bottom sheet.
     * Users can swipe down on the sheet handle or header to dismiss.
     */
    bindSwipeGesture() {
        const sheet = this.elements.sheet;
        let startY = 0;
        let currentY = 0;
        let isDragging = false;

        const handleTouchStart = (e) => {
            startY = e.touches[0].clientY;
            isDragging = true;
            sheet.style.transition = 'none';
        };

        const handleTouchMove = (e) => {
            if (!isDragging) return;
            currentY = e.touches[0].clientY;
            const deltaY = currentY - startY;

            // Only allow dragging down (positive delta)
            if (deltaY > 0) {
                sheet.style.transform = `translateY(${deltaY}px)`;
            }
        };

        const handleTouchEnd = () => {
            if (!isDragging) return;
            isDragging = false;
            sheet.style.transition = 'transform 0.3s ease-out';

            const deltaY = currentY - startY;
            // Dismiss if dragged more than 100px down
            if (deltaY > 100) {
                this.close();
            }
            sheet.style.transform = '';
            startY = 0;
            currentY = 0;
        };

        // Attach to sheet handle and header for swipe gesture
        const handle = sheet.querySelector('.sheet-handle');
        const header = sheet.querySelector('.sheet-header');

        [handle, header].forEach(el => {
            if (el) {
                el.addEventListener('touchstart', handleTouchStart, { passive: true });
                el.addEventListener('touchmove', handleTouchMove, { passive: true });
                el.addEventListener('touchend', handleTouchEnd, { passive: true });
            }
        });
    },

    /**
     * Open bottom sheet for a specific municipality.
     * @param {string} locationName - Municipality name for display
     * @param {object} cellProps - Municipality properties
     */
    open(locationName, cellProps = null) {
        this.currentLocationName = locationName;
        this.cellProps = cellProps;

        this.elements.location.textContent = locationName;
        this.render(cellProps);
        this.elements.sheet.classList.add('open');
        viewState = 'sheet';
    },

    /**
     * Close the bottom sheet.
     */
    close() {
        this.elements.sheet.classList.remove('open');
        this.elements.content.innerHTML = '';
        this.elements.location.textContent = '';
        this.currentLocationName = null;
        this.cellProps = null;
        viewState = 'none';
        currentCellData = null;
    },

    /**
     * Check if sheet is open.
     */
    isOpen() {
        return this.elements.sheet.classList.contains('open');
    },

    /**
     * Render content into the bottom sheet.
     * @param {object} props - Municipality properties
     */
    render(props) {
        if (!props) {
            this.elements.content.innerHTML = '<p>No data available</p>';
            return;
        }

        const population = props.population || 0;
        const rate = getCurrentRate(props).toFixed(1);
        const totalCount = props.total_count || 0;

        let html = '<div class="sheet-stats">';
        html += `<div class="stat-item"><span class="stat-value">${totalCount.toLocaleString()}</span><span class="stat-label">Events</span></div>`;
        html += `<div class="stat-item"><span class="stat-value">${rate}</span><span class="stat-label">per 10k</span></div>`;
        html += `<div class="stat-item"><span class="stat-value">${Math.round(population).toLocaleString()}</span><span class="stat-label">Population</span></div>`;
        html += '</div>';

        html += renderCategoryBreakdownTable(props, { showTotalRow: true });

        html += '<div class="sheet-actions">';
        html += '<button id="sheet-search-events" class="search-events-button" data-testid="sheet-search-events">Search Events →</button>';
        html += '</div>';

        this.elements.content.innerHTML = html;

        // Bind search events button
        document.getElementById('sheet-search-events').addEventListener('click', () => {
            // Capture values before close() clears them
            const locationName = this.currentLocationName;
            const props = this.cellProps;
            this.close();
            DrillDown.open(locationName, props);
            viewState = 'drawer';
        });
    }
};

// Expose for testing
window.BottomSheet = BottomSheet;

// Map load handler
map.on('load', () => {
    // Fit map to Sweden bounds (adapts to viewport size, especially on mobile)
    map.fitBounds(CONFIG.swedenBounds, {
        padding: { top: 20, bottom: 80, left: 20, right: 20 },
        maxZoom: CONFIG.initialZoom
    });

    // Initialize drill-down drawer
    DrillDown.init();

    // Initialize bottom sheet (mobile)
    BottomSheet.init();

    // Initialize mobile interactions
    initMobileInteractions();
    window.addEventListener('resize', initMobileInteractions);

    // Load municipality PMTiles source
    if (!loadMunicipalitySource()) {
        console.error('Failed to load municipality PMTiles');
        return;
    }

    // Initialize legend
    updateLegend();

    // Add municipality layer
    addMunicipalityLayer();

    // Fetch and display data date
    fetchDataDate();

    // Initialize info popover
    initInfoPopover();
});

// ============================================
// INFO POPOVER
// ============================================

/**
 * Fetch health endpoint and update the data date display.
 */
async function fetchDataDate() {
    try {
        const response = await fetch('/health');
        if (response.ok) {
            const data = await response.json();
            if (data.data_updated) {
                // Use ISO format (YYYY-MM-DD) - Swedish standard
                document.getElementById('data-date').textContent = `Data as of ${data.data_updated}`;
            }
        }
    } catch (e) {
        // Silently fail - data date is not critical
        console.warn('Failed to fetch data date:', e);
    }
}

/**
 * Initialize info popover toggle behavior.
 */
function initInfoPopover() {
    const button = document.getElementById('info-button');
    const popover = document.getElementById('info-popover');

    if (!button || !popover) return;

    // Toggle popover on button click
    button.addEventListener('click', (e) => {
        e.stopPropagation();
        const isHidden = popover.hidden;
        popover.hidden = !isHidden;
        button.setAttribute('aria-expanded', isHidden ? 'true' : 'false');
    });

    // Close popover when clicking outside
    document.addEventListener('click', (e) => {
        if (!popover.hidden && !popover.contains(e.target) && e.target !== button) {
            popover.hidden = true;
            button.setAttribute('aria-expanded', 'false');
        }
    });

    // Close popover on Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !popover.hidden) {
            popover.hidden = true;
            button.setAttribute('aria-expanded', 'false');
            button.focus();
        }
    });
}

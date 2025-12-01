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
    zoomToResolution: {
        3: 4,
        4: 4,
        5: 5,
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

    // Color scale for absolute counts (red sequential)
    absoluteColors: {
        stops: [0, 10, 50, 150, 500],
        colors: ['#fee5d9', '#fcae91', '#fb6a4a', '#de2d26', '#a50f15']
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

    return [
        'interpolate',
        ['linear'],
        ['coalesce', ['get', field], 0],
        colors.stops[0], colors.colors[0],
        colors.stops[1], colors.colors[1],
        colors.stops[2], colors.colors[2],
        colors.stops[3], colors.colors[3],
        colors.stops[4], colors.colors[4]
    ];
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
        const url = `pmtiles://${CONFIG.tilesPath}/h3_r${res}.pmtiles`;

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

    // Click outside to hide details
    map.on('click', (e) => {
        const features = map.queryRenderedFeatures(e.point, { layers: ['h3-cells'] });
        if (features.length === 0) {
            hideCellDetails();
        }
    });
}

/**
 * Show cell details panel.
 */
function showCellDetails(props) {
    const content = document.getElementById('details-content');
    const panel = document.getElementById('cell-details');

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

    content.innerHTML = html;
    panel.classList.add('visible');
}

/**
 * Hide cell details panel.
 */
function hideCellDetails() {
    document.getElementById('cell-details').classList.remove('visible');
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

// Map load handler
map.on('load', () => {
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

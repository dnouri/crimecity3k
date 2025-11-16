"""
Convert SCB population grid data (1km squares) to H3 hexagonal cells.

Approach:
1. Load population data in SWEREF99 TM
2. Convert to WGS84 (lat/lon)
3. For each grid cell, find which H3 cells it overlaps
4. Distribute population to H3 cells (area-weighted or simple assignment)
5. Aggregate population by H3 cell

Test different H3 resolutions (r4, r5, r6) to see what works best.
"""

import geopandas as gpd
import h3
import pandas as pd
from shapely.geometry import Polygon
import time

def h3_polygon_to_shapely(h3_index):
    """Convert H3 index to Shapely polygon."""
    boundary = h3.cell_to_boundary(h3_index)
    # H3 returns (lat, lon) tuples, need to flip to (lon, lat) for Shapely
    coords = [(lon, lat) for lat, lon in boundary]
    return Polygon(coords)

def grid_cell_to_h3_simple(row, resolution=5):
    """
    Convert a grid cell to H3 cells using simple centroid method.

    Args:
        row: GeoDataFrame row with geometry in WGS84
        resolution: H3 resolution (4-7 typical)

    Returns:
        H3 cell index
    """
    centroid = row.geometry.centroid
    lat, lon = centroid.y, centroid.x
    return h3.latlng_to_cell(lat, lon, resolution)

def grid_cell_to_h3_polygon(row, resolution=5):
    """
    Convert a grid cell to multiple H3 cells using polygon overlap.

    Args:
        row: GeoDataFrame row with geometry in WGS84
        resolution: H3 resolution

    Returns:
        Set of H3 cell indices that overlap with the grid cell
    """
    # Get H3 cells that cover this polygon
    # h3.polygon_to_cells expects (lat, lon) coordinates
    coords = row.geometry.exterior.coords
    # Convert from (lon, lat) to (lat, lon) for H3
    geojson_coords = [[(lon, lat) for lat, lon in coords]]

    try:
        h3_cells = h3.polygon_to_cells(
            {"type": "Polygon", "coordinates": geojson_coords},
            resolution
        )
        return h3_cells
    except Exception as e:
        print(f"Error converting polygon: {e}")
        # Fallback to centroid method
        return {grid_cell_to_h3_simple(row, resolution)}

def convert_population_to_h3(gdf_wgs84, resolution=5, method='centroid'):
    """
    Convert population grid to H3 cells.

    Args:
        gdf_wgs84: GeoDataFrame with population data in WGS84
        resolution: H3 resolution
        method: 'centroid' (simple, fast) or 'polygon' (accurate, slower)

    Returns:
        DataFrame with H3 cells and aggregated population
    """
    print(f"\nConverting to H3 resolution {resolution} using {method} method...")

    results = []

    # Process only non-zero population cells for efficiency
    gdf_pop = gdf_wgs84[gdf_wgs84['beftotalt'] > 0].copy()
    print(f"Processing {len(gdf_pop):,} cells with population...")

    start_time = time.time()

    for idx, row in gdf_pop.iterrows():
        if method == 'centroid':
            # Simple: assign entire population to centroid H3 cell
            h3_cell = grid_cell_to_h3_simple(row, resolution)
            results.append({
                'h3_cell': h3_cell,
                'population': row['beftotalt'],
                'female': row['kvinna'],
                'male': row['man']
            })
        else:  # polygon
            # Advanced: distribute population across overlapping H3 cells
            h3_cells = grid_cell_to_h3_polygon(row, resolution)
            # Simple equal distribution (could be area-weighted)
            pop_per_cell = row['beftotalt'] / len(h3_cells)
            female_per_cell = row['kvinna'] / len(h3_cells)
            male_per_cell = row['man'] / len(h3_cells)

            for h3_cell in h3_cells:
                results.append({
                    'h3_cell': h3_cell,
                    'population': pop_per_cell,
                    'female': female_per_cell,
                    'male': male_per_cell
                })

        # Progress indicator
        if (idx + 1) % 10000 == 0:
            elapsed = time.time() - start_time
            print(f"  Processed {idx + 1:,} cells in {elapsed:.1f}s...")

    elapsed = time.time() - start_time
    print(f"Conversion completed in {elapsed:.1f}s")

    # Convert to DataFrame and aggregate by H3 cell
    df = pd.DataFrame(results)

    print(f"\nAggregating {len(df):,} H3 assignments...")
    df_agg = df.groupby('h3_cell').agg({
        'population': 'sum',
        'female': 'sum',
        'male': 'sum'
    }).reset_index()

    print(f"Result: {len(df_agg):,} unique H3 cells")

    return df_agg

def analyze_h3_results(df_h3, resolution):
    """Analyze H3 conversion results."""
    print(f"\n{'='*80}")
    print(f"H3 RESOLUTION {resolution} ANALYSIS")
    print(f"{'='*80}")

    print(f"\nTotal H3 cells: {len(df_h3):,}")
    print(f"Total population: {df_h3['population'].sum():,.0f}")
    print(f"Mean population per cell: {df_h3['population'].mean():.1f}")
    print(f"Median population per cell: {df_h3['population'].median():.1f}")
    print(f"Max population per cell: {df_h3['population'].max():,.0f}")

    # Cell size info
    sample_cell = df_h3.iloc[0]['h3_cell']
    area_km2 = h3.cell_area(sample_cell, unit='km^2')
    print(f"\nApproximate H3 cell area: {area_km2:.2f} km²")

    # Population distribution
    print("\nPopulation distribution:")
    print(f"  < 100: {(df_h3['population'] < 100).sum():,} cells")
    print(f"  100-1000: {((df_h3['population'] >= 100) & (df_h3['population'] < 1000)).sum():,} cells")
    print(f"  1000-10000: {((df_h3['population'] >= 1000) & (df_h3['population'] < 10000)).sum():,} cells")
    print(f"  > 10000: {(df_h3['population'] >= 10000).sum():,} cells")

    # Sample data
    print("\nSample H3 cells:")
    sample = df_h3.nlargest(10, 'population')
    for _, row in sample.iterrows():
        lat, lon = h3.cell_to_latlng(row['h3_cell'])
        print(f"  {row['h3_cell']}: population={row['population']:,.0f}, lat={lat:.4f}, lon={lon:.4f}")

def main():
    print("="*80)
    print("CONVERT POPULATION GRID TO H3 CELLS")
    print("="*80)

    # Load population data
    print("\nLoading population data...")
    gdf = gpd.read_file('tmp/population_1km_2024.gpkg')
    print(f"Loaded {len(gdf):,} grid cells")
    print(f"Original CRS: {gdf.crs}")

    # Convert to WGS84
    print("\nConverting to WGS84...")
    gdf_wgs84 = gdf.to_crs(epsg=4326)
    print(f"New CRS: {gdf_wgs84.crs}")

    # Test different H3 resolutions with centroid method (faster)
    resolutions_to_test = [4, 5, 6]

    results = {}

    for res in resolutions_to_test:
        df_h3 = convert_population_to_h3(gdf_wgs84, resolution=res, method='centroid')
        analyze_h3_results(df_h3, res)
        results[res] = df_h3

        # Save to file
        output_file = f'tmp/population_h3_r{res}.parquet'
        df_h3.to_parquet(output_file)
        print(f"\nSaved to: {output_file}")

    # Compare resolutions
    print("\n" + "="*80)
    print("RESOLUTION COMPARISON")
    print("="*80)

    comparison = []
    for res, df in results.items():
        sample_cell = df.iloc[0]['h3_cell']
        area_km2 = h3.cell_area(sample_cell, unit='km^2')
        comparison.append({
            'Resolution': res,
            'H3 Cells': len(df),
            'Cell Area (km²)': f"{area_km2:.2f}",
            'Avg Pop/Cell': f"{df['population'].mean():.0f}",
            'Max Pop/Cell': f"{df['population'].max():.0f}"
        })

    df_compare = pd.DataFrame(comparison)
    print("\n" + df_compare.to_string(index=False))

    print("\n" + "="*80)
    print("RECOMMENDATION")
    print("="*80)
    print("\nFor crime visualization:")
    print("  - Resolution 4: Very coarse (252 km²) - good for national overview")
    print("  - Resolution 5: Coarse (90 km²) - good for regional patterns")
    print("  - Resolution 6: Medium (32 km²) - good balance for Sweden")
    print("  - Resolution 7+: Fine (<12 km²) - city-level detail")
    print("\nSuggested: Start with r5 or r6 depending on your crime event resolution")

if __name__ == "__main__":
    main()

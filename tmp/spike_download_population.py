"""
Download SCB population grid data (1km resolution) for Sweden.

Data source: SCB Open Geodata
URL: https://www.scb.se/en/services/open-data-api/open-geodata/grid-statistics/
Latest year: 2024
Format: GeoPackage
Coordinate System: SWEREF99 TM (EPSG:3006)
"""

import requests
from pathlib import Path
import geopandas as gpd
import time

def download_population_grid(year=2024, output_dir="tmp"):
    """
    Download population grid data from SCB via WFS.

    Args:
        year: Year of data (2015-2024 available)
        output_dir: Directory to save downloaded file

    Returns:
        Path to downloaded file
    """
    print(f"Downloading SCB population grid data for {year}...")

    # Construct WFS download URL
    wfs_url = (
        f"https://geodata.scb.se/geoserver/stat/wfs"
        f"?service=WFS"
        f"&REQUEST=GetFeature"
        f"&version=1.1.0"
        f"&TYPENAMES=stat:befolkning_1km_{year}"
        f"&outputFormat=geopackage"
    )

    # Set up output path
    output_path = Path(output_dir) / f"population_1km_{year}.gpkg"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Download file
    print(f"Downloading from: {wfs_url}")
    print(f"Saving to: {output_path}")

    start_time = time.time()

    response = requests.get(wfs_url, stream=True, timeout=300)
    response.raise_for_status()

    total_size = int(response.headers.get('content-length', 0))
    print(f"File size: {total_size / (1024*1024):.2f} MB")

    with open(output_path, 'wb') as f:
        downloaded = 0
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                progress = (downloaded / total_size) * 100
                print(f"Progress: {progress:.1f}%", end='\r')

    elapsed = time.time() - start_time
    print(f"\nDownload completed in {elapsed:.1f} seconds")

    return output_path

def explore_population_data(gpkg_path):
    """
    Explore the structure and contents of population grid data.

    Args:
        gpkg_path: Path to GeoPackage file
    """
    print("\n" + "=" * 80)
    print("EXPLORING POPULATION DATA")
    print("=" * 80)

    # Read GeoPackage
    print(f"\nReading: {gpkg_path}")
    gdf = gpd.read_file(gpkg_path)

    # Basic info
    print(f"\nRows: {len(gdf):,}")
    print(f"Columns: {list(gdf.columns)}")
    print(f"CRS: {gdf.crs}")
    print(f"Geometry type: {gdf.geometry.type.unique()}")

    # Data preview
    print("\nFirst 5 rows:")
    print(gdf.head())

    # Summary statistics
    print("\nData summary:")
    print(gdf.describe())

    # Population distribution
    if 'beftotalt' in gdf.columns:  # Total population column
        total_pop = gdf['beftotalt'].sum()
        print(f"\nTotal population in dataset: {total_pop:,}")
        print(f"Cells with population > 0: {(gdf['beftotalt'] > 0).sum():,}")
        print(f"Cells with population = 0: {(gdf['beftotalt'] == 0).sum():,}")
        print(f"Max population in a cell: {gdf['beftotalt'].max():,}")
        print(f"Mean population per cell (non-zero): {gdf[gdf['beftotalt'] > 0]['beftotalt'].mean():.1f}")

    # Bounding box
    bounds = gdf.total_bounds
    print(f"\nBounding box (SWEREF99 TM):")
    print(f"  Min X: {bounds[0]:,.0f}")
    print(f"  Min Y: {bounds[1]:,.0f}")
    print(f"  Max X: {bounds[2]:,.0f}")
    print(f"  Max Y: {bounds[3]:,.0f}")

    # Sample data
    print("\nSample of non-zero population cells:")
    sample = gdf[gdf['beftotalt'] > 0].head(10)
    if len(sample) > 0:
        for idx, row in sample.iterrows():
            print(f"  Cell: {row.get('rutid_scb', 'N/A')}, Population: {row.get('beftotalt', 'N/A')}")

    return gdf

def test_coordinate_conversion(gdf):
    """
    Test conversion from SWEREF99 TM to WGS84.

    Args:
        gdf: GeoDataFrame with population data
    """
    print("\n" + "=" * 80)
    print("TESTING COORDINATE CONVERSION")
    print("=" * 80)

    print(f"\nOriginal CRS: {gdf.crs}")

    # Convert to WGS84
    print("Converting to WGS84 (EPSG:4326)...")
    gdf_wgs84 = gdf.to_crs(epsg=4326)

    print(f"New CRS: {gdf_wgs84.crs}")

    # Show sample coordinates
    print("\nSample coordinate conversion:")
    for i in range(min(5, len(gdf))):
        orig_geom = gdf.iloc[i].geometry
        new_geom = gdf_wgs84.iloc[i].geometry

        print(f"\n  Cell {i+1}:")
        print(f"    SWEREF99 TM: centroid at ({orig_geom.centroid.x:.2f}, {orig_geom.centroid.y:.2f})")
        print(f"    WGS84:       centroid at ({new_geom.centroid.x:.6f}°, {new_geom.centroid.y:.6f}°)")

    # Show bounding box in WGS84
    bounds = gdf_wgs84.total_bounds
    print(f"\nBounding box (WGS84):")
    print(f"  Min Lon: {bounds[0]:.6f}°")
    print(f"  Min Lat: {bounds[1]:.6f}°")
    print(f"  Max Lon: {bounds[2]:.6f}°")
    print(f"  Max Lat: {bounds[3]:.6f}°")

    return gdf_wgs84

def main():
    print("=" * 80)
    print("SCB POPULATION GRID DATA DOWNLOAD AND EXPLORATION")
    print("=" * 80)

    try:
        # Download data
        gpkg_path = download_population_grid(year=2024, output_dir="tmp")

        # Explore data
        gdf = explore_population_data(gpkg_path)

        # Test coordinate conversion
        gdf_wgs84 = test_coordinate_conversion(gdf)

        print("\n" + "=" * 80)
        print("SUCCESS")
        print("=" * 80)
        print(f"\nPopulation data downloaded and ready for H3 conversion.")
        print(f"File: {gpkg_path}")
        print(f"Next step: Convert to H3 cells")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

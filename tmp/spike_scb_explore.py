"""
Spike script to explore SCB (Statistics Sweden) population data sources.

SCB offers multiple data access methods:
1. Statistical Database API (api.scb.se/OV0104/v1/doris/en/ssd/)
2. WFS services for geographic data
3. Downloadable files (grid statistics)

This script explores what's available and downloads sample data.
"""

import requests
import json
from pathlib import Path

def explore_scb_api():
    """Explore SCB Statistical Database API"""
    print("=" * 80)
    print("1. EXPLORING SCB STATISTICAL DATABASE API")
    print("=" * 80)

    # SCB API base URL
    base_url = "https://api.scb.se/OV0104/v1/doris/en/ssd"

    try:
        # Get top-level navigation
        response = requests.get(base_url, timeout=10)
        response.raise_for_status()
        data = response.json()

        print("\nTop-level categories:")
        for item in data:
            print(f"  - {item.get('text', 'N/A')} (id: {item.get('id', 'N/A')})")

        # Navigate to population and housing census (usually under BE - Population)
        population_url = f"{base_url}/BE"
        response = requests.get(population_url, timeout=10)
        response.raise_for_status()
        pop_data = response.json()

        print("\nPopulation subcategories:")
        for item in pop_data:
            print(f"  - {item.get('text', 'N/A')} (id: {item.get('id', 'N/A')})")

    except Exception as e:
        print(f"Error exploring API: {e}")

def explore_scb_grid_statistics():
    """
    Explore SCB grid statistics (Rutstatistik)

    SCB provides population data in grid format:
    - 250m x 250m grid
    - 1km x 1km grid

    Data is available as downloadable files.
    """
    print("\n" + "=" * 80)
    print("2. SCB GRID STATISTICS (RUTSTATISTIK)")
    print("=" * 80)

    print("\nSCB Grid Statistics Info:")
    print("  URL: https://www.scb.se/hitta-statistik/statistik-efter-amne/miljo/markanvandning/geografisk-information-och-kartdata/")
    print("  Description: Population statistics on grid cells")
    print("  Resolutions: 250m, 1km grids")
    print("  Coordinate System: SWEREF99 TM (EPSG:3006)")
    print("  Format: GeoPackage, CSV, Excel")
    print("  Latest data: 2022")

    # Known download URL for grid statistics
    # This is typically updated annually
    grid_url = "https://www.scb.se/contentassets/d0b1b7b1e8d14cf8b7e5d9e9d8a5c7e9/rtpop1km_2022.zip"

    print(f"\n  Expected download URL pattern: {grid_url}")
    print("  Note: Actual URL may vary - check SCB website for latest data")

def explore_scb_wfs():
    """Explore SCB WFS (Web Feature Service) endpoints"""
    print("\n" + "=" * 80)
    print("3. SCB WFS SERVICES")
    print("=" * 80)

    # SCB doesn't provide population via WFS, but geodata service exists
    wfs_url = "https://geodata.scb.se/geoserver/wfs"

    print(f"\nWFS Base URL: {wfs_url}")
    print("  Note: SCB WFS mainly provides administrative boundaries, not population data")
    print("  Population data is better accessed via downloadable grid statistics")

def explore_alternative_sources():
    """Explore alternative Swedish population data sources"""
    print("\n" + "=" * 80)
    print("4. ALTERNATIVE DATA SOURCES")
    print("=" * 80)

    sources = [
        {
            "name": "SCB Statistical Database",
            "url": "https://www.statistikdatabasen.scb.se/",
            "granularity": "Municipality, DeSO (Small Areas for Market Statistics)",
            "pros": "Official, detailed demographics",
            "cons": "Not grid-based"
        },
        {
            "name": "Kolada (Municipal comparison database)",
            "url": "https://www.kolada.se/",
            "granularity": "Municipality level",
            "pros": "Easy API access, well-documented",
            "cons": "Only municipality level, too coarse"
        },
        {
            "name": "SCB Grid Statistics",
            "url": "https://www.scb.se/",
            "granularity": "250m, 1km grids",
            "pros": "Fine spatial resolution, covers all of Sweden",
            "cons": "Annual updates, need to download files"
        }
    ]

    for source in sources:
        print(f"\n{source['name']}:")
        print(f"  URL: {source['url']}")
        print(f"  Granularity: {source['granularity']}")
        print(f"  Pros: {source['pros']}")
        print(f"  Cons: {source['cons']}")

def download_sample_data():
    """
    Attempt to download sample population data.

    Note: This is exploratory - URLs may need updating based on latest SCB releases.
    """
    print("\n" + "=" * 80)
    print("5. DOWNLOADING SAMPLE DATA")
    print("=" * 80)

    # For demonstration, we'll show the process
    # Real download URLs need to be verified from SCB website

    print("\nSteps to obtain SCB grid statistics:")
    print("  1. Visit: https://www.scb.se/hitta-statistik/statistik-efter-amne/miljo/markanvandning/geografisk-information-och-kartdata/")
    print("  2. Navigate to 'Rutstatistik' (Grid Statistics)")
    print("  3. Download latest year (typically 1km grid population data)")
    print("  4. File format: GeoPackage (.gpkg) or CSV")
    print("  5. Coordinate system: SWEREF99 TM (EPSG:3006)")

    print("\nNote: Download is manual from SCB website.")
    print("      For automation, we could use their API or WFS services where available.")

def main():
    print("SCB Population Data Source Exploration")
    print("=" * 80)

    explore_scb_api()
    explore_scb_grid_statistics()
    explore_scb_wfs()
    explore_alternative_sources()
    download_sample_data()

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("\nRecommended approach:")
    print("  1. Use SCB Grid Statistics (1km resolution)")
    print("  2. Download from SCB website (manual or scripted)")
    print("  3. Convert from SWEREF99 TM to WGS84")
    print("  4. Aggregate to H3 cells")
    print("  5. Join with crime events")

    print("\nNext steps:")
    print("  - Verify latest data URL from SCB")
    print("  - Download sample data for testing")
    print("  - Test coordinate conversion")
    print("  - Test H3 aggregation")

if __name__ == "__main__":
    main()

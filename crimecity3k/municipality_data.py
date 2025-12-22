"""Municipality data download and processing for Phase 6.

Downloads Swedish municipality boundaries from okfse/sweden-geojson and
population data from SCB (Statistics Sweden) API.

Data Sources:
- Boundaries: https://github.com/okfse/sweden-geojson (CC0 license)
- Population: SCB FolkmangdNov table via PX-Web API

Key functions:
- download_municipality_boundaries(): Get GeoJSON with 290 municipality polygons
- download_population_data(): Get 2024 population by municipality from SCB
- normalize_name(): Case-insensitive name normalization for matching
"""

import json
import logging
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# URLs for data sources
GEOJSON_URL = (
    "https://raw.githubusercontent.com/okfse/sweden-geojson/"
    "refs/heads/master/swedish_municipalities.geojson"
)
SCB_API_URL = "https://api.scb.se/OV0104/v1/doris/sv/ssd/START/BE/BE0101/BE0101A/FolkmangdNov"


def normalize_name(name: str) -> str:
    """Normalize municipality name for case-insensitive matching.

    Handles known case differences between event location_names and
    GeoJSON kom_namn values (e.g., "Dals-Ed" vs "Dals-ed").

    Args:
        name: Municipality name to normalize

    Returns:
        Lowercase normalized name
    """
    return name.lower()


def download_municipality_boundaries() -> dict[str, Any]:
    """Download Swedish municipality boundaries GeoJSON.

    Downloads from okfse/sweden-geojson GitHub repository. The GeoJSON
    contains 290 municipality features with properties:
    - id: kommun_kod (4-digit code like "0114")
    - kom_namn: municipality name
    - lan_code: county code (2-digit)
    - geo_point_2d: centroid [lat, lon]

    Returns:
        GeoJSON FeatureCollection dict

    Raises:
        urllib.error.URLError: If download fails
    """
    logger.info(f"Downloading municipality boundaries from {GEOJSON_URL}")

    with urllib.request.urlopen(GEOJSON_URL, timeout=30) as response:
        data: dict[str, Any] = json.load(response)

    feature_count = len(data.get("features", []))
    logger.info(f"Downloaded {feature_count} municipality features")

    return data


def download_population_data(year: str = "2024") -> list[dict[str, Any]]:
    """Download population by municipality from SCB.

    Uses SCB's PX-Web API to query the FolkmangdNov table (population as
    of November 1st). Returns total population (both sexes, all ages)
    for each of 290 municipalities.

    Args:
        year: Year for population data (default: "2024")

    Returns:
        List of dicts with kommun_kod, kommun_namn, and population

    Raises:
        urllib.error.URLError: If download fails
        ValueError: If API returns unexpected data
    """
    logger.info(f"Fetching SCB population metadata from {SCB_API_URL}")

    # First, get metadata to find municipality codes
    with urllib.request.urlopen(SCB_API_URL, timeout=30) as response:
        metadata = json.load(response)

    # Extract municipality codes (4-digit) and their names
    region_var = metadata["variables"][0]
    region_codes = [v for v in region_var["values"] if len(v) == 4]
    region_names = {
        code: name
        for code, name in zip(region_var["values"], region_var["valueTexts"], strict=False)
        if len(code) == 4
    }

    logger.info(f"Found {len(region_codes)} municipality codes")

    # Build query for all municipalities, total age, both sexes, specified year
    query = {
        "query": [
            {
                "code": "Region",
                "selection": {"filter": "item", "values": region_codes},
            },
            {
                "code": "Alder",
                "selection": {"filter": "item", "values": ["tot"]},
            },
            {
                "code": "Kon",
                "selection": {"filter": "item", "values": ["1", "2"]},
            },
            {
                "code": "ContentsCode",
                "selection": {"filter": "item", "values": ["BE0101A9"]},
            },
            {
                "code": "Tid",
                "selection": {"filter": "item", "values": [year]},
            },
        ],
        "response": {"format": "json"},
    }

    logger.info(f"Querying SCB API for {year} population data...")

    req = urllib.request.Request(
        SCB_API_URL,
        data=json.dumps(query).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(req, timeout=120) as response:
        data = json.load(response)

    # Parse response: each row has kommune_kod, age, sex, year as key,
    # and population as value. We need to sum male + female per municipality.
    population_by_code: dict[str, int] = {}

    for row in data["data"]:
        kommun_kod = row["key"][0]
        population = int(row["values"][0])
        population_by_code[kommun_kod] = population_by_code.get(kommun_kod, 0) + population

    # Build result list
    result = [
        {
            "kommun_kod": code,
            "kommun_namn": region_names.get(code, ""),
            "population": pop,
        }
        for code, pop in population_by_code.items()
    ]

    total_pop = sum(r["population"] for r in result)
    logger.info(f"Downloaded population for {len(result)} municipalities, total: {total_pop:,}")

    return result


def save_municipality_data(output_dir: Path) -> tuple[Path, Path]:
    """Download and save municipality boundaries and population data.

    Creates:
    - {output_dir}/boundaries.geojson: Municipality polygons
    - {output_dir}/population.csv: Population by municipality

    Args:
        output_dir: Directory to save files

    Returns:
        Tuple of (boundaries_path, population_path)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Download and save boundaries
    boundaries = download_municipality_boundaries()
    boundaries_path = output_dir / "boundaries.geojson"
    with open(boundaries_path, "w", encoding="utf-8") as f:
        json.dump(boundaries, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved boundaries to {boundaries_path}")

    # Download and save population
    population = download_population_data()
    population_path = output_dir / "population.csv"
    with open(population_path, "w", encoding="utf-8") as f:
        f.write("kommun_kod,kommun_namn,population\n")
        for row in population:
            f.write(f"{row['kommun_kod']},{row['kommun_namn']},{row['population']}\n")
    logger.info(f"Saved population to {population_path}")

    return boundaries_path, population_path


def create_name_mapping(
    geojson_data: dict[str, Any],
) -> dict[str, dict[str, str]]:
    """Create mapping from normalized names to official names and codes.

    Args:
        geojson_data: GeoJSON FeatureCollection from download_municipality_boundaries()

    Returns:
        Dict mapping normalized names to {"kommun_kod": ..., "kommun_namn": ...}
    """
    mapping = {}
    for feature in geojson_data["features"]:
        props = feature["properties"]
        normalized = normalize_name(props["kom_namn"])
        mapping[normalized] = {
            "kommun_kod": props["id"],
            "kommun_namn": props["kom_namn"],
        }
    return mapping


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    output_dir = Path("data/municipalities")
    save_municipality_data(output_dir)

"""Event type definitions loaded from TOML.

Provides lookups for Swedish→English translation and Swedish→category mapping.
Single source of truth for all event type metadata.

Usage:
    from crimecity3k.event_types import (
        get_category,
        get_english,
        get_category_types,
        CATEGORIES,
    )

    category = get_category("Stöld")  # "property"
    english = get_english("Stöld")    # "Theft"
    types = get_category_types()      # {"property": ["Stöld", ...], ...}
"""

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import TypedDict


class EventTypeInfo(TypedDict):
    """Type info for a single event type."""

    english: str
    category: str


# All valid categories
CATEGORIES: list[str] = [
    "traffic",
    "property",
    "violence",
    "narcotics",
    "fraud",
    "public_order",
    "weapons",
    "other",
]


def _find_toml_path() -> Path:
    """Find the event_types.toml file.

    Searches relative to this module, then relative to CWD.
    """
    # Relative to this module (for installed package)
    module_path = Path(__file__).parent.parent / "data" / "event_types.toml"
    if module_path.exists():
        return module_path

    # Relative to CWD (for development)
    cwd_path = Path("data/event_types.toml")
    if cwd_path.exists():
        return cwd_path

    raise FileNotFoundError("event_types.toml not found. Expected at data/event_types.toml")


@lru_cache(maxsize=1)
def _load_event_types() -> dict[str, EventTypeInfo]:
    """Load event types from TOML file (cached)."""
    toml_path = _find_toml_path()
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    event_types: dict[str, EventTypeInfo] = data.get("event_types", {})
    return event_types


def get_category(event_type: str) -> str:
    """Get category for a Swedish event type.

    Args:
        event_type: Swedish event type string (e.g., "Stöld")

    Returns:
        Category name. Returns "other" for unknown types.
    """
    event_types = _load_event_types()
    info = event_types.get(event_type)
    if info:
        return info["category"]
    return "other"


def get_english(event_type: str) -> str:
    """Get English translation for a Swedish event type.

    Args:
        event_type: Swedish event type string (e.g., "Stöld")

    Returns:
        English translation. Returns the Swedish if not found.
    """
    event_types = _load_event_types()
    info = event_types.get(event_type)
    if info:
        return info["english"]
    return event_type  # Fallback to Swedish


def get_all_types() -> dict[str, EventTypeInfo]:
    """Get all event types with their info.

    Returns:
        Dict mapping Swedish type to {english, category}.
    """
    return _load_event_types().copy()


def get_category_types() -> dict[str, list[str]]:
    """Get types grouped by category.

    Returns:
        Dict mapping category name to list of Swedish event types.
    """
    event_types = _load_event_types()
    result: dict[str, list[str]] = {cat: [] for cat in CATEGORIES}

    for swedish, info in event_types.items():
        category = info["category"]
        if category in result:
            result[category].append(swedish)

    # Sort types within each category
    for types in result.values():
        types.sort()

    return result


def get_category_types_bilingual() -> dict[str, list[dict[str, str]]]:
    """Get types grouped by category with both languages.

    Returns:
        Dict mapping category to list of {se, en} dicts.
    """
    event_types = _load_event_types()
    result: dict[str, list[dict[str, str]]] = {cat: [] for cat in CATEGORIES}

    for swedish, info in event_types.items():
        category = info["category"]
        if category in result:
            result[category].append(
                {
                    "se": swedish,
                    "en": info["english"],
                }
            )

    # Sort by English name within each category
    for types in result.values():
        types.sort(key=lambda t: t["en"])

    return result

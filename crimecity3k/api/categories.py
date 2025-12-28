"""Event category definitions and type mappings.

Thin wrapper around crimecity3k.event_types for API compatibility.
The single source of truth is data/event_types.toml, loaded by event_types.py.

Categories:
- traffic: Road accidents, traffic violations, drunk driving
- property: Theft, burglary, robbery, vandalism
- violence: Assault, threats, murder, sexual crimes
- narcotics: Drug-related offenses
- fraud: Financial crimes, forgery, elder fraud
- public_order: Public disturbances, fire, alcohol violations
- weapons: Weapons and knife law violations
- other: Police activities, rescues, misc events
"""

from crimecity3k.event_types import (
    CATEGORIES,
    get_all_types,
    get_category,
    get_category_types,
    get_category_types_bilingual,
    get_english,
)

# Re-export for backwards compatibility
__all__ = [
    "CATEGORY_TYPES",
    "TYPE_TO_CATEGORY",
    "get_category",
    "get_all_categories",
    "get_english",
    "get_category_types_bilingual",
]

# Backwards compatible: category → list of Swedish types
CATEGORY_TYPES: dict[str, list[str]] = get_category_types()

# Backwards compatible: type → category (reverse mapping)
TYPE_TO_CATEGORY: dict[str, str] = {
    swedish: info["category"] for swedish, info in get_all_types().items()
}


def get_all_categories() -> list[str]:
    """Get all category names in display order.

    Returns:
        List of category names including 'other'.
    """
    return CATEGORIES.copy()

"""Event category definitions and type mappings.

Mirrors the category mapping in crimecity3k/sql/h3_aggregation.sql.
This is the single source of truth for category→type relationships
used by the API. The SQL uses the same definitions for aggregation.

Categories:
- traffic: Road accidents, traffic violations, drunk driving
- property: Theft, burglary, robbery, vandalism
- violence: Assault, threats, murder
- narcotics: Drug-related offenses
- fraud: Financial crimes
- public_order: Public disturbances, alcohol violations
- weapons: Weapons law violations
- other: All remaining event types
"""

# Category → list of event types
# Must stay in sync with h3_aggregation.sql CASE statement
CATEGORY_TYPES: dict[str, list[str]] = {
    "traffic": [
        "Trafikolycka, personskada",
        "Trafikolycka, smitning",
        "Trafikolycka, singel",
        "Trafikolycka, övrigt",
        "Trafikbrott, övriga",
        "Rattfylleri",
        "Olovlig körning",
    ],
    "property": [
        "Stöld",
        "Stöld/inbrott",
        "Tillgrepp, stöld",
        "Inbrott",
        "Skadegörelse",
        "Rån",
        "Rån, övrigt",
        "Rån väpnat",
    ],
    "violence": [
        "Misshandel",
        "Misshandel, grov",
        "Våld/hot mot tjänsteman",
        "Våldtäkt",
        "Våldtäkt, försök",
        "Mord/dråp, försök",
        "Mord/dråp",
    ],
    "narcotics": [
        "Narkotikabrott",
    ],
    "fraud": [
        "Bedrägeri",
        "Bedrägeri, ocker",
    ],
    "public_order": [
        "Ordningslagen",
        "Fylleri",
        "Ofredande/förargelse",
        "Brand",
        "Alkohollagen",
        "Övriga brott mot person",
    ],
    "weapons": [
        "Vapenlagen",
    ],
    # 'other' is the catch-all for types not in above categories
    # We don't enumerate them here - they're determined at runtime
}

# Reverse mapping: type → category (for fast lookup)
TYPE_TO_CATEGORY: dict[str, str] = {}
for category, types in CATEGORY_TYPES.items():
    for event_type in types:
        TYPE_TO_CATEGORY[event_type] = category


def get_category(event_type: str) -> str:
    """Get category for an event type.

    Args:
        event_type: Swedish event type string (e.g., "Stöld")

    Returns:
        Category name. Returns "other" for unknown types.
    """
    return TYPE_TO_CATEGORY.get(event_type, "other")


def get_all_categories() -> list[str]:
    """Get all category names in display order.

    Returns:
        List of category names including 'other'.
    """
    return list(CATEGORY_TYPES.keys()) + ["other"]

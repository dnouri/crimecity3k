# Event Type Mapping Analysis

## Executive Summary

Currently **62% of events fall into "other"** due to incomplete category mappings. This analysis proposes a complete mapping of all 87 event types with English translations.

## Current Architecture

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│ categories.py       │────▶│ municipality_agg.sql │────▶│ events.parquet  │
│ (Python: API)       │     │ (SQL: aggregation)   │     │ (category_count)│
└─────────────────────┘     └──────────────────────┘     └─────────────────┘
         │                                                        │
         ▼                                                        ▼
┌─────────────────────┐                                 ┌─────────────────┐
│ /api/types          │────────────────────────────────▶│ Frontend (JS)   │
│ (returns Swedish)   │                                 │ displays Swedish│
└─────────────────────┘                                 └─────────────────┘
```

**Problem**: Two sources of truth (Python + SQL) that must stay in sync, no English translations.

## Proposed Architecture

Single source of truth in Python with both Swedish and English:

```python
# categories.py - NEW structure
EVENT_TYPES: dict[str, EventTypeInfo] = {
    "Stöld": EventTypeInfo(
        english="Theft",
        category="property",
    ),
    "Misshandel": EventTypeInfo(
        english="Assault",
        category="violence",
    ),
    # ... all 87 types
}
```

SQL generated from Python, frontend receives both languages from API.

---

## Complete Event Type Inventory (87 types)

### ✅ Currently Mapped Correctly (32 types)

| Swedish | English | Category | Count |
|---------|---------|----------|-------|
| Rattfylleri | Drunk Driving | traffic | 4,001 |
| Trafikolycka, personskada | Traffic Accident, Injury | traffic | 2,095 |
| Trafikolycka, singel | Traffic Accident, Single Vehicle | traffic | 809 |
| Olovlig körning | Unlicensed Driving | traffic | 461 |
| Stöld | Theft | property | 2,497 |
| Stöld/inbrott | Theft/Burglary | property | 1,271 |
| Skadegörelse | Vandalism | property | 1,135 |
| Rån | Robbery | property | 1,100 |
| Inbrott | Burglary | property | 375 |
| Rån väpnat | Armed Robbery | property | 54 |
| Misshandel | Assault | violence | 3,124 |
| Mord/dråp, försök | Attempted Murder | violence | 886 |
| Misshandel, grov | Aggravated Assault | violence | 711 |
| Våld/hot mot tjänsteman | Violence/Threats Against Official | violence | 429 |
| Mord/dråp | Murder/Manslaughter | violence | 359 |
| Våldtäkt | Rape | violence | 146 |
| Våldtäkt, försök | Attempted Rape | violence | 20 |
| Brand | Fire | public_order | 4,407 |
| Ofredande/förargelse | Harassment/Disturbance | public_order | 198 |
| Ordningslagen | Public Order Act | public_order | 67 |
| Alkohollagen | Alcohol Act Violation | public_order | 41 |
| Narkotikabrott | Drug Offense | narcotics | 902 |
| Bedrägeri | Fraud | fraud | 624 |
| Vapenlagen | Weapons Act Violation | weapons | 305 |

### ⚠️ Should Be Remapped (21 types, 21,356 events)

| Swedish | English | Current | Should Be | Count |
|---------|---------|---------|-----------|-------|
| **Trafikolycka** | **Traffic Accident** | other | **traffic** | **10,434** |
| **Trafikkontroll** | **Traffic Control** | other | **traffic** | **4,068** |
| Trafikbrott | Traffic Offense | other | traffic | 1,606 |
| Trafikolycka, vilt | Traffic Accident, Wildlife | other | traffic | 1,028 |
| Trafikolycka, smitning från | Hit and Run | other | traffic | 272 |
| Trafikhinder | Traffic Obstruction | other | traffic | 247 |
| Fylleri/LOB | Public Intoxication | other | public_order | 1,167 |
| Brand automatlarm | Fire, Automatic Alarm | other | public_order | 10 |
| Motorfordon, stöld | Motor Vehicle Theft | other | property | 270 |
| Stöld, försök | Attempted Theft | other | property | 236 |
| Rån, försök | Attempted Robbery | other | property | 172 |
| Motorfordon, anträffat stulet | Stolen Vehicle Found | other | property | 117 |
| Rån övrigt | Other Robbery | other | property | 99 |
| Inbrott, försök | Attempted Burglary | other | property | 69 |
| Olaga hot | Unlawful Threat | other | violence | 506 |
| Bråk | Fight/Brawl | other | violence | 378 |
| Sedlighetsbrott | Sexual Offense | other | violence | 81 |
| Vållande till kroppsskada | Causing Bodily Harm | other | violence | 63 |
| Sexualbrott | Sexual Crime | other | violence | 56 |
| Olaga frihetsberövande/människorov | Unlawful Detention/Kidnapping | other | violence | 26 |
| Mordbrand | Arson | other | violence | 20 |
| Knivlagen | Knife Act Violation | other | weapons | 441 |
| Åldringsbrott | Elder Abuse/Fraud | other | fraud | 178 |
| Ekobrott | Economic Crime | other | fraud | 12 |
| Missbruk av urkund | Document Fraud | other | fraud | 11 |
| Förfalskningsbrott | Forgery | other | fraud | 4 |
| Sabotage mot blåljusverksamhet | Sabotage Against Emergency Services | other | public_order | 26 |

### 📋 Correctly Stays in "Other" (34 types)

These are police activities, not categorizable crimes:

| Swedish | English | Count | Reason |
|---------|---------|-------|--------|
| Övrigt | Other/Miscellaneous | 3,941 | Catch-all |
| Arbetsplatsolycka | Workplace Accident | 1,218 | Not crime |
| Försvunnen person | Missing Person | 915 | Not crime |
| Kontroll person/fordon | Person/Vehicle Check | 372 | Police activity |
| Farligt föremål, misstänkt | Suspected Dangerous Object | 367 | Investigation |
| Fjällräddning | Mountain Rescue | 310 | Rescue operation |
| Djur | Animal-related | 274 | Various |
| Räddningsinsats | Rescue Operation | 235 | Not crime |
| Olaga intrång | Trespassing | 212 | Could be property? |
| Anträffad död | Body Found | 208 | Not crime |
| Explosion | Explosion | 187 | Could be violence? |
| Skottlossning | Shooting | 164 | Could be violence? |
| Polisinsats/kommendering | Police Operation | 124 | Police activity |
| Detonation | Detonation | 116 | Could be violence? |
| Larm Inbrott | Burglary Alarm | 102 | Alarm, not confirmed |
| Häleri | Receiving Stolen Goods | 100 | Could be property? |
| Hemfridsbrott | Home Invasion/Trespass | 59 | Could be property? |
| Anträffat gods | Property Found | 49 | Not crime |
| Larm Överfall | Assault Alarm | 48 | Alarm, not confirmed |
| Efterlyst person | Wanted Person | 37 | Police activity |
| Uppdatering | Update | 74 | Information |
| Information | Information | 22 | Information |
| Sjukdom/olycksfall | Illness/Accident | 95 | Not crime |
| Sjölagen | Maritime Law | 22 | Specialized |
| Luftfartslagen | Aviation Law | 18 | Specialized |
| Utlänningslagen | Immigration Law | 15 | Specialized |
| Miljöbrott | Environmental Crime | 25 | Could be own category? |
| Skyddslagen | Protection Act | 47 | Specialized |
| Kontroll | Control/Check | 19 | Police activity |
| Bombhot | Bomb Threat | 4 | Could be violence? |
| Varningslarm/haveri | Warning Alarm/Breakdown | 5 | Not crime |
| Smällar | Bangs/Explosions (sounds) | 8 | Investigation |
| Spridning smitta/kemikalier | Spreading Disease/Chemicals | 3 | Specialized |
| Hets mot folkgrupp | Hate Speech | 3 | Could be violence? |
| Lagen om hundar och katter | Dog and Cat Act | 6 | Specialized |
| Skottlossning, misstänkt | Suspected Shooting | 44 | Investigation |

---

## Recommendations

### 1. Single Source of Truth

Create a comprehensive `event_types.py` that defines ALL 87 types:

```python
from dataclasses import dataclass
from enum import Enum

class Category(str, Enum):
    TRAFFIC = "traffic"
    PROPERTY = "property"
    VIOLENCE = "violence"
    NARCOTICS = "narcotics"
    FRAUD = "fraud"
    PUBLIC_ORDER = "public_order"
    WEAPONS = "weapons"
    OTHER = "other"

@dataclass
class EventType:
    swedish: str
    english: str
    category: Category

EVENT_TYPES: list[EventType] = [
    EventType("Stöld", "Theft", Category.PROPERTY),
    EventType("Misshandel", "Assault", Category.VIOLENCE),
    # ... all 87 types
]

# Generated lookups
SWEDISH_TO_ENGLISH: dict[str, str] = {et.swedish: et.english for et in EVENT_TYPES}
SWEDISH_TO_CATEGORY: dict[str, Category] = {et.swedish: et.category for et in EVENT_TYPES}
CATEGORY_TYPES: dict[Category, list[str]] = ...  # group by category
```

### 2. SQL Generation

Generate the SQL CASE statement from Python to ensure sync:

```python
def generate_category_sql() -> str:
    """Generate SQL CASE statement from EVENT_TYPES."""
    cases = []
    for category in Category:
        types = [et.swedish for et in EVENT_TYPES if et.category == category]
        if types and category != Category.OTHER:
            type_list = ", ".join(f"'{t}'" for t in types)
            cases.append(f"WHEN type IN ({type_list}) THEN '{category.value}'")
    return "CASE\n" + "\n".join(cases) + "\nELSE 'other'\nEND"
```

### 3. API Enhancement

Update `/api/types` to return both languages:

```json
{
  "categories": {
    "violence": {
      "english": "Violence",
      "types": [
        {"swedish": "Misshandel", "english": "Assault"},
        {"swedish": "Mord/dråp", "english": "Murder/Manslaughter"}
      ]
    }
  }
}
```

### 4. Frontend Changes

- Display English in UI labels/chips
- Show Swedish on hover (tooltip)
- Or: toggle language preference

---

## Impact Summary

| Metric | Before | After |
|--------|--------|-------|
| Events in "other" | 42,442 (62%) | ~21,000 (31%) |
| Mapped categories | 32 types | 53 types |
| Traffic events | 7,366 | 24,500+ |
| Property events | 6,432 | 7,395+ |
| Violence events | 5,675 | 6,805+ |

### Kiruna Example

| Category | Before | After |
|----------|--------|-------|
| Traffic | 44 | 146 |
| Other | 212 | 94 |
| Rate per 10k | 144.1 | (same total, better breakdown) |

---

## Decision Points

1. **Should "Skottlossning" (Shooting) be violence?** Currently other.
2. **Should "Explosion/Detonation" be violence?** Currently other.
3. **Should "Olaga intrång" (Trespassing) be property?** Currently other.
4. **Should "Häleri" (Receiving stolen goods) be property?** Currently other.
5. **Create new categories?** E.g., "emergency" for rescues, "investigation" for alarms.

---

## Next Steps

1. Review and finalize category assignments for edge cases
2. Create `event_types.py` with complete mapping
3. Update SQL to use generated CASE statement
4. Update API to return bilingual data
5. Update frontend to display English with Swedish tooltips
6. Re-run pipeline and verify category distributions

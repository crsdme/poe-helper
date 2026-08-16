from app.data.static import BASIC_CURRENCY

EXTRA_CURRENCIES = [
    {"id": "chromatic", "name": "Chromatic Orb"},
    {"id": "fusing", "name": "Orb of Fusing"},
    {"id": "jeweller", "name": "Jeweller's Orb"},
    {"id": "wisdom", "name": "Scroll of Wisdom"},
    {"id": "portal", "name": "Portal Scroll"},
    {"id": "armourer", "name": "Armourer's Scrap"},
    {"id": "whetstone", "name": "Blacksmith's Whetstone"},
    {"id": "glassblower", "name": "Glassblower's Bauble"},
    {"id": "chisel", "name": "Cartographer's Chisel"},
    {"id": "gcp", "name": "Gemcutter's Prism"},
    {"id": "binding", "name": "Orb of Binding"},
    {"id": "harbinger", "name": "Harbinger's Orb"},
    {"id": "ancient", "name": "Ancient Orb"},
    {"id": "horizon", "name": "Orb of Horizons"},
    {"id": "engineer", "name": "Engineer's Orb"},
    {"id": "regret", "name": "Orb of Regret"},
    {"id": "mirror", "name": "Mirror of Kalandra"},
    {"id": "regal", "name": "Regal Orb"},
]

BUTTONS = [
    {"id": "harvest_apply", "group": "buttons"},
    {"id": "harvest_window", "group": "buttons"},
    {"id": "inventory", "group": "buttons"},
]


def mappable_currencies() -> list[dict]:
    seen: set[str] = set()
    rows: list[dict] = []
    for row in [*BASIC_CURRENCY, *EXTRA_CURRENCIES]:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        rows.append(row)
    return rows

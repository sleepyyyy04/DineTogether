"""
Temporary Greater-LA test runner for DineTogether.

What it does:
1. Reads the original app/data/Greater_LA_cleaned.csv directly.
2. Adapts the raw fields in memory to the six fields the existing
   DineTogether restaurant table expects.
3. Uses a separate SQLite database:
      instance/dinetogether_la_test.sqlite
   so the original instance/dinetogether.sqlite is not touched.
4. Expands the cuisine choices shown in Preferences based on the
   cuisines detected in the raw Greater LA data.

Run:
    python run_la.py
"""
from __future__ import annotations

import csv
import math
import os
import re
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_CSV_PATH = os.path.join(BASE_DIR, "app", "data", "Greater_LA_cleaned.csv")
TEST_DB_PATH = os.path.join(BASE_DIR, "instance", "dinetogether_la_test.sqlite")

# Temporary reference point because the current DineTogether UI does not
# yet ask the user for a location. Distances are measured from Downtown LA.
ORIGIN_LAT = 34.052235
ORIGIN_LON = -118.243683

CUISINE_PATTERNS = [
    ("Vietnamese", [r"\bvietnamese\b", r"\bpho\b"]),
    ("Chinese", [r"\bchinese\b", r"\bhunan\b", r"\bsichuan\b", r"\bszechuan\b",
                 r"\bshanghainese\b", r"\bcantonese\b", r"\bmandarin\b",
                 r"\bdim sum\b", r"\bmalatang\b", r"\bcongee\b"]),
    ("Japanese", [r"\bjapanese\b", r"\bsushi\b", r"\bramen\b", r"\bteppanyaki\b",
                  r"\bshabu[- ]shabu\b", r"\bsukiyaki\b", r"\bkatsu\b", r"\bhandroll\b"]),
    ("Korean", [r"\bkorean\b", r"\bkimbap\b", r"\btopokki\b", r"\bjokbal\b", r"\bbon juk\b"]),
    ("Mexican", [r"\bmexican\b", r"\btaco\b", r"\bburrito\b", r"\btorta\b"]),
    ("Salvadoran", [r"\bsalvadoran\b", r"\bpupusa\b"]),
    ("Guatemalan", [r"\bguatemalan\b", r"\bquetzalteca\b"]),
    ("Honduran", [r"\bhonduran\b", r"\bcatracha\b"]),
    ("Cuban", [r"\bcuban\b"]),
    ("Colombian", [r"\bcolombian\b"]),
    ("Venezuelan", [r"\bvenezuelan\b"]),
    ("Ecuadorian", [r"\becuadorian\b"]),
    ("Peruvian", [r"\bperuvian\b"]),
    ("Indian", [r"\bindian\b", r"\bbiryani\b", r"\bdesi\b"]),
    ("Afghan", [r"\bafghan\b"]),
    ("Thai", [r"\bthai\b", r"\bsiam\b"]),
    ("Mediterranean", [r"\bmediterranean\b", r"\bgreek\b", r"\bpita\b"]),
    ("Middle Eastern", [r"\bmiddle eastern\b", r"\bkabob\b", r"\bkebab\b"]),
    ("Italian", [r"\bitalian\b"]),
    ("French", [r"\bfrench\b", r"\bcreperie\b"]),
    ("Spanish", [r"\bspanish\b"]),
    ("Jamaican", [r"\bjamaican\b", r"\bjerk\b"]),
    ("Hawaiian", [r"\bhawaiian\b", r"\bpoke\b"]),
    ("American", [r"\bamerican\b", r"\bsouthern\b", r"\bdiner\b", r"\bhamburger\b",
                  r"\bburger\b", r"\bhot dog\b", r"\bbarbecue\b", r"\bbbq\b",
                  r"\bbar & grill\b", r"\bcheesesteak\b", r"\bsmokehouse\b", r"\bwings\b"]),
]

GENERIC_PATTERNS = [
    ("Seafood", [r"\bseafood\b", r"\bfish & chips\b"]),
    ("Pizza", [r"\bpizza\b"]),
    ("Chicken", [r"\bchicken\b"]),
    ("Hot Pot", [r"\bhot pot\b"]),
    ("Sandwich", [r"\bsandwich\b", r"\bdeli\b"]),
    ("Asian Fusion", [r"\basian fusion\b"]),
    ("Asian", [r"\basian\b", r"\bdumpling\b", r"\bnoodle\b"]),
    ("Fast Food", [r"\bfast food\b"]),
    ("Health Food", [r"\bhealth food\b"]),
    ("Breakfast", [r"\bbreakfast\b", r"\bpancake\b"]),
    ("Dessert", [r"\bdessert\b"]),
    ("Latin American", [r"\blatin american\b", r"\barepa\b"]),
]


def _text(value) -> str:
    return "" if value is None else str(value).strip().lower()


def derive_cuisine(row: dict[str, str]) -> str:
    structured = " | ".join((_text(row.get("category")), _text(row.get("categories"))))
    fallback = " | ".join((structured, _text(row.get("title")), _text(row.get("description"))))

    # Prefer explicit category data.
    for label, patterns in CUISINE_PATTERNS:
        if any(re.search(pattern, structured) for pattern in patterns):
            return label

    # If category data is generic, use name/description as a fallback.
    for label, patterns in CUISINE_PATTERNS:
        if any(re.search(pattern, fallback) for pattern in patterns):
            return label

    for label, patterns in GENERIC_PATTERNS:
        if any(re.search(pattern, fallback) for pattern in patterns):
            return label

    return "Other"


def derive_dietary_tags(row: dict[str, str]) -> str:
    text = " | ".join(
        _text(row.get(key))
        for key in ("offerings", "categories", "description")
    )

    tags: list[str] = []
    has_vegan = "vegan" in text
    has_vegetarian = "vegetarian" in text or has_vegan

    if has_vegetarian:
        tags.append("vegetarian")
    if has_vegan:
        tags.append("vegan")
    if "gluten-free" in text or "gluten free" in text or "gluten_free" in text:
        tags.append("gluten_free")
    if "halal" in text:
        tags.append("halal")
    if "kosher" in text:
        tags.append("kosher")

    return ",".join(tags)


def distance_from_downtown_la(lat: float, lon: float) -> float:
    """Haversine straight-line distance in miles."""
    radius_miles = 3958.7613
    lat1 = math.radians(ORIGIN_LAT)
    lon1 = math.radians(ORIGIN_LON)
    lat2 = math.radians(lat)
    lon2 = math.radians(lon)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return radius_miles * 2 * math.asin(math.sqrt(a))


def load_raw_rows() -> list[dict[str, str]]:
    if not os.path.exists(RAW_CSV_PATH):
        raise FileNotFoundError(
            "\nCould not find app/data/Greater_LA_cleaned.csv.\n"
            "Upload your original Greater_LA_cleaned.csv into the app/data folder, "
            "then run python run_la.py again.\n"
        )

    with open(RAW_CSV_PATH, newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def import_raw_restaurants_if_empty(
    db: sqlite3.Connection,
    csv_path: str | None = None,
) -> int:
    """Adapter used by the existing DineTogether init_db() function."""
    (count,) = db.execute("SELECT COUNT(*) FROM restaurants").fetchone()
    if count > 0:
        return 0

    raw_rows = load_raw_rows()
    rows = []

    for raw in raw_rows:
        try:
            name = str(raw["title"]).strip()
            cuisine = derive_cuisine(raw)
            price_level = max(1, min(4, int(float(raw["price_level"]))))
            dietary_tags = derive_dietary_tags(raw)
            distance_mi = round(
                distance_from_downtown_la(float(raw["latitude"]), float(raw["longitude"])),
                1,
            )
            rating = round(float(raw["rating"]), 2)
        except (KeyError, TypeError, ValueError):
            # Skip a malformed row rather than crashing the entire test import.
            continue

        if not name:
            continue

        rows.append(
            (name, cuisine, price_level, dietary_tags, distance_mi, rating)
        )

    db.executemany(
        "INSERT INTO restaurants "
        "(name, cuisine, price_level, dietary_tags, distance_mi, rating) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    db.commit()

    print(f"\nLoaded {len(rows)} restaurants from the ORIGINAL Greater_LA_cleaned.csv.")
    print("Test distance reference: Downtown Los Angeles.")
    print(f"Separate test database: {TEST_DB_PATH}\n")
    return len(rows)


# Patch only this temporary Python process; the original project files remain intact.
from app.services import restaurant_import, validators

restaurant_import.import_restaurants_if_empty = import_raw_restaurants_if_empty

# Let the Preferences page show the cuisine labels actually detected in the raw data.
detected_cuisines = sorted({derive_cuisine(row) for row in load_raw_rows()})
validators.ALLOWED_CUISINES = ("any", *detected_cuisines)

from app import create_app

app = create_app({"DATABASE": TEST_DB_PATH})

if __name__ == "__main__":
    app.run(debug=True)

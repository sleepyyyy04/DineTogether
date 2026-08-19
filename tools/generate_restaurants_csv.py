"""
One-off generator for the static restaurant demonstration dataset
(SRS 2.1, DC-03/DC-04: a static CSV with at least 100 valid records,
varied cuisine/price/dietary/distance/rating per SRS 2.5).

This script is not a runtime dependency — app/db.py only ever reads
the CSV it produces (app/data/restaurants.csv). Re-run it only if the
dataset itself needs to be regenerated; `random.seed` keeps the output
reproducible.

Usage: python3 tools/generate_restaurants_csv.py
"""
from __future__ import annotations

import csv
import os
import random

CUISINES = [
    "American", "Italian", "Chinese", "Mexican", "Indian",
    "Japanese", "Thai", "Mediterranean", "French",
]

DIETARY_TAGS = ["vegetarian", "vegan", "gluten-free", "halal", "kosher", "dairy-free"]

NAME_PREFIXES = [
    "The Golden", "Blue", "Green", "Silver", "Sunset", "Copper", "Riverside",
    "Old Town", "Cedar", "Maple", "Harbor", "Garden", "Downtown", "Northside",
    "Sunny", "Rustic", "Urban", "Village", "Corner", "Lantern",
]

NAME_SUFFIXES = [
    "Kitchen", "Bistro", "Grill", "Table", "House", "Cafe", "Diner",
    "Eatery", "Tavern", "Restaurant", "Spot", "Kitchen & Bar", "Cantina",
    "Noodle Bar", "Trattoria",
]

OUTPUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "app", "data", "restaurants.csv"
)

ROW_COUNT = 120


def generate_rows(rng: random.Random) -> list[dict]:
    seen_names = set()
    rows = []
    while len(rows) < ROW_COUNT:
        name = f"{rng.choice(NAME_PREFIXES)} {rng.choice(NAME_SUFFIXES)}"
        if name in seen_names:
            continue
        seen_names.add(name)

        cuisine = rng.choice(CUISINES)
        price_tier = rng.randint(1, 4)
        dietary_count = rng.choices([0, 1, 2, 3], weights=[15, 35, 35, 15])[0]
        dietary_tags = sorted(rng.sample(DIETARY_TAGS, dietary_count))
        distance_km = round(rng.uniform(0.3, 15.0), 1)
        rating = round(rng.uniform(3.0, 5.0), 1)

        rows.append(
            {
                "name": name,
                "cuisine": cuisine,
                "price_tier": price_tier,
                "dietary_tags": ";".join(dietary_tags),
                "distance_km": distance_km,
                "rating": rating,
            }
        )
    return rows


def main() -> None:
    rng = random.Random(42)
    rows = generate_rows(rng)

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["name", "cuisine", "price_tier", "dietary_tags", "distance_km", "rating"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} restaurant records to {os.path.abspath(OUTPUT_PATH)}")


if __name__ == "__main__":
    main()

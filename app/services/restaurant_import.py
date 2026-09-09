"""
Restaurant dataset import (FR-04.1, DC-03, DC-04).

Greater_LA_cleaned.csv is treated as the raw static restaurant dataset.
The source CSV is not modified.

During import:
- title -> name
- category -> cuisine
- categories -> dietary_tags
- price_level -> price_level
- rating -> rating
- latitude/longitude -> calculated distance_mi from Sofia University,
  Costa Mesa

The raw category strings are intentionally preserved. Cuisine and dietary
matching are handled with case-insensitive substring matching in the
application layer rather than exact equality.
"""

from __future__ import annotations

import csv
import math
import os
import sqlite3


_CSV_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "Greater_LA_cleaned.csv",
)


# Sofia University - Costa Mesa campus
# 3333 Harbor Blvd, Costa Mesa, CA 92626
#
# Fixed reference point for restaurant distance calculations.
SOFIA_LATITUDE = 33.6900
SOFIA_LONGITUDE = -117.9180

EARTH_RADIUS_MI = 3958.8


def calculate_distance_mi(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculate straight-line geographic distance between two latitude /
    longitude points using the Haversine formula.

    Returns distance in miles.
    """
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_MI * c


def import_restaurants_if_empty(
    db: sqlite3.Connection,
    csv_path: str | None = None,
) -> int:
    """
    Import Greater_LA_cleaned.csv into the restaurants table.

    Returns the number of rows inserted.

    If the restaurants table already contains data, nothing is imported
    and 0 is returned.
    """
    path = csv_path or _CSV_PATH

    (count,) = db.execute(
        "SELECT COUNT(*) FROM restaurants"
    ).fetchone()

    if count > 0:
        return 0

    rows = []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            name = row["title"].strip()

            # Keep the real dataset strings.
            #
            # Example:
            #   category:
            #       "Chinese restaurant"
            #
            #   categories:
            #       "Chinese restaurant, Asian restaurant,
            #        Fast food restaurant"
            #
            # Matching is performed later using substring detection.
            cuisine = row["category"].strip()
            dietary_tags = row["categories"].strip()

            price_level = int(row["price_level"])
            rating = float(row["rating"])

            latitude = float(row["latitude"])
            longitude = float(row["longitude"])

            distance_mi = round(
                calculate_distance_mi(
                    SOFIA_LATITUDE,
                    SOFIA_LONGITUDE,
                    latitude,
                    longitude,
                ),
                2,
            )

            rows.append(
                (
                    name,
                    cuisine,
                    price_level,
                    dietary_tags,
                    distance_mi,
                    rating,
                )
            )

    db.executemany(
        """
        INSERT INTO restaurants
            (
                name,
                cuisine,
                price_level,
                dietary_tags,
                distance_mi,
                rating
            )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )

    db.commit()

    return len(rows)

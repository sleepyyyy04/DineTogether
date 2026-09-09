"""
Data-access layer for the static restaurant dataset (FR-04).

Restaurant rows are populated from Greater_LA_cleaned.csv during
application initialization.

The original restaurant category strings are retained. Matching against
user cuisine and dietary preferences is case-insensitive and uses
substring detection rather than exact equality.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


@dataclass
class Restaurant:
    id: int
    name: str

    # Raw primary category from Greater_LA_cleaned.csv.
    # Example: "Chinese restaurant"
    cuisine: str

    price_level: int

    # Raw categories from Greater_LA_cleaned.csv, split on commas.
    #
    # Example:
    # [
    #     "Chinese restaurant",
    #     "Asian restaurant",
    #     "Fast food restaurant",
    # ]
    dietary_tags: list[str] = field(default_factory=list)

    distance_mi: float = 0.0
    rating: float = 0.0

    def searchable_categories(self) -> str:
        """
        Return all restaurant category information as one normalized
        searchable string.

        Both the primary category and full categories list are included
        because the primary category may simply be "Restaurant" while
        the full categories field contains something useful such as
        "Mexican restaurant".
        """
        values = [self.cuisine, *self.dietary_tags]

        return " ".join(values).lower()

    def matches_cuisine(self, cuisine: str) -> bool:
        """
        Return True when a user's cuisine preference occurs anywhere in
        the restaurant's category information.

        Matching is case-insensitive substring matching.

        Examples:
            "Chinese" matches "Chinese restaurant"
            "Mexican" matches "Mexican restaurant"
            "Japanese" matches "Japanese restaurant"

        The special preference "any" always matches.
        """
        if not cuisine:
            return False

        cuisine = cuisine.strip().lower()

        if cuisine == "any":
            return True

        return cuisine in self.searchable_categories()

    def supports(self, dietary: str) -> bool:
        """
        Return True when the requested dietary term occurs anywhere in
        the restaurant's categories.

        Matching is case-insensitive substring matching.

        Examples:
            "vegan" matches "Vegan restaurant"
            "vegetarian" matches "Vegetarian restaurant"
            "halal" matches "Halal restaurant"
            "kosher" matches "Kosher restaurant"

        gluten_free is normalized because the preference uses an
        underscore while the source dataset may use "gluten-free" or
        "gluten free".
        """
        if not dietary:
            return False

        dietary = dietary.strip().lower()

        if dietary == "none":
            return True

        search_text = self.searchable_categories()

        if dietary == "gluten_free":
            return (
                "gluten-free" in search_text
                or "gluten free" in search_text
                or "gluten_free" in search_text
            )

        return dietary in search_text


def _row_to_restaurant(row: sqlite3.Row) -> Restaurant:
    tags = [
        tag.strip()
        for tag in row["dietary_tags"].split(",")
        if tag.strip()
    ]

    return Restaurant(
        id=row["id"],
        name=row["name"],
        cuisine=row["cuisine"],
        price_level=row["price_level"],
        dietary_tags=tags,
        distance_mi=row["distance_mi"],
        rating=row["rating"],
    )


class RestaurantRepository:
    def __init__(self, db: sqlite3.Connection):
        self._db = db

    def list_all(self) -> list[Restaurant]:
        rows = self._db.execute(
            """
            SELECT
                id,
                name,
                cuisine,
                price_level,
                dietary_tags,
                distance_mi,
                rating
            FROM restaurants
            ORDER BY id
            """
        ).fetchall()

        return [_row_to_restaurant(row) for row in rows]

    def get_by_id(
        self,
        restaurant_id: int,
    ) -> Restaurant | None:
        row = self._db.execute(
            """
            SELECT
                id,
                name,
                cuisine,
                price_level,
                dietary_tags,
                distance_mi,
                rating
            FROM restaurants
            WHERE id = ?
            """,
            (restaurant_id,),
        ).fetchone()

        return _row_to_restaurant(row) if row else None

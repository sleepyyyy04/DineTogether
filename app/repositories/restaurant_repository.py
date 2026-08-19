"""
Data-access layer for the static restaurant dataset (FR-04). Read-only
from the application's point of view — rows are only ever written by
app/services/restaurant_import.py during initialization.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


@dataclass
class Restaurant:
    id: int
    name: str
    cuisine: str
    price_level: int
    dietary_tags: list[str] = field(default_factory=list)
    distance_mi: float = 0.0
    rating: float = 0.0

    def supports(self, dietary: str) -> bool:
        return dietary in self.dietary_tags


def _row_to_restaurant(row: sqlite3.Row) -> Restaurant:
    tags = [t for t in row["dietary_tags"].split(",") if t]
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
            "SELECT id, name, cuisine, price_level, dietary_tags, distance_mi, rating "
            "FROM restaurants ORDER BY id"
        ).fetchall()
        return [_row_to_restaurant(r) for r in rows]

    def get_by_id(self, restaurant_id: int) -> Restaurant | None:
        row = self._db.execute(
            "SELECT id, name, cuisine, price_level, dietary_tags, distance_mi, rating "
            "FROM restaurants WHERE id = ?",
            (restaurant_id,),
        ).fetchone()
        return _row_to_restaurant(row) if row else None

"""
Restaurant dataset import (FR-04.1, DC-03, DC-04).

Restaurant data is a static demo CSV, never a live API (DC-03). This
module reads it into SQLite exactly once: init_db() calls
import_restaurants_if_empty() on every startup, but the insert only
runs while the restaurants table is still empty, so restarting the
app never duplicates rows (NFR-03.2).
"""
from __future__ import annotations

import csv
import os
import sqlite3

_CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "restaurants.csv")


def import_restaurants_if_empty(db: sqlite3.Connection, csv_path: str | None = None) -> int:
    """Return the number of rows inserted (0 if the table already had data)."""
    path = csv_path or _CSV_PATH

    (count,) = db.execute("SELECT COUNT(*) FROM restaurants").fetchone()
    if count > 0:
        return 0

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [
            (
                row["name"].strip(),
                row["cuisine"].strip(),
                int(row["price_level"]),
                row["dietary_tags"].strip(),
                float(row["distance_mi"]),
                float(row["rating"]),
            )
            for row in reader
        ]

    db.executemany(
        "INSERT INTO restaurants (name, cuisine, price_level, dietary_tags, distance_mi, rating) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    db.commit()
    return len(rows)

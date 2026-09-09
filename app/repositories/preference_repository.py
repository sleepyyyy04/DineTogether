"""
Data-access layer for FR-03 Preference Submission. One row per
participant (UNIQUE(participant_id) in the schema) — submitting again
replaces the row in place (FR-03.2/03.3), it never appends a history.

Cuisine, budget, and dietary are each multi-select; they're stored as
comma-separated TEXT columns (same convention as
restaurants.dietary_tags in restaurant_repository.py) and split back
into lists on read.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


@dataclass
class Preference:
    id: int
    event_id: int
    participant_id: int
    cuisines: list[str] = field(default_factory=list)
    budget_levels: list[int] = field(default_factory=list)
    dietary: list[str] = field(default_factory=list)
    max_distance_mi: float = 0.0
    min_rating: float | None = None


def _split(value: str) -> list[str]:
    return [v for v in value.split(",") if v]


def _row_to_preference(row: sqlite3.Row) -> Preference:
    return Preference(
        id=row["id"],
        event_id=row["event_id"],
        participant_id=row["participant_id"],
        cuisines=_split(row["cuisine"]),
        budget_levels=[int(v) for v in _split(row["budget_levels"])],
        dietary=_split(row["dietary"]),
        max_distance_mi=row["max_distance_mi"],
        min_rating=row["min_rating"],
    )


class PreferenceRepository:
    def __init__(self, db: sqlite3.Connection):
        self._db = db

    def upsert(
        self,
        event_id: int,
        participant_id: int,
        cuisines: list[str],
        budget_levels: list[int],
        dietary: list[str],
        max_distance_mi: float,
        min_rating: float | None = None,
    ) -> Preference:
        cuisine_value = ",".join(cuisines)
        budget_value = ",".join(str(level) for level in budget_levels)
        dietary_value = ",".join(dietary)
        self._db.execute(
            """
            INSERT INTO preferences
                (event_id, participant_id, cuisine, budget_levels, dietary, max_distance_mi, min_rating, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(participant_id) DO UPDATE SET
                cuisine = excluded.cuisine,
                budget_levels = excluded.budget_levels,
                dietary = excluded.dietary,
                max_distance_mi = excluded.max_distance_mi,
                min_rating = excluded.min_rating,
                updated_at = excluded.updated_at
            """,
            (event_id, participant_id, cuisine_value, budget_value, dietary_value, max_distance_mi, min_rating),
        )
        self._db.commit()
        return self.get_for_participant(participant_id)

    def get_for_participant(self, participant_id: int) -> Preference | None:
        row = self._db.execute(
            "SELECT id, event_id, participant_id, cuisine, budget_levels, dietary, max_distance_mi, min_rating "
            "FROM preferences WHERE participant_id = ?",
            (participant_id,),
        ).fetchone()
        return _row_to_preference(row) if row else None

    def list_for_event(self, event_id: int) -> list[Preference]:
        rows = self._db.execute(
            "SELECT id, event_id, participant_id, cuisine, budget_levels, dietary, max_distance_mi, min_rating "
            "FROM preferences WHERE event_id = ? ORDER BY id",
            (event_id,),
        ).fetchall()
        return [_row_to_preference(r) for r in rows]

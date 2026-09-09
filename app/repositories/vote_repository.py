"""
Data-access layer for FR-05 Voting and Result Management. A
participant may approve any number of shortlisted restaurants;
resubmitting replaces their whole prior selection (FR-05.2) rather
than adding to it. Results are written once per event, at
finalization, and are the durable record voting_service and the
results page read back (FR-05.5).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class Vote:
    id: int
    event_id: int
    participant_id: int
    restaurant_id: int


@dataclass
class Result:
    event_id: int
    restaurant_id: int | None
    is_tie: bool
    vote_totals: str
    decided_at: str


class VoteRepository:
    def __init__(self, db: sqlite3.Connection):
        self._db = db

    def set_votes(self, event_id: int, participant_id: int, restaurant_ids: list[int]) -> list[Vote]:
        """Replace this participant's entire selection for the event
        with restaurant_ids (FR-05.2: resubmitting replaces, not
        adds)."""
        self._db.execute(
            "DELETE FROM votes WHERE event_id = ? AND participant_id = ?",
            (event_id, participant_id),
        )
        self._db.executemany(
            "INSERT INTO votes (event_id, participant_id, restaurant_id, voted_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            [(event_id, participant_id, restaurant_id) for restaurant_id in restaurant_ids],
        )
        self._db.commit()
        return self.get_votes_for_participant(event_id, participant_id)

    def get_votes_for_participant(self, event_id: int, participant_id: int) -> list[Vote]:
        rows = self._db.execute(
            "SELECT id, event_id, participant_id, restaurant_id FROM votes "
            "WHERE event_id = ? AND participant_id = ?",
            (event_id, participant_id),
        ).fetchall()
        return [
            Vote(
                id=row["id"],
                event_id=row["event_id"],
                participant_id=row["participant_id"],
                restaurant_id=row["restaurant_id"],
            )
            for row in rows
        ]

    def get_vote_counts(self, event_id: int) -> dict[int, int]:
        """restaurant_id -> number of votes, for restaurants with >=1 vote."""
        rows = self._db.execute(
            "SELECT restaurant_id, COUNT(*) AS n FROM votes WHERE event_id = ? "
            "GROUP BY restaurant_id",
            (event_id,),
        ).fetchall()
        return {r["restaurant_id"]: r["n"] for r in rows}

    def is_finalized(self, event_id: int) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM results WHERE event_id = ?", (event_id,)
        ).fetchone()
        return row is not None

    def save_result(
        self,
        event_id: int,
        restaurant_id: int | None,
        is_tie: bool,
        vote_totals_json: str,
    ) -> Result:
        self._db.execute(
            "INSERT INTO results (event_id, restaurant_id, is_tie, vote_totals, decided_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (event_id, restaurant_id, int(is_tie), vote_totals_json),
        )
        self._db.commit()
        return self.get_result(event_id)

    def get_result(self, event_id: int) -> Result | None:
        row = self._db.execute(
            "SELECT event_id, restaurant_id, is_tie, vote_totals, decided_at "
            "FROM results WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        return Result(
            event_id=row["event_id"],
            restaurant_id=row["restaurant_id"],
            is_tie=bool(row["is_tie"]),
            vote_totals=row["vote_totals"],
            decided_at=row["decided_at"],
        )

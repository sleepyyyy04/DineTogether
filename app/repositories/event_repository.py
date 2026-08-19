"""
Data-access layer for events and participants (SRS Event Management
module). Every query is parameterized (NFR-04.4) — no query in this
file is ever built with string formatting or f-strings.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class Event:
    id: int
    name: str
    invite_code: str


@dataclass
class Participant:
    id: int
    event_id: int
    user_id: int
    display_name: str


class EventRepository:
    def __init__(self, db: sqlite3.Connection):
        self._db = db

    def code_exists(self, invite_code: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM events WHERE invite_code = ?", (invite_code,)
        ).fetchone()
        return row is not None

    def create_event(self, name: str, invite_code: str) -> Event:
        cur = self._db.execute(
            "INSERT INTO events (name, invite_code) VALUES (?, ?)",
            (name, invite_code),
        )
        self._db.commit()
        return Event(id=cur.lastrowid, name=name, invite_code=invite_code)

    def get_event_by_code(self, invite_code: str) -> Event | None:
        row = self._db.execute(
            "SELECT id, name, invite_code FROM events WHERE invite_code = ?",
            (invite_code,),
        ).fetchone()
        if row is None:
            return None
        return Event(id=row["id"], name=row["name"], invite_code=row["invite_code"])

    def get_event_by_id(self, event_id: int) -> Event | None:
        row = self._db.execute(
            "SELECT id, name, invite_code FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        return Event(id=row["id"], name=row["name"], invite_code=row["invite_code"])

    def add_participant(self, event_id: int, user_id: int, display_name: str) -> Participant:
        cur = self._db.execute(
            "INSERT INTO participants (event_id, user_id, display_name) VALUES (?, ?, ?)",
            (event_id, user_id, display_name),
        )
        self._db.commit()
        return Participant(id=cur.lastrowid, event_id=event_id, user_id=user_id, display_name=display_name)

    def get_participant_for_user(self, event_id: int, user_id: int) -> Participant | None:
        row = self._db.execute(
            "SELECT id, event_id, user_id, display_name FROM participants "
            "WHERE event_id = ? AND user_id = ?",
            (event_id, user_id),
        ).fetchone()
        if row is None:
            return None
        return Participant(
            id=row["id"], event_id=row["event_id"], user_id=row["user_id"], display_name=row["display_name"]
        )

    def list_participants(self, event_id: int) -> list[Participant]:
        rows = self._db.execute(
            "SELECT id, event_id, user_id, display_name FROM participants "
            "WHERE event_id = ? ORDER BY joined_at",
            (event_id,),
        ).fetchall()
        return [
            Participant(id=r["id"], event_id=r["event_id"], user_id=r["user_id"], display_name=r["display_name"])
            for r in rows
        ]

    def list_events_for_user(self, user_id: int) -> list[Event]:
        rows = self._db.execute(
            "SELECT e.id, e.name, e.invite_code FROM events e "
            "JOIN participants p ON p.event_id = e.id "
            "WHERE p.user_id = ? ORDER BY p.joined_at DESC",
            (user_id,),
        ).fetchall()
        return [Event(id=r["id"], name=r["name"], invite_code=r["invite_code"]) for r in rows]

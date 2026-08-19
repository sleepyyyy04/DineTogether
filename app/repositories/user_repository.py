"""
Data-access layer for user accounts. Every query is parameterized
(NFR-04.4) — no query in this file is ever built with string
formatting or f-strings.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class User:
    id: int
    username: str
    password_hash: str
    display_name: str


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        display_name=row["display_name"],
    )


class UserRepository:
    def __init__(self, db: sqlite3.Connection):
        self._db = db

    def create(self, username: str, password_hash: str, display_name: str) -> User:
        cur = self._db.execute(
            "INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)",
            (username, password_hash, display_name),
        )
        self._db.commit()
        return User(id=cur.lastrowid, username=username, password_hash=password_hash, display_name=display_name)

    def get_by_username(self, username: str) -> User | None:
        row = self._db.execute(
            "SELECT id, username, password_hash, display_name FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return _row_to_user(row) if row else None

    def get_by_id(self, user_id: int) -> User | None:
        row = self._db.execute(
            "SELECT id, username, password_hash, display_name FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return _row_to_user(row) if row else None

"""
SQLite access helper.

Per DC-02 / NFR-04.4, all data access goes through parameterized
queries — never string-formatted SQL — and every repository in
app/repositories/ calls get_db() rather than opening its own
connection, so there is exactly one place that owns the connection
lifecycle.
"""
import sqlite3

import click
from flask import current_app, g


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    invite_code TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS participants (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    joined_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(event_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_participants_event_id ON participants(event_id);

CREATE TABLE IF NOT EXISTS restaurants (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    cuisine      TEXT NOT NULL,
    price_level  INTEGER NOT NULL,
    dietary_tags TEXT NOT NULL DEFAULT '',
    distance_mi  REAL NOT NULL,
    rating       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS preferences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    participant_id  INTEGER NOT NULL UNIQUE REFERENCES participants(id) ON DELETE CASCADE,
    cuisine         TEXT NOT NULL,
    budget_levels   TEXT NOT NULL,
    dietary         TEXT NOT NULL,
    max_distance_mi REAL NOT NULL,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_preferences_event_id ON preferences(event_id);

CREATE TABLE IF NOT EXISTS votes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id       INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    participant_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
    restaurant_id  INTEGER NOT NULL REFERENCES restaurants(id),
    voted_at       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(event_id, participant_id, restaurant_id)
);

CREATE INDEX IF NOT EXISTS idx_votes_event_id ON votes(event_id);

CREATE TABLE IF NOT EXISTS results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      INTEGER NOT NULL UNIQUE REFERENCES events(id) ON DELETE CASCADE,
    restaurant_id INTEGER REFERENCES restaurants(id),
    is_tie        INTEGER NOT NULL DEFAULT 0,
    vote_totals   TEXT NOT NULL,
    decided_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_db() -> None:
    """Create tables if they don't exist yet (NFR-03.2: data must
    survive and remain readable across an application restart), then
    import the static restaurant dataset (FR-04.1) if it hasn't been
    loaded yet."""
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()

    from app.services.restaurant_import import import_restaurants_if_empty

    import_restaurants_if_empty(db)


@click.command("init-db")
def init_db_command():
    """Flask CLI command: `flask init-db` — wipes and recreates tables."""
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()
    click.echo("Initialized the database.")

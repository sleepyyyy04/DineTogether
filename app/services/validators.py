"""
Shared field validation (NFR-04.2: validate type, length, format, and
allowed values on the server before processing or storage).

This module is the single source of truth for the "blank / too long"
rule so Create Event (FR-01.3) and Join Event's display name
(FR-02.1) can't drift out of sync — the refactor called out in the
increment report.
"""
from __future__ import annotations

import re

EVENT_NAME_MAX_LEN = 80
DISPLAY_NAME_MIN_LEN = 1
DISPLAY_NAME_MAX_LEN = 40

# Invitation codes are generated server-side as 4 uppercase
# letters/digits (see event_service.generate_invite_code). This
# pattern is what FR-02.2 checks incoming codes against before ever
# touching the database.
INVITE_CODE_PATTERN = re.compile(r"^[A-Z0-9]{4}$")

# --- Account registration / login -----------------------------------

# Letters, digits, underscore, dot, hyphen — no spaces or "@", so a
# username can never be confused for (or require) a real email address.
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 72


class ValidationError(Exception):
    """Raised with a field name and a user-safe message (NFR-02.2:
    never leak internal technical details in the message)."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


def validate_event_name(name: str) -> str:
    if name is None:
        raise ValidationError("name", "Event name is required.")
    name = name.strip()
    if not name:
        raise ValidationError("name", "Event name is required.")
    if len(name) > EVENT_NAME_MAX_LEN:
        raise ValidationError(
            "name", f"Event name must be {EVENT_NAME_MAX_LEN} characters or fewer."
        )
    return name


def validate_display_name(name: str) -> str:
    if name is None:
        raise ValidationError("display_name", "Display name is required.")
    name = name.strip()
    if len(name) < DISPLAY_NAME_MIN_LEN or len(name) > DISPLAY_NAME_MAX_LEN:
        raise ValidationError(
            "display_name",
            f"Display name must be {DISPLAY_NAME_MIN_LEN}-{DISPLAY_NAME_MAX_LEN} characters.",
        )
    return name


def validate_username(username: str) -> str:
    if username is None:
        raise ValidationError("username", "Username is required.")
    username = username.strip().lower()
    if not USERNAME_PATTERN.match(username):
        raise ValidationError(
            "username", "Username must be 3-30 characters: letters, digits, underscore, dot, or hyphen."
        )
    return username


def validate_password(password: str) -> str:
    if password is None or len(password) < PASSWORD_MIN_LEN:
        raise ValidationError(
            "password", f"Password must be at least {PASSWORD_MIN_LEN} characters."
        )
    if len(password) > PASSWORD_MAX_LEN:
        raise ValidationError(
            "password", f"Password must be {PASSWORD_MAX_LEN} characters or fewer."
        )
    return password


def validate_invite_code_format(code: str) -> str:
    """FR-02.2: reject a malformed code before doing a DB lookup, so a
    malformed code and an unknown-but-well-formed code both produce
    the same non-sensitive error from the caller's point of view."""
    if code is None:
        raise ValidationError("code", "Invitation code is required.")
    code = code.strip().upper()
    if not INVITE_CODE_PATTERN.match(code):
        raise ValidationError("code", "That invitation code isn't valid.")
    return code


# --- FR-03 Preference Submission (NFR-04.2: validate type, length,
# format, and allowed values on the server, always) -----------------

ALLOWED_CUISINES = (
    "any",
    "American",
    "Italian",
    "Chinese",
    "Mexican",
    "Indian",
    "Japanese",
    "Thai",
    "Mediterranean",
    "French",
    "Vietnamese",
)

# Maps a displayed budget tier to the maximum restaurant price_level
# (1-4, i.e. $ .. $$$$) a participant choosing that tier will accept.
ALLOWED_BUDGETS = {"$": 1, "$$": 2, "$$$": 3, "$$$$": 4}

ALLOWED_DIETARY = ("none", "vegetarian", "vegan", "gluten_free", "halal", "kosher")

MIN_DISTANCE_MI = 0.5
MAX_DISTANCE_MI = 25.0


def validate_cuisine(cuisines: list[str]) -> list[str]:
    if not cuisines:
        raise ValidationError("cuisine", "Choose at least one cuisine option.")
    for cuisine in cuisines:
        if cuisine not in ALLOWED_CUISINES:
            raise ValidationError("cuisine", "Choose a valid cuisine option.")
    return cuisines


def validate_budget(budgets: list[str]) -> list[int]:
    if not budgets:
        raise ValidationError("budget", "Choose at least one budget option.")
    for budget in budgets:
        if budget not in ALLOWED_BUDGETS:
            raise ValidationError("budget", "Choose a valid budget option.")
    return sorted({ALLOWED_BUDGETS[budget] for budget in budgets})


def validate_dietary(dietary: list[str]) -> list[str]:
    if not dietary:
        raise ValidationError("dietary", "Choose at least one dietary option.")
    for option in dietary:
        if option not in ALLOWED_DIETARY:
            raise ValidationError("dietary", "Choose a valid dietary option.")
    return dietary


def validate_max_distance(raw_distance: str) -> float:
    if raw_distance is None or not str(raw_distance).strip():
        raise ValidationError("max_distance", "Maximum distance is required.")
    try:
        distance = float(raw_distance)
    except (TypeError, ValueError):
        raise ValidationError("max_distance", "Maximum distance must be a number.")
    if distance < MIN_DISTANCE_MI or distance > MAX_DISTANCE_MI:
        raise ValidationError(
            "max_distance",
            f"Maximum distance must be between {MIN_DISTANCE_MI} and {MAX_DISTANCE_MI} miles.",
        )
    return distance

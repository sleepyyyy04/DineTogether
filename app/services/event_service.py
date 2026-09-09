"""
Application-logic layer for Event Creation (FR-01) and Event
Joining/Access (FR-02). Routes call only this module; this module is
the only caller of EventRepository (ADR-0001 layering, no cross-layer
shortcuts).
"""
from __future__ import annotations

import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.repositories.event_repository import Event, EventRepository, Participant
from app.repositories.user_repository import User
from app.repositories.vote_repository import VoteRepository
from app.services.validators import validate_event_name, validate_invite_code_format

# Unambiguous alphabet: no 0/O or 1/I, so a participant reading the
# code aloud or typing it on a phone keyboard is less likely to
# transcribe it wrong.
_CODE_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "01OI")
_CODE_LENGTH = 4
_MAX_CODE_ATTEMPTS = 10

# How long an invite code stays usable for a *new* participant after
# the event was created. Someone who already joined can always get
# back in — this only gates first-time joins.
INVITE_CODE_TTL = timedelta(minutes=30)


class EventNotFoundError(Exception):
    """Raised by join_event for a well-formed but unknown code (FR-02.2).
    Callers should render the same non-sensitive message they'd use
    for a malformed code — see routes.py."""


class InviteCodeExpiredError(Exception):
    """Raised when a new participant tries to join more than
    INVITE_CODE_TTL after the event was created."""


class EventAlreadyFinalizedError(Exception):
    """Raised when a new participant tries to join an event whose
    final decision has already been saved — voting and preferences
    are locked by then, so there is nothing left to join for."""


@dataclass
class JoinResult:
    event: Event
    participant: Participant


def _generate_unique_invite_code(repo: EventRepository) -> str:
    """Fix for code-review Finding 1: generate a code and retry until
    it's confirmed unused, instead of inserting blind and risking a
    collision with an existing event's code."""
    for _ in range(_MAX_CODE_ATTEMPTS):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        if not repo.code_exists(code):
            return code
    # Astronomically unlikely with a 32^4 code space at this dataset
    # size, but fail loudly rather than silently reusing a code.
    raise RuntimeError("Could not generate a unique invitation code; try again.")


def create_event(repo: EventRepository, name: str, user: User) -> JoinResult:
    """FR-01.1 / FR-01.2 / FR-01.3.

    The organizer is added as a participant immediately (SRS 2.3: the
    organizer "can also submit preferences, vote, and view results"),
    reusing the same add_participant path join_event uses so there is
    exactly one way a participant row gets created. The participant's
    display name is the account's, not something typed per-event.
    """
    clean_name = validate_event_name(name)
    invite_code = _generate_unique_invite_code(repo)
    event = repo.create_event(clean_name, invite_code)
    participant = repo.add_participant(event.id, user.id, user.display_name)
    return JoinResult(event=event, participant=participant)


def join_event(repo: EventRepository, vote_repo: VoteRepository, raw_code: str, user: User) -> JoinResult:
    """FR-02.1 / FR-02.2 / FR-02.3.

    Joining the same event twice with the same account is idempotent
    (UNIQUE(event_id, user_id) in the schema) — it returns the
    existing participant row rather than erroring, since re-visiting
    an invite link is a normal thing to do. That idempotent path is
    checked before the expiry/finalized gates below, so someone who
    already joined never gets locked out of an event they're already
    part of.
    """
    code = validate_invite_code_format(raw_code)

    event = repo.get_event_by_code(code)
    if event is None:
        raise EventNotFoundError(code)

    existing = repo.get_participant_for_user(event.id, user.id)
    if existing is not None:
        return JoinResult(event=event, participant=existing)

    if vote_repo.is_finalized(event.id):
        raise EventAlreadyFinalizedError(event.id)

    created_at = datetime.strptime(event.created_at, "%Y-%m-%d %H:%M:%S")
    if datetime.utcnow() - created_at > INVITE_CODE_TTL:
        raise InviteCodeExpiredError(event.id)

    participant = repo.add_participant(event.id, user.id, user.display_name)
    return JoinResult(event=event, participant=participant)

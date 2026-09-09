"""
Application-logic layer for Preference Submission (FR-03). Routes
call only this module; it is the only caller of PreferenceRepository
for writes (ADR-0001 layering).
"""
from __future__ import annotations

from app.repositories.preference_repository import Preference, PreferenceRepository
from app.repositories.vote_repository import VoteRepository
from app.services.validators import (
    validate_budget,
    validate_cuisine,
    validate_dietary,
    validate_max_distance,
)


class EventFinalizedError(Exception):
    """Raised when a preference submission is attempted after the
    event's final result has already been saved (FR-03.3 boundary:
    edits are only allowed while the result is not yet saved)."""


class AlreadyVotedError(Exception):
    """Raised when a participant who has already cast a vote tries to
    change their preferences. The shortlist they voted from is a
    snapshot of every participant's preferences at that moment —
    letting it shift afterward could silently invalidate ballots
    already cast against it."""


def submit_preferences(
    pref_repo: PreferenceRepository,
    vote_repo: VoteRepository,
    event_id: int,
    participant_id: int,
    raw_cuisines: list[str],
    raw_budgets: list[str],
    raw_dietary: list[str],
    raw_max_distance: str,
) -> Preference:
    if vote_repo.is_finalized(event_id):
        raise EventFinalizedError(event_id)

    if vote_repo.get_votes_for_participant(event_id, participant_id):
        raise AlreadyVotedError(event_id)

    cuisines = validate_cuisine(raw_cuisines)
    budget_levels = validate_budget(raw_budgets)
    dietary = validate_dietary(raw_dietary)
    max_distance_mi = validate_max_distance(raw_max_distance)

    return pref_repo.upsert(
        event_id=event_id,
        participant_id=participant_id,
        cuisines=cuisines,
        budget_levels=budget_levels,
        dietary=dietary,
        max_distance_mi=max_distance_mi,
    )

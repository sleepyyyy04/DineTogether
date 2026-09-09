"""
Application-logic layer for Voting and Result Management (FR-05).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.repositories.preference_repository import PreferenceRepository
from app.repositories.restaurant_repository import RestaurantRepository
from app.repositories.vote_repository import Result, Vote, VoteRepository
from app.services.recommendation_service import get_recommendations


class EventFinalizedError(Exception):
    """Raised when a vote is cast, or finalize is called again, after
    the event's result has already been saved (FR-05.2/05.5 boundary:
    "before finalization")."""


class RestaurantNotOnShortlistError(Exception):
    """Raised when a vote targets a restaurant outside the current
    recommendation shortlist, or when no restaurant was selected at
    all (FR-05.1: vote for restaurants "on the shortlist")."""


class NoShortlistError(Exception):
    """Raised when finalize is attempted before any recommendation
    shortlist exists (FR-05.1 precondition)."""


@dataclass
class FinalizeOutcome:
    result: Result
    winner_name: str | None


def cast_votes(
    pref_repo: PreferenceRepository,
    restaurant_repo: RestaurantRepository,
    vote_repo: VoteRepository,
    event_id: int,
    participant_id: int,
    restaurant_ids: list[int],
) -> list[Vote]:
    if vote_repo.is_finalized(event_id):
        raise EventFinalizedError(event_id)

    shortlist_ids = {r.id for r in get_recommendations(pref_repo, restaurant_repo, event_id).restaurants}
    if not restaurant_ids or any(rid not in shortlist_ids for rid in restaurant_ids):
        raise RestaurantNotOnShortlistError(restaurant_ids)

    return vote_repo.set_votes(event_id, participant_id, restaurant_ids)


def finalize(
    pref_repo: PreferenceRepository,
    restaurant_repo: RestaurantRepository,
    vote_repo: VoteRepository,
    event_id: int,
) -> FinalizeOutcome:
    if vote_repo.is_finalized(event_id):
        # FR-05.5: the decision was already saved — return it rather
        # than silently recomputing a possibly different one.
        result = vote_repo.get_result(event_id)
        winner = restaurant_repo.get_by_id(result.restaurant_id) if result.restaurant_id else None
        return FinalizeOutcome(result=result, winner_name=winner.name if winner else None)

    shortlist = get_recommendations(pref_repo, restaurant_repo, event_id).restaurants
    if not shortlist:
        raise NoShortlistError(event_id)

    counts = vote_repo.get_vote_counts(event_id)
    if not counts:
        raise NoShortlistError(event_id)

    top_count = max(counts.values())
    winners = [rid for rid, n in counts.items() if n == top_count]

    id_to_name = {r.id: r.name for r in restaurant_repo.list_all()}
    vote_totals = {id_to_name.get(rid, str(rid)): n for rid, n in counts.items()}
    vote_totals_json = json.dumps(vote_totals, sort_keys=True)

    is_tie = len(winners) > 1
    winning_restaurant_id = None if is_tie else winners[0]

    result = vote_repo.save_result(
        event_id=event_id,
        restaurant_id=winning_restaurant_id,
        is_tie=is_tie,
        vote_totals_json=vote_totals_json,
    )
    winner_name = None if is_tie else id_to_name.get(winning_restaurant_id)
    return FinalizeOutcome(result=result, winner_name=winner_name)


def get_results(vote_repo: VoteRepository, event_id: int) -> Result | None:
    return vote_repo.get_result(event_id)

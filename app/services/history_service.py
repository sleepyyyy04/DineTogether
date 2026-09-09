"""
Application-logic layer for a logged-in user's cross-event history:
every event they've created or joined, what they voted for, and how
that event was finally decided. Composes EventRepository,
VoteRepository, and RestaurantRepository the same way
recommendation_service/voting_service do, so routes.py stays a thin
controller (ADR-0001).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.repositories.event_repository import Event, EventRepository
from app.repositories.restaurant_repository import Restaurant, RestaurantRepository
from app.repositories.vote_repository import VoteRepository


@dataclass
class HistoryEntry:
    event: Event
    my_choices: list[Restaurant]
    finalized: bool
    is_tie: bool
    winner: Restaurant | None


def get_history_for_user(
    event_repo: EventRepository,
    vote_repo: VoteRepository,
    restaurant_repo: RestaurantRepository,
    user_id: int,
) -> list[HistoryEntry]:
    entries = []
    for event in event_repo.list_events_for_user(user_id):
        participant = event_repo.get_participant_for_user(event.id, user_id)
        my_votes = vote_repo.get_votes_for_participant(event.id, participant.id) if participant else []
        my_choices = [restaurant_repo.get_by_id(vote.restaurant_id) for vote in my_votes]

        result = vote_repo.get_result(event.id)
        winner = restaurant_repo.get_by_id(result.restaurant_id) if result and result.restaurant_id else None

        entries.append(
            HistoryEntry(
                event=event,
                my_choices=my_choices,
                finalized=result is not None,
                is_tie=result.is_tie if result else False,
                winner=winner,
            )
        )
    return entries

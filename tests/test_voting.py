import json

import pytest

from app.repositories.preference_repository import PreferenceRepository
from app.repositories.restaurant_repository import RestaurantRepository
from app.repositories.vote_repository import VoteRepository
from app.services import event_service, preference_service, voting_service
from app.services.recommendation_service import get_recommendations


WIDE_OPEN = dict(
    raw_cuisines=["any"], raw_budgets=["$", "$$", "$$$", "$$$$"], raw_dietary=["none"], raw_max_distance="25"
)
NARROW = dict(raw_cuisines=["any"], raw_budgets=["$"], raw_dietary=["vegan"], raw_max_distance="1")


@pytest.fixture
def two_participants_with_preferences(db, make_user):
    from app.repositories.event_repository import EventRepository

    event_repo = EventRepository(db)
    pref_repo = PreferenceRepository(db)
    vote_repo = VoteRepository(db)

    alex = make_user(display_name="Alex", username="alex")
    ben = make_user(display_name="Ben", username="ben")

    organizer = event_service.create_event(event_repo, "Group Dinner", alex)
    joiner = event_service.join_event(event_repo, organizer.event.invite_code, ben)

    event_id = organizer.event.id
    preference_service.submit_preferences(pref_repo, vote_repo, event_id, organizer.participant.id, **WIDE_OPEN)
    preference_service.submit_preferences(pref_repo, vote_repo, event_id, joiner.participant.id, **WIDE_OPEN)

    return event_id, organizer.participant.id, joiner.participant.id


def _repos(db):
    return PreferenceRepository(db), RestaurantRepository(db), VoteRepository(db)


def test_cast_vote_records_a_vote_for_a_shortlisted_restaurant(db, two_participants_with_preferences):
    event_id, alex_id, _ = two_participants_with_preferences
    pref_repo, restaurant_repo, vote_repo = _repos(db)

    shortlist = get_recommendations(pref_repo, restaurant_repo, event_id).restaurants
    choice = shortlist[0]

    voting_service.cast_vote(pref_repo, restaurant_repo, vote_repo, event_id, alex_id, choice.id)

    recorded = vote_repo.get_vote_for_participant(event_id, alex_id)
    assert recorded.restaurant_id == choice.id


def test_casting_another_vote_replaces_the_previous_one(db, two_participants_with_preferences):
    """FR-05.2."""
    event_id, alex_id, _ = two_participants_with_preferences
    pref_repo, restaurant_repo, vote_repo = _repos(db)

    shortlist = get_recommendations(pref_repo, restaurant_repo, event_id).restaurants
    first_choice, second_choice = shortlist[0], shortlist[1]

    voting_service.cast_vote(pref_repo, restaurant_repo, vote_repo, event_id, alex_id, first_choice.id)
    voting_service.cast_vote(pref_repo, restaurant_repo, vote_repo, event_id, alex_id, second_choice.id)

    recorded = vote_repo.get_vote_for_participant(event_id, alex_id)
    assert recorded.restaurant_id == second_choice.id
    counts = vote_repo.get_vote_counts(event_id)
    assert counts == {second_choice.id: 1}


def test_cast_vote_rejects_a_restaurant_outside_the_shortlist(db, two_participants_with_preferences):
    event_id, alex_id, ben_id = two_participants_with_preferences
    pref_repo, restaurant_repo, vote_repo = _repos(db)

    # Narrow Ben's preferences so the group shortlist shrinks to a strict subset.
    preference_service.submit_preferences(pref_repo, vote_repo, event_id, ben_id, **NARROW)
    shortlist_ids = {r.id for r in get_recommendations(pref_repo, restaurant_repo, event_id).restaurants}

    excluded = next(r for r in restaurant_repo.list_all() if r.id not in shortlist_ids)

    with pytest.raises(voting_service.RestaurantNotOnShortlistError):
        voting_service.cast_vote(pref_repo, restaurant_repo, vote_repo, event_id, alex_id, excluded.id)


def test_finalize_with_no_votes_cast_raises(db, two_participants_with_preferences):
    event_id, _, _ = two_participants_with_preferences
    pref_repo, restaurant_repo, vote_repo = _repos(db)

    with pytest.raises(voting_service.NoShortlistError):
        voting_service.finalize(pref_repo, restaurant_repo, vote_repo, event_id)


def test_finalize_picks_the_restaurant_with_the_most_votes(db, two_participants_with_preferences):
    """FR-05.3/05.5."""
    event_id, alex_id, ben_id = two_participants_with_preferences
    pref_repo, restaurant_repo, vote_repo = _repos(db)

    winner = get_recommendations(pref_repo, restaurant_repo, event_id).restaurants[0]
    voting_service.cast_vote(pref_repo, restaurant_repo, vote_repo, event_id, alex_id, winner.id)
    voting_service.cast_vote(pref_repo, restaurant_repo, vote_repo, event_id, ben_id, winner.id)

    outcome = voting_service.finalize(pref_repo, restaurant_repo, vote_repo, event_id)

    assert outcome.result.is_tie is False
    assert outcome.result.restaurant_id == winner.id
    assert outcome.winner_name == winner.name
    assert json.loads(outcome.result.vote_totals) == {winner.name: 2}

    # The decision survives being read back independently (NFR-03.2).
    persisted = voting_service.get_results(vote_repo, event_id)
    assert persisted.restaurant_id == winner.id


def test_finalize_with_a_tie_saves_no_single_winner(db, two_participants_with_preferences):
    """FR-05.4: a tie must be shown, never silently resolved."""
    event_id, alex_id, ben_id = two_participants_with_preferences
    pref_repo, restaurant_repo, vote_repo = _repos(db)

    shortlist = get_recommendations(pref_repo, restaurant_repo, event_id).restaurants
    first_choice, second_choice = shortlist[0], shortlist[1]

    voting_service.cast_vote(pref_repo, restaurant_repo, vote_repo, event_id, alex_id, first_choice.id)
    voting_service.cast_vote(pref_repo, restaurant_repo, vote_repo, event_id, ben_id, second_choice.id)

    outcome = voting_service.finalize(pref_repo, restaurant_repo, vote_repo, event_id)

    assert outcome.result.is_tie is True
    assert outcome.result.restaurant_id is None
    assert outcome.winner_name is None


def test_vote_and_finalize_rejected_after_finalization(db, two_participants_with_preferences):
    event_id, alex_id, ben_id = two_participants_with_preferences
    pref_repo, restaurant_repo, vote_repo = _repos(db)

    winner = get_recommendations(pref_repo, restaurant_repo, event_id).restaurants[0]
    voting_service.cast_vote(pref_repo, restaurant_repo, vote_repo, event_id, alex_id, winner.id)
    voting_service.finalize(pref_repo, restaurant_repo, vote_repo, event_id)

    with pytest.raises(voting_service.EventFinalizedError):
        voting_service.cast_vote(pref_repo, restaurant_repo, vote_repo, event_id, ben_id, winner.id)

    # Finalizing again is idempotent: it returns the already-saved result rather than erroring.
    outcome = voting_service.finalize(pref_repo, restaurant_repo, vote_repo, event_id)
    assert outcome.result.restaurant_id == winner.id

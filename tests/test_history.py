import json

from app.repositories.event_repository import EventRepository
from app.repositories.restaurant_repository import RestaurantRepository
from app.repositories.vote_repository import VoteRepository
from app.services import event_service, history_service


def test_history_is_empty_for_a_user_with_no_events(db, user):
    entries = history_service.get_history_for_user(
        EventRepository(db), VoteRepository(db), RestaurantRepository(db), user.id
    )
    assert entries == []


def test_history_lists_events_the_user_created_or_joined(db, user, make_user):
    event_repo = EventRepository(db)
    ben = make_user(display_name="Ben", username="ben")

    created = event_service.create_event(event_repo, "Friday Dinner", user)
    event_service.join_event(event_repo, created.event.invite_code, ben)

    entries = history_service.get_history_for_user(
        event_repo, VoteRepository(db), RestaurantRepository(db), user.id
    )
    assert [e.event.name for e in entries] == ["Friday Dinner"]
    assert entries[0].finalized is False
    assert entries[0].my_choice is None


def test_history_does_not_include_events_the_user_never_joined(db, user, make_user):
    event_repo = EventRepository(db)
    ben = make_user(display_name="Ben", username="ben")
    event_service.create_event(event_repo, "Ben's Dinner", ben)

    entries = history_service.get_history_for_user(
        event_repo, VoteRepository(db), RestaurantRepository(db), user.id
    )
    assert entries == []


def test_history_shows_my_vote_and_the_final_result(db, user):
    event_repo = EventRepository(db)
    vote_repo = VoteRepository(db)
    restaurant_repo = RestaurantRepository(db)

    created = event_service.create_event(event_repo, "Friday Dinner", user)
    restaurant = restaurant_repo.list_all()[0]
    vote_repo.upsert_vote(created.event.id, created.participant.id, restaurant.id)
    vote_repo.save_result(
        created.event.id,
        restaurant_id=restaurant.id,
        is_tie=False,
        vote_totals_json=json.dumps({restaurant.name: 1}),
    )

    entries = history_service.get_history_for_user(event_repo, vote_repo, restaurant_repo, user.id)
    assert entries[0].my_choice.id == restaurant.id
    assert entries[0].finalized is True
    assert entries[0].is_tie is False
    assert entries[0].winner.id == restaurant.id

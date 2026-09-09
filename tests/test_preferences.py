import pytest

from app.repositories.event_repository import EventRepository
from app.repositories.preference_repository import PreferenceRepository
from app.repositories.restaurant_repository import RestaurantRepository
from app.repositories.vote_repository import VoteRepository
from app.services import event_service, preference_service
from app.services.validators import ValidationError


@pytest.fixture
def participant(db, user):
    repo = EventRepository(db)
    result = event_service.create_event(repo, "Friday Team Dinner", user)
    return result.event.id, result.participant.id


def test_submit_preferences_stores_valid_values(db, participant):
    event_id, participant_id = participant
    pref_repo = PreferenceRepository(db)
    vote_repo = VoteRepository(db)

    saved = preference_service.submit_preferences(
        pref_repo, vote_repo, event_id, participant_id, ["Italian"], ["$$"], ["vegetarian"], "5.0"
    )

    assert saved.cuisines == ["Italian"]
    assert saved.budget_levels == [2]
    assert saved.dietary == ["vegetarian"]
    assert saved.max_distance_mi == 5.0


def test_submit_preferences_stores_multiple_selections_per_field(db, participant):
    event_id, participant_id = participant
    pref_repo = PreferenceRepository(db)
    vote_repo = VoteRepository(db)

    saved = preference_service.submit_preferences(
        pref_repo,
        vote_repo,
        event_id,
        participant_id,
        ["Italian", "Thai"],
        ["$", "$$"],
        ["vegetarian", "gluten_free"],
        "5.0",
    )

    assert saved.cuisines == ["Italian", "Thai"]
    assert saved.budget_levels == [1, 2]
    assert saved.dietary == ["vegetarian", "gluten_free"]


def test_submitting_again_replaces_the_previous_preference_set(db, participant):
    """FR-03.2/03.3: one current preference set per participant."""
    event_id, participant_id = participant
    pref_repo = PreferenceRepository(db)
    vote_repo = VoteRepository(db)

    preference_service.submit_preferences(
        pref_repo, vote_repo, event_id, participant_id, ["Italian"], ["$$"], ["vegetarian"], "5.0"
    )
    updated = preference_service.submit_preferences(
        pref_repo, vote_repo, event_id, participant_id, ["Thai"], ["$$$$"], ["none"], "10.0"
    )

    assert updated.cuisines == ["Thai"]
    all_prefs = pref_repo.list_for_event(event_id)
    assert len(all_prefs) == 1
    assert all_prefs[0].cuisines == ["Thai"]


@pytest.mark.parametrize(
    "field, args",
    [
        ("cuisine", ([], ["$$"], ["none"], "5.0")),
        ("cuisine", (["Klingon"], ["$$"], ["none"], "5.0")),
        ("budget", (["Italian"], [], ["none"], "5.0")),
        ("budget", (["Italian"], ["free"], ["none"], "5.0")),
        ("dietary", (["Italian"], ["$$"], [], "5.0")),
        ("dietary", (["Italian"], ["$$"], ["carnivore"], "5.0")),
        ("max_distance", (["Italian"], ["$$"], ["none"], "not-a-number")),
        ("max_distance", (["Italian"], ["$$"], ["none"], "0.1")),
        ("max_distance", (["Italian"], ["$$"], ["none"], "100")),
        ("min_rating", (["Italian"], ["$$"], ["none"], "5.0", "not-a-number")),
        ("min_rating", (["Italian"], ["$$"], ["none"], "5.0", "5.1")),
        ("min_rating", (["Italian"], ["$$"], ["none"], "5.0", "-1")),
    ],
)
def test_submit_preferences_rejects_invalid_values(db, participant, field, args):
    event_id, participant_id = participant
    pref_repo = PreferenceRepository(db)
    vote_repo = VoteRepository(db)

    with pytest.raises(ValidationError) as exc_info:
        preference_service.submit_preferences(pref_repo, vote_repo, event_id, participant_id, *args)
    assert exc_info.value.field == field


@pytest.mark.parametrize("distance", ["0.5", "75.0"])
def test_submit_preferences_accepts_boundary_distances(db, participant, distance):
    event_id, participant_id = participant
    pref_repo = PreferenceRepository(db)
    vote_repo = VoteRepository(db)

    saved = preference_service.submit_preferences(
        pref_repo, vote_repo, event_id, participant_id, ["any"], ["$"], ["none"], distance
    )
    assert saved.max_distance_mi == float(distance)


def test_min_rating_is_optional(db, participant):
    event_id, participant_id = participant
    pref_repo = PreferenceRepository(db)
    vote_repo = VoteRepository(db)

    left_blank = preference_service.submit_preferences(
        pref_repo, vote_repo, event_id, participant_id, ["Italian"], ["$$"], ["none"], "5.0"
    )
    assert left_blank.min_rating is None

    with_rating = preference_service.submit_preferences(
        pref_repo, vote_repo, event_id, participant_id, ["Italian"], ["$$"], ["none"], "5.0", "4.0"
    )
    assert with_rating.min_rating == 4.0


def test_submit_preferences_rejected_once_event_is_finalized(db, participant):
    event_id, participant_id = participant
    pref_repo = PreferenceRepository(db)
    vote_repo = VoteRepository(db)
    vote_repo.save_result(event_id, restaurant_id=None, is_tie=False, vote_totals_json="{}")

    with pytest.raises(preference_service.EventFinalizedError):
        preference_service.submit_preferences(
            pref_repo, vote_repo, event_id, participant_id, ["Italian"], ["$$"], ["none"], "5.0"
        )


def test_submit_preferences_rejected_once_participant_has_voted(db, participant):
    """The shortlist a ballot was cast against must not shift under
    it, so preferences lock for that participant as soon as they
    vote — independent of whether the event has been finalized."""
    event_id, participant_id = participant
    pref_repo = PreferenceRepository(db)
    vote_repo = VoteRepository(db)
    restaurant_id = RestaurantRepository(db).list_all()[0].id

    preference_service.submit_preferences(
        pref_repo, vote_repo, event_id, participant_id, ["Italian"], ["$$"], ["none"], "5.0"
    )
    vote_repo.set_votes(event_id, participant_id, [restaurant_id])

    with pytest.raises(preference_service.AlreadyVotedError):
        preference_service.submit_preferences(
            pref_repo, vote_repo, event_id, participant_id, ["Thai"], ["$$$$"], ["none"], "10.0"
        )

import pytest

from app.repositories.event_repository import EventRepository
from app.repositories.preference_repository import PreferenceRepository
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
    ],
)
def test_submit_preferences_rejects_invalid_values(db, participant, field, args):
    event_id, participant_id = participant
    pref_repo = PreferenceRepository(db)
    vote_repo = VoteRepository(db)

    with pytest.raises(ValidationError) as exc_info:
        preference_service.submit_preferences(pref_repo, vote_repo, event_id, participant_id, *args)
    assert exc_info.value.field == field


@pytest.mark.parametrize("distance", ["0.5", "25.0"])
def test_submit_preferences_accepts_boundary_distances(db, participant, distance):
    event_id, participant_id = participant
    pref_repo = PreferenceRepository(db)
    vote_repo = VoteRepository(db)

    saved = preference_service.submit_preferences(
        pref_repo, vote_repo, event_id, participant_id, ["any"], ["$"], ["none"], distance
    )
    assert saved.max_distance_mi == float(distance)


def test_submit_preferences_rejected_once_event_is_finalized(db, participant):
    event_id, participant_id = participant
    pref_repo = PreferenceRepository(db)
    vote_repo = VoteRepository(db)
    vote_repo.save_result(event_id, restaurant_id=None, is_tie=False, vote_totals_json="{}")

    with pytest.raises(preference_service.EventFinalizedError):
        preference_service.submit_preferences(
            pref_repo, vote_repo, event_id, participant_id, ["Italian"], ["$$"], ["none"], "5.0"
        )

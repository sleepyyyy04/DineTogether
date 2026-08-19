import pytest

from app.repositories.event_repository import EventRepository
from app.services import event_service
from app.services.validators import ValidationError


@pytest.fixture
def existing_event(db, make_user):
    repo = EventRepository(db)
    organizer = make_user(display_name="Organizer", username="organizer")
    return event_service.create_event(repo, "Friday Team Dinner", organizer).event


def test_join_event_with_valid_code_succeeds(db, existing_event, make_user):
    repo = EventRepository(db)
    priya = make_user(display_name="Priya", username="priya")
    result = event_service.join_event(repo, existing_event.invite_code, priya)

    assert result.event.id == existing_event.id
    # The joiner's display name comes from their account, not a form field.
    assert result.participant.display_name == "Priya"
    # The organizer ("Organizer", from the existing_event fixture) is already
    # a participant, so the joiner is the second entry, not the first.
    names = [p.display_name for p in repo.list_participants(existing_event.id)]
    assert names == ["Organizer", "Priya"]


def test_join_event_rejects_malformed_code(db, existing_event, user):
    repo = EventRepository(db)
    with pytest.raises(ValidationError) as exc_info:
        event_service.join_event(repo, "not-a-code!", user)
    assert exc_info.value.field == "code"


def test_join_event_rejects_unknown_but_well_formed_code(db, existing_event, user):
    """FR-02.2. Added after the review found the AI's original tests
    never exercised this path (Finding 4)."""
    repo = EventRepository(db)
    with pytest.raises(event_service.EventNotFoundError):
        event_service.join_event(repo, "ZZZZ", user)


def test_joining_the_same_event_twice_is_idempotent(db, existing_event, make_user):
    """UNIQUE(event_id, user_id) in the schema: re-visiting an invite
    link with the same account must reuse the existing participant
    row instead of erroring or creating a duplicate."""
    repo = EventRepository(db)
    priya = make_user(display_name="Priya", username="priya")

    first = event_service.join_event(repo, existing_event.invite_code, priya)
    second = event_service.join_event(repo, existing_event.invite_code, priya)

    assert first.participant.id == second.participant.id
    names = [p.display_name for p in repo.list_participants(existing_event.id)]
    assert names == ["Organizer", "Priya"]

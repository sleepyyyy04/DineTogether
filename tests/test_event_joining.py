import pytest

from app.repositories.event_repository import EventRepository
from app.repositories.vote_repository import VoteRepository
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
    result = event_service.join_event(repo, VoteRepository(db), existing_event.invite_code, priya)

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
        event_service.join_event(repo, VoteRepository(db), "not-a-code!", user)
    assert exc_info.value.field == "code"


def test_join_event_rejects_unknown_but_well_formed_code(db, existing_event, user):
    """FR-02.2. Added after the review found the AI's original tests
    never exercised this path (Finding 4)."""
    repo = EventRepository(db)
    with pytest.raises(event_service.EventNotFoundError):
        event_service.join_event(repo, VoteRepository(db), "ZZZZ", user)


def test_joining_the_same_event_twice_is_idempotent(db, existing_event, make_user):
    """UNIQUE(event_id, user_id) in the schema: re-visiting an invite
    link with the same account must reuse the existing participant
    row instead of erroring or creating a duplicate."""
    repo = EventRepository(db)
    vote_repo = VoteRepository(db)
    priya = make_user(display_name="Priya", username="priya")

    first = event_service.join_event(repo, vote_repo, existing_event.invite_code, priya)
    second = event_service.join_event(repo, vote_repo, existing_event.invite_code, priya)

    assert first.participant.id == second.participant.id
    names = [p.display_name for p in repo.list_participants(existing_event.id)]
    assert names == ["Organizer", "Priya"]


def test_join_event_rejects_an_expired_invite_code(db, existing_event, make_user):
    """A new participant may not join more than INVITE_CODE_TTL after
    the event was created."""
    repo = EventRepository(db)
    priya = make_user(display_name="Priya", username="priya")

    db.execute(
        "UPDATE events SET created_at = datetime('now', '-1 hour') WHERE id = ?",
        (existing_event.id,),
    )
    db.commit()

    with pytest.raises(event_service.InviteCodeExpiredError):
        event_service.join_event(repo, VoteRepository(db), existing_event.invite_code, priya)


def test_join_event_rejects_a_finalized_event(db, existing_event, make_user):
    """A new participant may not join an event whose result has
    already been saved, regardless of how recently it was created."""
    repo = EventRepository(db)
    vote_repo = VoteRepository(db)
    priya = make_user(display_name="Priya", username="priya")

    vote_repo.save_result(existing_event.id, restaurant_id=None, is_tie=True, vote_totals_json="{}")

    with pytest.raises(event_service.EventAlreadyFinalizedError):
        event_service.join_event(repo, vote_repo, existing_event.invite_code, priya)

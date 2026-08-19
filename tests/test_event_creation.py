import pytest

from app.repositories.event_repository import EventRepository
from app.services import event_service
from app.services.validators import ValidationError


def test_create_event_stores_name_and_returns_unique_code(db, user):
    repo = EventRepository(db)
    result = event_service.create_event(repo, "Friday Team Dinner", user)

    assert result.event.id is not None
    assert result.event.name == "Friday Team Dinner"
    assert len(result.event.invite_code) == 4
    assert repo.get_event_by_code(result.event.invite_code).id == result.event.id
    # The organizer is added as a participant immediately (SRS 2.3),
    # using their account's display name.
    assert result.participant.display_name == "Alex"
    assert repo.list_participants(result.event.id)[0].display_name == "Alex"


def test_create_event_rejects_blank_name(db, user):
    repo = EventRepository(db)
    with pytest.raises(ValidationError) as exc_info:
        event_service.create_event(repo, "   ", user)
    assert exc_info.value.field == "name"


def test_create_event_rejects_overlong_name(db, user):
    repo = EventRepository(db)
    with pytest.raises(ValidationError) as exc_info:
        event_service.create_event(repo, "x" * 81, user)
    assert exc_info.value.field == "name"


def test_generate_unique_invite_code_retries_on_collision(db, user, monkeypatch):
    """Regression test for code-review Finding 1: the old
    implementation inserted the first generated code with no
    uniqueness check, so a collision silently attached a new event
    to an existing invitation code."""
    repo = EventRepository(db)

    # Seed an existing event using a known code.
    repo.create_event("Existing Event", "AB12")

    # Force the generator to return the colliding code first, then a
    # fresh one, and confirm the service does not accept the collision.
    calls = {"count": 0}
    real_choice_sequence = list("AB12") + list("CD34")

    def fake_choice(_alphabet):
        idx = calls["count"]
        calls["count"] += 1
        return real_choice_sequence[idx]

    monkeypatch.setattr(event_service.secrets, "choice", fake_choice)

    new_event = event_service.create_event(repo, "New Event", user).event

    assert new_event.invite_code == "CD34"
    assert new_event.invite_code != "AB12"
    # Both events must independently resolve to their own code.
    assert repo.get_event_by_code("AB12").name == "Existing Event"
    assert repo.get_event_by_code("CD34").name == "New Event"

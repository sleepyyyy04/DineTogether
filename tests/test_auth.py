import pytest
from werkzeug.security import check_password_hash

from app.services import auth_service
from app.services.validators import ValidationError


def test_register_creates_a_user_with_a_hashed_password(db, user_repo):
    result = auth_service.register(user_repo, "alex", "password123", "Alex")

    assert result.user.username == "alex"
    assert result.user.display_name == "Alex"
    assert result.user.password_hash != "password123"
    assert check_password_hash(result.user.password_hash, "password123")


def test_register_normalizes_username_case_and_whitespace(db, user_repo):
    result = auth_service.register(user_repo, "  Alex  ", "password123", "Alex")
    assert result.user.username == "alex"


def test_register_rejects_a_duplicate_username(db, user_repo):
    auth_service.register(user_repo, "alex", "password123", "Alex")
    with pytest.raises(auth_service.UsernameAlreadyRegisteredError):
        auth_service.register(user_repo, "alex", "different-pass", "Someone Else")


@pytest.mark.parametrize(
    "field, args",
    [
        ("username", ("ab", "password123", "Alex")),  # too short
        ("username", ("a" * 31, "password123", "Alex")),  # too long
        ("username", ("has spaces", "password123", "Alex")),
        ("username", ("has@symbol", "password123", "Alex")),
        ("password", ("alex", "short", "Alex")),
        ("password", ("alex", "x" * 73, "Alex")),
        ("display_name", ("alex", "password123", "")),
    ],
)
def test_register_rejects_invalid_values(db, user_repo, field, args):
    with pytest.raises(ValidationError) as exc_info:
        auth_service.register(user_repo, *args)
    assert exc_info.value.field == field


def test_login_succeeds_with_correct_credentials(db, user_repo):
    auth_service.register(user_repo, "alex", "password123", "Alex")
    user = auth_service.login(user_repo, "alex", "password123")
    assert user.username == "alex"


def test_login_is_case_insensitive_on_username(db, user_repo):
    auth_service.register(user_repo, "alex", "password123", "Alex")
    user = auth_service.login(user_repo, "Alex", "password123")
    assert user.username == "alex"


def test_login_rejects_unknown_username(db, user_repo):
    with pytest.raises(auth_service.InvalidCredentialsError):
        auth_service.login(user_repo, "nobody", "password123")


def test_login_rejects_wrong_password(db, user_repo):
    auth_service.register(user_repo, "alex", "password123", "Alex")
    with pytest.raises(auth_service.InvalidCredentialsError):
        auth_service.login(user_repo, "alex", "wrong-password")

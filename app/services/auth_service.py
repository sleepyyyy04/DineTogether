"""
Application-logic layer for account registration and login. Routes
call only this module; it is the only caller of UserRepository for
writes (ADR-0001 layering).
"""
from __future__ import annotations

from dataclasses import dataclass

from werkzeug.security import check_password_hash, generate_password_hash

from app.repositories.user_repository import User, UserRepository
from app.services.validators import validate_display_name, validate_password, validate_username


class UsernameAlreadyRegisteredError(Exception):
    """Raised when registering with a username that's already in use."""


class InvalidCredentialsError(Exception):
    """Raised on login when the username/password pair doesn't match.
    Deliberately doesn't distinguish an unknown username from a wrong
    password — either detail would let a login attempt be used to
    enumerate registered accounts."""


@dataclass
class RegisterResult:
    user: User


def register(
    user_repo: UserRepository, raw_username: str, raw_password: str, raw_display_name: str
) -> RegisterResult:
    username = validate_username(raw_username)
    password = validate_password(raw_password)
    display_name = validate_display_name(raw_display_name)

    if user_repo.get_by_username(username) is not None:
        raise UsernameAlreadyRegisteredError(username)

    password_hash = generate_password_hash(password)
    user = user_repo.create(username=username, password_hash=password_hash, display_name=display_name)
    return RegisterResult(user=user)


def login(user_repo: UserRepository, raw_username: str, raw_password: str) -> User:
    username = (raw_username or "").strip().lower()
    user = user_repo.get_by_username(username)
    if user is None or not check_password_hash(user.password_hash, raw_password or ""):
        raise InvalidCredentialsError()
    return user

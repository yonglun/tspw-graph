from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class PasswordPolicy:
    @staticmethod
    def validate(password: str) -> list[str]:
        failures: list[str] = []
        if len(password) < 10:
            failures.append("MIN_LENGTH")
        if not any(character.isupper() for character in password):
            failures.append("UPPERCASE_REQUIRED")
        if not any(character.islower() for character in password):
            failures.append("LOWERCASE_REQUIRED")
        if not any(character.isdigit() for character in password):
            failures.append("DIGIT_REQUIRED")
        if not any(not character.isalnum() for character in password):
            failures.append("SPECIAL_REQUIRED")
        return failures


class PasswordSecurity:
    def __init__(self) -> None:
        self._hasher = PasswordHasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, hash_value: str, password: str) -> bool:
        try:
            return self._hasher.verify(hash_value, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def csrf_matches(expected: str, presented: str) -> bool:
    return bool(presented) and secrets.compare_digest(expected, presented)

from app.auth.security import PasswordPolicy, PasswordSecurity, csrf_matches, hash_session_token, new_token


def test_password_policy_reports_each_missing_requirement():
    assert PasswordPolicy.validate("short") == ["MIN_LENGTH", "UPPERCASE_REQUIRED", "DIGIT_REQUIRED", "SPECIAL_REQUIRED"]
    assert PasswordPolicy.validate("Pass@word1") == []


def test_hash_and_verify_password_without_plaintext_storage():
    encoded = PasswordSecurity().hash("Pass@word1")
    assert "Pass@word1" not in encoded
    assert PasswordSecurity().verify(encoded, "Pass@word1") is True
    assert PasswordSecurity().verify(encoded, "wrong-password") is False


def test_session_token_hash_is_stable_and_csrf_compare_is_exact():
    token = new_token()
    assert token != hash_session_token(token)
    assert hash_session_token(token) == hash_session_token(token)
    assert csrf_matches("csrf-value", "csrf-value") is True
    assert csrf_matches("csrf-value", "different") is False

"""Authentication, password hashing and user administration tests."""
from __future__ import annotations

import pytest

from app import AuthenticationError, DataConflictError, ValidationError
from app.security import hash_password, password_problems, verify_password
from database.seed_data import DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME


def test_default_administrator_can_log_in(auth):
    user = auth.login(DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD)
    assert user.is_admin is True
    assert user.password_hash != DEFAULT_ADMIN_PASSWORD  # never stored as plain text


def test_wrong_password_is_rejected(auth):
    with pytest.raises(AuthenticationError):
        auth.login(DEFAULT_ADMIN_USERNAME, "not-the-password")


def test_unknown_user_is_rejected(auth):
    with pytest.raises(AuthenticationError):
        auth.login("ghost", DEFAULT_ADMIN_PASSWORD)


def test_empty_input_is_rejected(auth):
    with pytest.raises(AuthenticationError):
        auth.login("", "")


def test_seed_data_runs_only_once(db, auth):
    assert db.seed_if_needed() is False
    assert db.setting("seed_version") == "1"
    assert auth.login(DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD) is not None


def test_passwords_are_hashed_with_a_random_salt():
    salt_one, hash_one = hash_password("admin123")
    salt_two, hash_two = hash_password("admin123")
    assert salt_one != salt_two
    assert hash_one != hash_two
    assert verify_password("admin123", salt_one, hash_one)
    assert not verify_password("admin123", salt_two, hash_one)


def test_verify_password_rejects_corrupt_stored_values():
    assert verify_password("admin123", "not-hex", "also-not-hex") is False


def test_password_policy_is_enforced():
    assert password_problems("short") != []
    assert password_problems("nodigitshere") != []
    assert password_problems("admin123", "admin124") != []
    assert password_problems("admin123", "admin123") == []


def test_create_user_and_login(auth):
    user_id = auth.create_user(username="staff.one", full_name="Staff One",
                               role="staff", password="access123",
                               confirm="access123")
    user = auth.login("STAFF.ONE", "access123")
    assert user.id == user_id
    assert user.role == "staff"
    assert user.is_admin is False


def test_duplicate_username_is_rejected(auth):
    auth.create_user(username="manager.one", full_name="Manager One",
                     role="manager", password="access123")
    with pytest.raises(DataConflictError):
        auth.create_user(username="manager.one", full_name="Another Manager",
                         role="manager", password="access123")


def test_weak_password_is_rejected(auth):
    with pytest.raises(ValidationError):
        auth.create_user(username="weak.user", full_name="Weak User",
                         role="staff", password="abc", confirm="abc")


def test_last_administrator_cannot_be_deactivated(auth):
    admin = auth.login(DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD)
    from app import OperationError

    with pytest.raises(OperationError):
        auth.update_user(admin.id, is_active=False)


def test_reset_and_change_password(auth):
    auth.create_user(username="temp.user", full_name="Temp User",
                     role="staff", password="access123")
    row = auth.db.fetch_one("SELECT id FROM users WHERE username = ?", ("temp.user",))
    auth.reset_password(int(row["id"]), "newpass1", "newpass1")
    assert auth.login("temp.user", "newpass1") is not None
    with pytest.raises(AuthenticationError):
        auth.change_password(int(row["id"]), "wrong", "another1", "another1")
    auth.change_password(int(row["id"]), "newpass1", "another1", "another1")
    assert auth.login("temp.user", "another1") is not None

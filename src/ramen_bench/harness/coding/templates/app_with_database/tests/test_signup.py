import uuid

import pytest
from app.users import DuplicateEmail, create_user, get_user


def test_create_user(db):
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    create_user(db, email, "Test User")
    assert get_user(db, email)["name"] == "Test User"


def test_email_is_normalised(db):
    email = f"Mixed-{uuid.uuid4().hex[:8]}@Example.COM "
    create_user(db, email, "Mixed Case")
    assert get_user(db, email.strip().lower()) is not None


def test_unique_email(db):
    create_user(db, "dana@example.com", "Dana")
    with pytest.raises(DuplicateEmail):
        create_user(db, "Dana@Example.com", "Dana Again")

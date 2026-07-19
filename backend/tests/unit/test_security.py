import uuid

import pytest

from core.exceptions import AuthenticationError
from core.ids import uuid7
from core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_token,
    new_api_key,
    verify_password,
)


def test_password_hash_roundtrip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip():
    uid, org = uuid.uuid4(), uuid.uuid4()
    token = create_access_token(user_id=uid, org_id=org, role="editor")
    payload = decode_access_token(token)
    assert payload["sub"] == str(uid)
    assert payload["role"] == "editor"


def test_jwt_garbage_rejected():
    with pytest.raises(AuthenticationError):
        decode_access_token("not.a.token")


def test_api_key_format_and_hash_stability():
    key = new_api_key()
    assert key.startswith("kmb_")
    assert hash_token(key) == hash_token(key)
    assert len(hash_token(key)) == 64


def test_uuid7_time_ordered():
    a, b = uuid7(), uuid7()
    assert a.version == 7
    assert a.bytes[:6] <= b.bytes[:6]


def test_pii_redaction():
    from utils.pii import redact_pii

    assert "<email>" in redact_pii("contact s.kumar@cvum.io now")
    assert "password=<redacted>" in redact_pii("password: hunter2secret")

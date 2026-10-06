from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from jose import jwt
from pydantic import SecretStr

from app.config import settings
from app.services.auth import AuthService


def test_auth_accepts_only_hs256_with_application_secret(monkeypatch):
    secret = "independent-application-secret-for-auth-test"
    monkeypatch.setattr(settings, "secret_key", SecretStr(secret))
    service = AuthService(Mock(), Mock())
    claims = {"sub": "creator", "type": "access", "jti": "test-id",
              "exp": datetime.now(timezone.utc) + timedelta(minutes=1)}
    valid = jwt.encode(claims, secret, algorithm="HS256")
    assert service.decode_token(valid).sub == "creator"
    # Knowing another key (including a public DER key) must not permit HMAC forgery.
    for key, algorithm in [(secret, "HS384"), (secret, "HS512"),
                           (b"attacker-known-public-key-material", "HS256")]:
        token = jwt.encode(claims, key, algorithm=algorithm)
        with pytest.raises(HTTPException) as exc:
            service.decode_token(token)
        assert exc.value.status_code == 401

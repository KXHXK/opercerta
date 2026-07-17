from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import SecretStr

from opercerta.api.auth import (
    AuthenticatedActor,
    AuthenticationRequired,
    DemoAccount,
    DemoTokenUnavailable,
    InvalidAccessToken,
    JwtAuthenticator,
    JwtSettings,
    Role,
)


def make_settings(*, demo_token_enabled: bool = True) -> JwtSettings:
    return JwtSettings(
        signing_key=SecretStr("unit-test-signing-key-not-production"),
        issuer="opercerta-unit-test",
        audience="opercerta-unit-test-api",
        ttl_seconds=300,
        demo_token_enabled=demo_token_enabled,
    )


def make_authenticator(*, demo_token_enabled: bool = True) -> JwtAuthenticator:
    return JwtAuthenticator(make_settings(demo_token_enabled=demo_token_enabled))


def now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def test_issued_approver_token_round_trips_to_fixed_demo_actor() -> None:
    authenticator = make_authenticator()
    token = authenticator.issue_demo_token(DemoAccount.APPROVER, now())

    assert authenticator.authenticate(f"Bearer {token}") == AuthenticatedActor(
        subject="demo.approver",
        role=Role.APPROVER,
    )


def test_issued_token_has_required_short_lived_claims() -> None:
    issued_at = now()
    authenticator = make_authenticator()
    token = authenticator.issue_demo_token(DemoAccount.OPERATOR, issued_at)

    claims = jwt.decode(token, options={"verify_signature": False})

    assert claims["sub"] == "demo.operator"
    assert claims["role"] == "operator"
    assert claims["iss"] == "opercerta-unit-test"
    assert claims["aud"] == "opercerta-unit-test-api"
    assert claims["iat"] == int(issued_at.timestamp())
    assert claims["exp"] == int((issued_at + timedelta(seconds=300)).timestamp())
    assert isinstance(claims["jti"], str) and claims["jti"]


@pytest.mark.parametrize("authorization", [None, "Basic x", "Bearer"])
def test_missing_or_malformed_authorization_is_rejected(
    authorization: str | None,
) -> None:
    with pytest.raises(AuthenticationRequired):
        make_authenticator().authenticate(authorization)


def test_malformed_bearer_token_is_invalid() -> None:
    with pytest.raises(InvalidAccessToken):
        make_authenticator().authenticate("Bearer malformed")


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": now() - timedelta(seconds=1)},
        {"iss": "unexpected-issuer"},
        {"aud": "unexpected-audience"},
        {"role": "unknown-role"},
    ],
)
def test_invalid_claims_are_rejected_without_exposing_jwt_details(
    claims: dict[str, object],
) -> None:
    settings = make_settings()
    token = jwt.encode(
        {
            "sub": "demo.approver",
            "role": "approver",
            "iss": settings.issuer,
            "aud": settings.audience,
            "iat": now(),
            "exp": now() + timedelta(seconds=300),
            "jti": "test-jti",
            **claims,
        },
        settings.signing_key.get_secret_value(),
        algorithm="HS256",
    )

    with pytest.raises(InvalidAccessToken) as error:
        JwtAuthenticator(settings).authenticate(f"Bearer {token}")

    assert str(error.value) == "invalid_access_token"


def test_tampered_signature_is_rejected() -> None:
    authenticator = make_authenticator()
    token = authenticator.issue_demo_token(DemoAccount.AUDITOR, now())
    replacement = "a" if token[-1] != "a" else "b"

    with pytest.raises(InvalidAccessToken):
        authenticator.authenticate(f"Bearer {token[:-1]}{replacement}")


def test_demo_token_issuer_is_explicitly_disabled_by_setting() -> None:
    with pytest.raises(DemoTokenUnavailable):
        make_authenticator(demo_token_enabled=False).issue_demo_token(
            DemoAccount.DEMO_ADMIN,
            now(),
        )

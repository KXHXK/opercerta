from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated
from uuid import uuid4

import jwt
from pydantic import (
    BaseModel,
    ConfigDict,
    PositiveInt,
    SecretStr,
    StringConstraints,
    ValidationError,
)

Subject = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
Issuer = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
Audience = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]


class Role(StrEnum):
    OPERATOR = "operator"
    APPROVER = "approver"
    AUDITOR = "auditor"
    DEMO_ADMIN = "demo-admin"


class DemoAccount(StrEnum):
    OPERATOR = "operator"
    APPROVER = "approver"
    AUDITOR = "auditor"
    DEMO_ADMIN = "demo-admin"


@dataclass(frozen=True, slots=True)
class AuthenticatedActor:
    subject: str
    role: Role


class JwtSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signing_key: SecretStr
    issuer: Issuer
    audience: Audience
    ttl_seconds: PositiveInt
    demo_token_enabled: bool


class AuthenticationRequired(RuntimeError):
    code = "authentication_required"

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidAccessToken(RuntimeError):
    code = "invalid_access_token"

    def __init__(self) -> None:
        super().__init__(self.code)


class PermissionDenied(RuntimeError):
    code = "permission_denied"

    def __init__(self) -> None:
        super().__init__(self.code)


class DemoTokenUnavailable(RuntimeError):
    code = "demo_token_unavailable"

    def __init__(self) -> None:
        super().__init__(self.code)


DEMO_ACTORS: dict[DemoAccount, AuthenticatedActor] = {
    DemoAccount.OPERATOR: AuthenticatedActor("demo.operator", Role.OPERATOR),
    DemoAccount.APPROVER: AuthenticatedActor("demo.approver", Role.APPROVER),
    DemoAccount.AUDITOR: AuthenticatedActor("demo.auditor", Role.AUDITOR),
    DemoAccount.DEMO_ADMIN: AuthenticatedActor("demo.admin", Role.DEMO_ADMIN),
}


class _TokenClaims(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sub: Subject
    role: Role
    iss: Issuer
    aud: Audience
    iat: int
    exp: int
    jti: str


class JwtAuthenticator:
    def __init__(self, settings: JwtSettings) -> None:
        self._settings = settings

    @property
    def ttl_seconds(self) -> int:
        return int(self._settings.ttl_seconds)

    def issue_demo_token(self, account: DemoAccount, issued_at: datetime) -> str:
        if not self._settings.demo_token_enabled:
            raise DemoTokenUnavailable
        if issued_at.tzinfo is None or issued_at.utcoffset() is None:
            raise ValueError("issued_at must include timezone")
        actor = DEMO_ACTORS[account]
        expiration = issued_at.astimezone(UTC) + timedelta(seconds=self.ttl_seconds)
        claims = {
            "sub": actor.subject,
            "role": actor.role.value,
            "iss": self._settings.issuer,
            "aud": self._settings.audience,
            "iat": issued_at.astimezone(UTC),
            "exp": expiration,
            "jti": uuid4().hex,
        }
        return jwt.encode(
            claims,
            self._settings.signing_key.get_secret_value(),
            algorithm="HS256",
        )

    def authenticate(self, authorization: str | None) -> AuthenticatedActor:
        token = self._bearer_token(authorization)
        try:
            payload = jwt.decode(
                token,
                self._settings.signing_key.get_secret_value(),
                algorithms=["HS256"],
                issuer=self._settings.issuer,
                audience=self._settings.audience,
                options={
                    "require": ["sub", "role", "iss", "aud", "iat", "exp", "jti"],
                },
            )
            claims = _TokenClaims.model_validate(payload)
        except (jwt.InvalidTokenError, ValidationError) as error:
            raise InvalidAccessToken from error
        return AuthenticatedActor(subject=claims.sub, role=claims.role)

    @staticmethod
    def _bearer_token(authorization: str | None) -> str:
        if authorization is None or not authorization.startswith("Bearer "):
            raise AuthenticationRequired
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise AuthenticationRequired
        return token

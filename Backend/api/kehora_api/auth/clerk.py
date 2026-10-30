"""Clerk session JWT verification (PRD 10: Clerk JWT in the Authorization header).

Keys come from the instance JWKS (`<issuer>/.well-known/jwks.json`), cached by `kid` and
refetched when an unknown `kid` appears (key rotation), at most once per minute.
"""

import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

JWKS_REFETCH_MIN_INTERVAL = 60.0
LEEWAY_SECONDS = 5


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class ClerkClaims:
    user_id: str
    org_id: str | None
    raw: dict[str, Any]


class JwksCache:
    def __init__(self, jwks_url: str, http: httpx.AsyncClient) -> None:
        self._url = jwks_url
        self._http = http
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at = 0.0

    async def _refresh(self) -> None:
        resp = await self._http.get(self._url, timeout=5.0)
        resp.raise_for_status()
        keys = {}
        for jwk in resp.json().get("keys", []):
            if jwk.get("kid"):
                keys[jwk["kid"]] = jwt.PyJWK(jwk)
        self._keys = keys
        self._fetched_at = time.monotonic()

    async def get(self, kid: str) -> jwt.PyJWK:
        if kid not in self._keys and (
            time.monotonic() - self._fetched_at > JWKS_REFETCH_MIN_INTERVAL or not self._keys
        ):
            await self._refresh()
        try:
            return self._keys[kid]
        except KeyError:
            raise AuthError("unknown signing key") from None


class ClerkVerifier:
    def __init__(self, issuer: str, authorized_parties: list[str], http: httpx.AsyncClient) -> None:
        self.issuer = issuer.rstrip("/")
        self.authorized_parties = authorized_parties
        self.jwks = JwksCache(f"{self.issuer}/.well-known/jwks.json", http)

    async def verify(self, token: str) -> ClerkClaims:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthError("malformed token") from exc
        if header.get("alg") != "RS256" or not header.get("kid"):
            raise AuthError("unsupported token header")
        key = await self.jwks.get(header["kid"])
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                leeway=LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "sub", "iss"], "verify_aud": False},
            )
        except jwt.PyJWTError as exc:
            raise AuthError(str(exc)) from exc

        azp = claims.get("azp")
        if azp is not None and self.authorized_parties and azp not in self.authorized_parties:
            raise AuthError("unauthorized party")

        # Session token v2 carries the active org as `o.id`; v1 used `org_id`.
        org = claims.get("o")
        org_id = org.get("id") if isinstance(org, dict) else claims.get("org_id")
        return ClerkClaims(user_id=str(claims["sub"]), org_id=org_id, raw=claims)

"""A stand-in for Clerk in API tests: signs session JWTs, serves JWKS and /users/{id},
and signs webhooks the way Svix does."""

import base64
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from svix.webhooks import Webhook

ISSUER = "https://clerk.kehora.test"
API_URL = "https://api.clerk.test/v1"
AZP = "http://localhost:5173"
WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"kehora-test-webhook-secret-32b!!").decode()


class FakeClerk:
    def __init__(self) -> None:
        self.kid = "kid-1"
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.users: dict[str, dict[str, Any]] = {}
        self.jwks_requests = 0
        self.user_requests = 0

    # --- identity fixtures -------------------------------------------------------------
    def add_user(self, email: str, role: str | None = None, **extra: Any) -> dict[str, Any]:
        clerk_id = f"user_{uuid.uuid4().hex[:24]}"
        data = {
            "id": clerk_id,
            "first_name": "Ada",
            "last_name": "Maker",
            "primary_email_address_id": "idn_1",
            "email_addresses": [{"id": "idn_1", "email_address": email}],
            "public_metadata": {"role": role} if role else {},
            **extra,
        }
        self.users[clerk_id] = data
        return data

    def rotate(self) -> None:
        self.kid = f"kid-{uuid.uuid4().hex[:6]}"
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # --- tokens ------------------------------------------------------------------------
    def token(self, sub: str, **overrides: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "sub": sub,
            "iss": ISSUER,
            "azp": AZP,
            "iat": now,
            "nbf": now,
            "exp": now + 60,
            "sid": "sess_1",
            "v": 2,
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, self._key, algorithm="RS256", headers={"kid": self.kid})

    def foreign_token(self, sub: str) -> str:
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = int(time.time())
        return jwt.encode(
            {"sub": sub, "iss": ISSUER, "iat": now, "exp": now + 60},
            other,
            algorithm="RS256",
            headers={"kid": self.kid},
        )

    def headers(self, sub: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token(sub)}"}

    # --- webhooks ----------------------------------------------------------------------
    def webhook(self, event_type: str, data: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
        body = json.dumps({"type": event_type, "data": data, "object": "event"})
        msg_id = f"msg_{uuid.uuid4().hex}"
        ts = datetime.now(UTC)
        sig = Webhook(WEBHOOK_SECRET).sign(msg_id, ts, body)
        return body.encode(), {
            "svix-id": msg_id,
            "svix-timestamp": str(int(ts.timestamp())),
            "svix-signature": sig,
            "content-type": "application/json",
        }

    # --- HTTP --------------------------------------------------------------------------
    def _jwks(self) -> dict[str, Any]:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self._key.public_key()))
        jwk.update({"kid": self.kid, "alg": "RS256", "use": "sig"})
        return {"keys": [jwk]}

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{ISSUER}/.well-known/jwks.json":
            self.jwks_requests += 1
            return httpx.Response(200, json=self._jwks())
        if url.startswith(f"{API_URL}/users/"):
            self.user_requests += 1
            user = self.users.get(url.rsplit("/", 1)[-1])
            return httpx.Response(200, json=user) if user else httpx.Response(404)
        return httpx.Response(404)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

"""Cached JWKS client for verifying iam-service's RS256 access tokens.

The JWKS document is fetched from iam-service once and held in memory; it is
re-fetched only when the cache TTL expires or a token presents an unknown `kid`
(key rotation). Verification keys are looked up by `kid` with no network call on
the hot path.
"""
import asyncio
import json
import time

import httpx
from jwt.algorithms import RSAAlgorithm

from app import config


class JwksError(Exception):
    """Raised when a usable signing key cannot be obtained."""


class JwksCache:
    def __init__(self) -> None:
        self._keys: dict[str, object] = {}
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()
        self.refresh_count = 0  # observability / test hook

    def _fresh(self) -> bool:
        return bool(self._keys) and (
            time.monotonic() - self._fetched_at
        ) < config.jwks_cache_ttl_seconds()

    async def _refresh(self) -> None:
        url = config.iam_jwks_url()
        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.get(url)
            resp.raise_for_status()
            document = resp.json()

        keys: dict[str, object] = {}
        for jwk in document.get("keys", []):
            kid = jwk.get("kid")
            if kid:
                keys[kid] = RSAAlgorithm.from_jwk(json.dumps(jwk))
        if not keys:
            raise JwksError("JWKS response contained no usable keys")

        self._keys = keys
        self._fetched_at = time.monotonic()
        self.refresh_count += 1

    async def get_key(self, kid: str | None):
        if kid and self._fresh() and kid in self._keys:
            return self._keys[kid]

        async with self._lock:
            if kid and self._fresh() and kid in self._keys:
                return self._keys[kid]
            try:
                await self._refresh()
            except (httpx.HTTPError, ValueError) as exc:
                raise JwksError(f"could not fetch JWKS from iam-service: {exc}") from exc

        if not kid or kid not in self._keys:
            raise JwksError(f"no signing key for kid={kid!r}")
        return self._keys[kid]

    def clear(self) -> None:
        self._keys = {}
        self._fetched_at = 0.0


jwks_cache = JwksCache()

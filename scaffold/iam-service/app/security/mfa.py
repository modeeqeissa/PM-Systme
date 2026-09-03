"""TOTP second factor (FR-IAM-01).

The secret is stored encrypted at rest (SRS 9.3.1). Dev uses a static Fernet
key derived from IAM_MFA_ENC_KEY or a fixed fallback; real deployments swap this
for envelope encryption backed by a KMS.
"""
import base64
import functools
import hashlib

import pyotp
from cryptography.fernet import Fernet, InvalidToken

from app import config


@functools.lru_cache(maxsize=1)
def _fernet() -> Fernet:
    if config.MFA_ENC_KEY:
        return Fernet(config.MFA_ENC_KEY)
    # Deterministic dev fallback so encrypted secrets survive a restart.
    digest = hashlib.sha256(b"pmp-iam-dev-mfa-key").digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - misconfiguration only
        raise ValueError("MFA secret cannot be decrypted (wrong IAM_MFA_ENC_KEY?)") from exc


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, badge_number: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=badge_number, issuer_name=config.MFA_ISSUER_LABEL
    )


def verify_code(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)

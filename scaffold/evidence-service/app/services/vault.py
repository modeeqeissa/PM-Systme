"""Encrypted evidence vault (FR-EVID-05) + SHA-256 hashing (FR-EVID-02).

Dev implementation: a local directory of Fernet-encrypted blobs. Production
swaps this for an object-store backed vault with KMS envelope encryption behind
the same three functions.
"""
import base64
import functools
import hashlib
import os
import uuid

from cryptography.fernet import Fernet

from app import config


def sha256_hex(data: bytes) -> str:
    """SHA-256 of the plaintext bytes, recorded at upload to detect tampering."""
    return hashlib.sha256(data).hexdigest()


@functools.lru_cache(maxsize=1)
def _fernet() -> Fernet:
    if config.VAULT_ENC_KEY:
        return Fernet(config.VAULT_ENC_KEY)
    digest = hashlib.sha256(b"pmp-evidence-dev-vault-key").digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _path(storage_ref: str) -> str:
    return os.path.join(config.vault_dir(), storage_ref)


def store(data: bytes) -> str:
    """Encrypt and persist ``data``; return its opaque storage_ref (vault key)."""
    os.makedirs(config.vault_dir(), exist_ok=True)
    storage_ref = f"ev_{uuid.uuid4().hex}"
    with open(_path(storage_ref), "wb") as fh:
        fh.write(_fernet().encrypt(data))
    return storage_ref


def load(storage_ref: str) -> bytes:
    """Return the decrypted plaintext bytes for ``storage_ref``."""
    with open(_path(storage_ref), "rb") as fh:
        return _fernet().decrypt(fh.read())


def exists(storage_ref: str) -> bool:
    return os.path.exists(_path(storage_ref))

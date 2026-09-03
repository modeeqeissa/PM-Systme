"""RSA signing key management for RS256 JWTs (FR-IAM-08).

Priority: IAM_JWT_PRIVATE_KEY (PEM) env var -> cached dev key file -> freshly
generated key written to that file. Real environments must set the env var so
the key is managed outside the repo.
"""
import functools

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from app import config


def _load_or_create() -> RSAPrivateKey:
    if config.JWT_PRIVATE_KEY_PEM:
        return serialization.load_pem_private_key(
            config.JWT_PRIVATE_KEY_PEM.encode(), password=None
        )
    try:
        with open(config.JWT_PRIVATE_KEY_PATH, "rb") as fh:
            return serialization.load_pem_private_key(fh.read(), password=None)
    except (FileNotFoundError, ValueError):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        try:
            with open(config.JWT_PRIVATE_KEY_PATH, "wb") as fh:
                fh.write(pem)
        except OSError:
            pass
        return key


@functools.lru_cache(maxsize=1)
def private_key() -> RSAPrivateKey:
    return _load_or_create()


@functools.lru_cache(maxsize=1)
def private_key_pem() -> str:
    return private_key().private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


@functools.lru_cache(maxsize=1)
def public_key_pem() -> str:
    return private_key().public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

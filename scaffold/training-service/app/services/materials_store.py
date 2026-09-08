"""Course-material blob store (docs §9.3.5 — materials.file_ref).

Same opaque-key shape as evidence-service's vault (`store` returns a `file_ref`
that later reads/deletes take), but materials are training documents rather
than chain-of-custody evidence, so this is plain storage — no encryption, no
hash chain. Production swaps the local directory for object storage behind
these three functions.
"""
import os
import uuid

from app import config


def _path(file_ref: str) -> str:
    return os.path.join(config.materials_dir(), file_ref)


def store(data: bytes) -> str:
    """Persist ``data``; return its opaque file_ref."""
    os.makedirs(config.materials_dir(), exist_ok=True)
    file_ref = f"mat_{uuid.uuid4().hex}"
    with open(_path(file_ref), "wb") as fh:
        fh.write(data)
    return file_ref


def exists(file_ref: str) -> bool:
    return os.path.exists(_path(file_ref))


def delete(file_ref: str) -> None:
    """Remove the blob if present (idempotent)."""
    try:
        os.remove(_path(file_ref))
    except FileNotFoundError:
        pass

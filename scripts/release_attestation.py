"""Ed25519 handoff for a verifier in a separate trusted CI job.

Only a separately trusted public-key fingerprint grants authority. A key bundled
by the actor/report itself is never an authority. Local callers must protect the
verifier process/key from candidate processes; same-user paths are not isolation.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sign(report: Path, private_key: Path, signature: Path, public_key: Path) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.from_private_bytes(private_key.read_bytes())
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    public_key.write_bytes(public)
    signature.write_bytes(key.sign(report.read_bytes()))
    return hashlib.sha256(public).hexdigest()


def verify(report: Path, signature: Path, public_key: Path, trusted_fingerprint: str) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    raw = public_key.read_bytes()
    if not trusted_fingerprint or hashlib.sha256(raw).hexdigest() != trusted_fingerprint:
        raise ValueError("Bağımsız verifier anahtar kimliği güvenilir kanalla eşleşmiyor.")
    try:
        Ed25519PublicKey.from_public_bytes(raw).verify(signature.read_bytes(), report.read_bytes())
    except Exception as error:
        # Cryptography InvalidSignature must not become a silently accepted result.
        raise ValueError("Bağımsız verifier imzası geçersiz.") from error

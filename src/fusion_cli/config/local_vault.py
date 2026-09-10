"""macOS masaüstünde izin penceresi açmadan kalıcı kasa anahtarı çözümü.

Yerel kullanıcı dosya izinleri koruma sınırıdır; aynı kullanıcıyla çalışan
programlara karşı Keychain erişim denetimi sağlamaz. Eski kasa korunur.
"""

from __future__ import annotations

import ctypes
import fcntl
import logging
import os
import secrets
import tempfile
from pathlib import Path

_logger = logging.getLogger(__name__)


def _migrate(root: Path, key: str) -> None:
    """Yarım kalmış geçişi yeniden dene; mevcut yeni kasaya dokunma."""
    from ..core.errors import ConfigError
    from .credentials import FernetSecretStore

    legacy = root / "secrets.enc"
    destination = root / "vault/secrets.enc"
    if not legacy.is_file() or destination.exists():
        return
    try:
        FernetSecretStore(legacy, secret_key=key).list_names()
    except (ConfigError, ValueError):
        _logger.warning("Eski kasa korunuyor ancak okunamıyor. API anahtarlarını yeniden ekle.")
        return
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(legacy.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).replace(destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _legacy_key() -> str | None:
    """Mevcut izni kullan; macOS izin diyaloğu göstermesine izin verme."""
    security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
    previous = ctypes.c_ubyte()
    if security.SecKeychainGetUserInteractionAllowed(ctypes.byref(previous)) != 0:
        return None
    if security.SecKeychainSetUserInteractionAllowed(False) != 0:
        return None
    try:
        import keyring

        return keyring.get_password("fusion-cli", "credential-master-key")
    except Exception:
        _logger.warning(
            "Eski kasa izinsiz okunamadı; dosyası korunuyor. API anahtarlarını yeniden ekle."
        )
        return None
    finally:
        security.SecKeychainSetUserInteractionAllowed(previous.value)


def local_master_key(root: Path) -> str:
    """Kilit altında anahtar oluştur; sürüm ve paket yolu değişince koru."""
    vault = root / "vault"
    vault.mkdir(mode=0o700, parents=True, exist_ok=True)
    vault.chmod(0o700)
    key_path = vault / "master.key"
    lock_fd = os.open(vault / "lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if key_path.exists():
            key_fd = os.open(key_path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(key_fd) as stream:
                current = stream.read().strip()
            if not current:
                raise ValueError("Yerel kasa anahtarı boş; mevcut kasa korunuyor.")
            key_path.chmod(0o600)
            _migrate(root, current)
            return current
        legacy = root / "secrets.enc"
        legacy_key = _legacy_key() if legacy.is_file() else None
        generated = legacy_key or secrets.token_urlsafe(48)
        # Anahtar önce yazılır; aradaki kesintide eski kasaya hiçbir zaman yazılmaz.
        key_fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(key_fd, "w") as stream:
            stream.write(generated)
            stream.flush()
            os.fsync(stream.fileno())
        _migrate(root, generated)
        return generated

"""macOS'ta kasa ana anahtarı: önce Keychain, olmazsa kullanıcıya özel yerel dosya.

Keychain erişimi HİÇBİR ZAMAN izin penceresi açmaz (`SecKeychainSetUserInteractionAllowed`
kapalı): öğe okunamaz/yazılamazsa eski dosya yöntemiyle çalışmaya devam edilir. Dosya
yöntemi aynı kullanıcıyla çalışan programlara karşı koruma sağlamaz; bu yüzden anahtar
Keychain'e taşınabildiğinde `vault/master.key` dosyası `master.key.migrated` yedeğine
çevrilir (silinmez: Keychain öğesi ileride kaybolursa kasa bu yedekle kurtarılır).
Yedeği Keychain'e geçişin işe yaradığını gördükten sonra kullanıcı silebilir.
"""

from __future__ import annotations

import contextlib
import ctypes
import fcntl
import hashlib
import logging
import os
import secrets
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

# Yalnız macOS'ta içe aktarılır (`keys._uses_local_vault`); `fcntl` ve `O_NOFOLLOW`
# POSIX'e özgüdür. Bu satır mypy'ın modülü Windows hedefinde denetlememesini sağlar.
assert sys.platform != "win32"

_logger = logging.getLogger(__name__)

_KEYCHAIN_SERVICE = "fusion-cli"
_LEGACY_ACCOUNT = "credential-master-key"
_ACCOUNT_PREFIX = "vault-master-key"
#: `FUSION_KEYCHAIN=off` Keychain'i hiç denemez (başsız CI, kısıtlı ortam, testler).
_KEYCHAIN_OFF = frozenset({"0", "off", "false", "no"})
_MIGRATED_SUFFIX = ".migrated"


class KeychainError(Exception):
    """Keychain okunamadı/yazılamadı (izin yok, kilitli, öğe erişimi reddedildi)."""


class Keychain(Protocol):
    """Tek bir kök dizin için ana anahtarın Keychain'deki yeri."""

    def get(self) -> str | None:
        """Öğe yoksa None; erişim sorunu varsa `KeychainError`."""
        ...

    def set(self, value: str) -> None:
        """Öğeyi yaz; olmazsa `KeychainError`."""
        ...


def keychain_account(root: Path) -> str:
    """Kök dizine özel Keychain hesap adı: iş yalıtımı açıkken her hesabın kendi kasası olur."""
    digest = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:12]
    return f"{_ACCOUNT_PREFIX}:{digest}"


@contextlib.contextmanager
def _no_keychain_ui() -> Iterator[None]:
    """Keychain çağrıları süresince izin diyaloğunu kapat; kapatılamazsa `KeychainError`."""
    try:
        security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
    except OSError as error:
        raise KeychainError(f"Security framework yüklenemedi: {error}") from error
    previous = ctypes.c_ubyte()
    if security.SecKeychainGetUserInteractionAllowed(ctypes.byref(previous)) != 0:
        raise KeychainError("Keychain etkileşim durumu okunamadı")
    if security.SecKeychainSetUserInteractionAllowed(False) != 0:
        raise KeychainError("Keychain etkileşimi kapatılamadı")
    try:
        yield
    finally:
        security.SecKeychainSetUserInteractionAllowed(previous.value)


class _SystemKeychain:
    """`keyring` üzerinden macOS Keychain; diyaloğa izin vermez."""

    def __init__(self, account: str) -> None:
        self._account = account

    def get(self) -> str | None:
        import keyring

        with _no_keychain_ui():
            try:
                return keyring.get_password(_KEYCHAIN_SERVICE, self._account)
            except Exception as error:  # keyring, KeyringError dışında da fırlatabilir
                raise KeychainError(str(error)) from error

    def set(self, value: str) -> None:
        import keyring

        with _no_keychain_ui():
            try:
                keyring.set_password(_KEYCHAIN_SERVICE, self._account, value)
            except Exception as error:
                raise KeychainError(str(error)) from error


def system_keychain(root: Path) -> Keychain | None:
    """Sistem Keychain'i; kapatılmışsa ya da `keyring` yoksa None (dosya yöntemi)."""
    if os.environ.get("FUSION_KEYCHAIN", "").strip().lower() in _KEYCHAIN_OFF:
        return None
    try:
        import keyring  # noqa: F401
    except ImportError:
        return None
    return _SystemKeychain(keychain_account(root))


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
    """Eski sürümün Keychain anahtarı (kök `secrets.enc` için); diyalog açmadan oku."""
    try:
        import keyring

        with _no_keychain_ui():
            return keyring.get_password(_KEYCHAIN_SERVICE, _LEGACY_ACCOUNT)
    except Exception:
        _logger.warning(
            "Eski kasa izinsiz okunamadı; dosyası korunuyor. API anahtarlarını yeniden ekle."
        )
        return None


def _read_key_file(path: Path) -> str | None:
    if not path.exists():
        return None
    key_fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(key_fd) as stream:
        current = stream.read().strip()
    if not current:
        raise ValueError("Yerel kasa anahtarı boş; mevcut kasa korunuyor.")
    path.chmod(0o600)
    return current


def _write_key_file(path: Path, value: str) -> None:
    key_fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(key_fd, "w") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def _decrypts_vault(root: Path, key: str) -> bool:
    """Anahtar mevcut kasayı çözüyor mu? Kasa yoksa (çözülecek bir şey yok) True."""
    from ..core.errors import ConfigError
    from .credentials import FernetSecretStore

    vault_file = root / "vault/secrets.enc"
    if not vault_file.is_file():
        return True
    try:
        FernetSecretStore(vault_file, secret_key=key).list_names()
    except ConfigError:
        return False
    return True


def _store_in_keychain(keychain: Keychain, value: str) -> bool:
    """Yaz ve geri okuyarak doğrula; doğrulanmadan dosya anahtarı asla bırakılmaz."""
    try:
        keychain.set(value)
        return keychain.get() == value
    except KeychainError as error:
        _logger.warning("Ana anahtar Keychain'e yazılamadı, dosya yöntemi sürüyor: %s", error)
        return False


def _archive_key_file(key_path: Path) -> None:
    """Keychain'e geçmiş anahtar dosyasını silmeden `.migrated` yedeğine çevir."""
    key_path.replace(key_path.with_name(key_path.name + _MIGRATED_SUFFIX))


def _resolve_with_keychain(root: Path, keychain: Keychain, key_path: Path) -> str | None:
    """Keychain varken anahtarı çöz ve göçü yap; çözülemezse None (çağıran dosya yoluna döner)."""
    backup_path = key_path.with_name(key_path.name + _MIGRATED_SUFFIX)
    file_key = _read_key_file(key_path)
    backup_key = None if file_key else _read_key_file(backup_path)
    try:
        stored = keychain.get()
        failed = False
    except KeychainError as error:
        _logger.warning("Keychain okunamadı, dosya yöntemi sürüyor: %s", error)
        stored, failed = None, True

    if stored:
        if file_key and file_key != stored:
            # Çelişki: kasayı çözen kazanır; hiçbirine dokunulmaz (veri kaybı yok).
            if not _decrypts_vault(root, stored) and _decrypts_vault(root, file_key):
                _logger.warning(
                    "Keychain ve dosya anahtarı çelişiyor; dosya anahtarı kullanılıyor."
                )
                return file_key
            _logger.warning("Keychain ve dosya anahtarı çelişiyor; Keychain anahtarı kullanılıyor.")
        elif file_key:
            _archive_key_file(key_path)
        return stored

    existing = file_key or backup_key
    if existing:
        if not failed and _store_in_keychain(keychain, existing):
            if file_key:
                _archive_key_file(key_path)
        elif backup_key and not key_path.exists():
            _write_key_file(key_path, backup_key)  # Keychain yok: yedekten dosyayı geri kur
        return existing

    if failed and (root / "vault/secrets.enc").is_file():
        raise ValueError("Keychain'e erişilemedi; kasanın anahtarı orada olabilir, kasa korunuyor.")
    return None


def local_master_key(root: Path, keychain: Keychain | None = None) -> str:
    """Kilit altında anahtar çöz/oluştur; sürüm ve paket yolu değişince koru.

    `keychain` verilmezse sistem Keychain'i denenir (`FUSION_KEYCHAIN=off` ile kapanır);
    Keychain yoksa ya da izin vermezse eski `vault/master.key` yöntemi kullanılır.
    """
    vault = root / "vault"
    vault.mkdir(mode=0o700, parents=True, exist_ok=True)
    vault.chmod(0o700)
    key_path = vault / "master.key"
    if keychain is None:
        keychain = system_keychain(root)
    lock_fd = os.open(vault / "lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if keychain is not None:
            resolved = _resolve_with_keychain(root, keychain, key_path)
            if resolved is not None:
                _migrate(root, resolved)
                return resolved
        else:
            current = _read_key_file(key_path)
            if current is not None:
                _migrate(root, current)
                return current
        legacy = root / "secrets.enc"
        legacy_key = _legacy_key() if legacy.is_file() else None
        generated = legacy_key or secrets.token_urlsafe(48)
        if keychain is None or not _store_in_keychain(keychain, generated):
            # Anahtar önce yazılır; aradaki kesintide eski kasaya hiçbir zaman yazılmaz.
            _write_key_file(key_path, generated)
        _migrate(root, generated)
        return generated

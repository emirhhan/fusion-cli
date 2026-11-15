"""Kullanıcının Chrome profilinden çerez okuma — yalnız AÇIK İSTEKLE (P-023).

`providers/web_browser.py` ilkesi değişmedi: normal tarayıcı profili hiçbir zaman
KENDİLİĞİNDEN okunmaz. Bu modül yalnız kullanıcı `fusion browser import-chrome` dediğinde
ya da Ayarlar › Web oturumları'ndan "Chrome'dan aktar"ı onayladığında çalışır.

Nasıl çalışır:
- Profiller `Local State` (`profile.info_cache`) üzerinden adlarıyla listelenir.
- Alan adları şifre ÇÖZMEDEN okunur (`host_key` düz metindir): onay ekranı Keychain'e
  dokunmadan "şu siteler aktarılacak" diyebilir.
- Değerler macOS'ta Keychain'deki "Chrome Safe Storage" parolasıyla (sistem izin
  diyaloğu çıkar — bu, kullanıcı onayının kendisidir), Linux'ta Chrome'un sabit
  "peanuts" parolasıyla çözülür: PBKDF2-SHA1 ("saltysalt") + AES-128-CBC, IV 16 boşluk.
  Chrome ≥ 130 düz metnin başına SHA-256(host_key) koyar; eşleşiyorsa atılır.
- Windows (DPAPI + AES-GCM) desteklenmez; anlaşılır hata verilir.
- `Cookies` dosyası Chrome açıkken kilitlidir: geçici kopya üzerinden okunur.

Çerez değerleri bu modülden yalnız `Cookie` nesnesi içinde çıkar; loglanmaz.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.cookie_files import SESSION_EXPIRES, Cookie, domain_allowed, normalize_domain
from ..core.errors import BrowserProfileError

#: Chrome'un anahtar türetme tuzu ve CBC başlangıç vektörü (Chromium os_crypt_mac.mm).
_SALT = b"saltysalt"
_IV = b" " * 16
_KEY_BYTES = 16
#: PBKDF2 tur sayısı: macOS 1003, Linux 1 (Chromium os_crypt_linux.cc).
KEY_ITERATIONS = 1003 if sys.platform == "darwin" else 1
#: Şifreli değerin sürüm öneki.
_VERSION_PREFIXES = (b"v10", b"v11")
#: Linux'ta `v11`: gnome-keyring/kwallet'ten alınan parola; sabit "peanuts" ÇÖZMEZ.
_LINUX_KEYRING_PREFIX = b"v11"
_LINUX_V11_HINT = (
    "Linux'ta Chrome çerezleri anahtarlık (gnome-keyring/kwallet, v11) ile şifreli; Fusion "
    "yalnız 'peanuts' (v10) çözer. Cookie-Editor ile JSON dışa aktarıp "
    "`fusion browser import-cookies` kullan."
)
_logger = logging.getLogger(__name__)
#: Chrome'un 1601 tabanlı mikrosaniye zaman damgasını Unix'e çevirme sabiti.
_CHROME_EPOCH_OFFSET_S = 11_644_473_600
_LOCAL_STATE = "Local State"
#: `samesite` sütunu: -1 belirsiz, 0 none, 1 lax, 2 strict.
_SAME_SITE = {0: "None", 1: "Lax", 2: "Strict"}
_SELECT = (
    "SELECT host_key, name, encrypted_value, value, path, expires_utc, is_secure, "
    "is_httponly, samesite FROM cookies"
)


@dataclass(frozen=True)
class ChromeProfile:
    """Bir Chrome profili: dizin, görünen ad ve `Cookies` dosyası."""

    directory: Path
    label: str
    cookies_path: Path


def chrome_user_data_dir(platform: str = sys.platform) -> Path:
    """İşletim sistemine göre Chrome kullanıcı veri kökü (`platform` testte enjekte edilir)."""
    home = Path.home()
    if platform == "darwin":
        return home / "Library" / "Application Support" / "Google" / "Chrome"
    if platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        return Path(base) / "Google" / "Chrome" / "User Data"
    return home / ".config" / "google-chrome"


def list_chrome_profiles(user_data: Path | None = None) -> tuple[ChromeProfile, ...]:
    """Çerez dosyası olan profilleri `Local State` adlarıyla listele; dizin yoksa boş."""
    root = user_data or chrome_user_data_dir()
    if not root.is_dir():
        return ()
    labels = _profile_labels(root)
    profiles: list[ChromeProfile] = []
    for folder in sorted(root.iterdir()):
        cookies = _cookies_file(folder)
        if cookies is None:
            continue
        profiles.append(
            ChromeProfile(
                directory=folder,
                label=labels.get(folder.name, folder.name),
                cookies_path=cookies,
            )
        )
    return tuple(profiles)


def chrome_cookie_domains(profile: ChromeProfile) -> tuple[str, ...]:
    """Profildeki alan adları — şifre çözmeden, onay ekranı için."""
    with _snapshot(profile.cookies_path) as copy:
        rows = _query(copy, "SELECT DISTINCT host_key FROM cookies")
    return tuple(sorted({normalize_domain(str(row[0])) for row in rows if row[0]}))


def read_chrome_cookies(
    profile: ChromeProfile, *, domains: tuple[str, ...] | None = None
) -> tuple[Cookie, ...]:
    """Profilin çerezlerini çöz; `domains` verilirse yalnız o alan adları."""
    key = derive_key(safe_storage_password(), iterations=KEY_ITERATIONS)
    with _snapshot(profile.cookies_path) as copy:
        rows = _query(copy, _SELECT)
    cookies: list[Cookie] = []
    skipped = 0
    keyring_skipped = 0
    first_error: BrowserProfileError | None = None
    for host, name, encrypted, plain, path, expires_utc, secure, http_only, same_site in rows:
        host_key = str(host or "")
        if not host_key or not name:
            continue
        if domains is not None and not domain_allowed(host_key, domains):
            continue
        value = str(plain or "")
        if encrypted:
            # Tek bozuk çerez bütün içe aktarmayı düşürmez: atlanır ve sayılır. Ölçüldü
            # (31 Ekim): Linux'ta anahtarlık etkinken v11 kayıt 'Keychain uyuşmuyor'
            # hatasıyla hiçbir çerezin yazılmamasına yol açıyordu.
            try:
                value = decrypt_value(bytes(encrypted), key, host_key)
            except BrowserProfileError as error:
                skipped += 1
                if bytes(encrypted).startswith(_LINUX_KEYRING_PREFIX) and sys.platform not in (
                    "darwin",
                    "win32",
                ):
                    keyring_skipped += 1
                first_error = first_error or error
                continue
        cookies.append(
            Cookie(
                name=str(name),
                value=value,
                domain=host_key,
                path=str(path or "/"),
                expires=_unix_expires(expires_utc),
                secure=bool(secure),
                http_only=bool(http_only),
                # `0` (none) de geçerli bir değerdir; `or` ile -1'e düşürülmez.
                same_site=_SAME_SITE.get(int(same_site) if same_site is not None else -1, "Lax"),
            )
        )
    if skipped and not cookies and first_error is not None:
        if keyring_skipped:
            raise BrowserProfileError(_LINUX_V11_HINT) from first_error
        raise first_error
    if skipped:
        _logger.warning(
            "Chrome içe aktarma: %d çerez çözülemedi ve atlandı (%d anahtarlık/v11).",
            skipped,
            keyring_skipped,
        )
    return tuple(cookies)


def safe_storage_password(platform: str = sys.platform) -> str:
    """Chrome'un yerel şifreleme parolası.

    macOS'ta Keychain sorgusu sistem izin diyaloğu açar: kullanıcı "İzin ver" demeden
    hiçbir değer çözülemez. Testler bu fonksiyonu sahteler.
    """
    if platform == "darwin":
        try:
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-w",
                    "-s",
                    "Chrome Safe Storage",
                    "-a",
                    "Chrome",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BrowserProfileError(f"Keychain sorgusu başarısız: {error}") from error
        if result.returncode != 0 or not result.stdout.strip():
            raise BrowserProfileError(
                "Chrome'un Keychain parolası alınamadı. İzin diyaloğunda 'İzin ver' seçilmeli; "
                "Chrome hiç açılmadıysa kayıt yoktur."
            )
        return str(result.stdout).strip()
    if platform == "win32":
        raise BrowserProfileError(
            "Windows'ta Chrome çerezleri (DPAPI) henüz çözülemiyor; Cookie-Editor ile JSON dışa "
            "aktarıp `fusion browser import-cookies` kullan."
        )
    return "peanuts"


def derive_key(password: str, *, iterations: int) -> bytes:
    """PBKDF2-HMAC-SHA1 ile 16 baytlık AES anahtarı (Chromium ile birebir)."""
    return hashlib.pbkdf2_hmac("sha1", password.encode(), _SALT, iterations, dklen=_KEY_BYTES)


def decrypt_value(encrypted: bytes, key: bytes, host_key: str) -> str:
    """`v10`/`v11` önekli değeri çöz; Chrome ≥ 130 SHA-256(host_key) önekini at."""
    if not encrypted.startswith(_VERSION_PREFIXES):
        # Şifresiz eski kayıt (ya da bilinmeyen biçim): olduğu gibi metne çevrilir.
        return encrypted.decode("utf-8", errors="replace")
    # cryptography tembel yüklenir: yalnız Chrome içe aktarımında gerekir ve stub'ı yok.
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    decryptor: Any = Cipher(algorithms.AES(key), modes.CBC(_IV)).decryptor()
    unpadder: Any = padding.PKCS7(algorithms.AES.block_size).unpadder()
    try:
        padded = bytes(decryptor.update(encrypted[3:]) + decryptor.finalize())
        plain = bytes(unpadder.update(padded) + unpadder.finalize())
    except ValueError as error:
        parola = "Keychain parolası" if sys.platform == "darwin" else "yerel parola"
        raise BrowserProfileError(
            f"Chrome çerezi çözülemedi: {parola} uyuşmuyor ya da biçim yeni."
        ) from error
    digest = hashlib.sha256(host_key.encode()).digest()
    if plain.startswith(digest):
        plain = plain[len(digest) :]
    try:
        return plain.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BrowserProfileError("Chrome çerezi çözülemedi: değer metin değil.") from error


def encrypt_for_test(plain: bytes, key: bytes) -> bytes:
    """Chrome'un yazdığı biçimde şifrele (`v10` + AES-CBC). Yalnız testlerin sahte DB'si için."""
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    padder: Any = padding.PKCS7(algorithms.AES.block_size).padder()
    encryptor: Any = Cipher(algorithms.AES(key), modes.CBC(_IV)).encryptor()
    padded = bytes(padder.update(plain) + padder.finalize())
    return b"v10" + bytes(encryptor.update(padded) + encryptor.finalize())


# --------------------------------------------------------------------------- #


def _profile_labels(root: Path) -> dict[str, str]:
    state = root / _LOCAL_STATE
    if not state.is_file():
        return {}
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    cache = data.get("profile", {}).get("info_cache", {}) if isinstance(data, dict) else {}
    return {
        str(folder): str(info.get("name") or folder)
        for folder, info in cache.items()
        if isinstance(info, dict)
    }


def _cookies_file(folder: Path) -> Path | None:
    if not folder.is_dir():
        return None
    for candidate in (folder / "Network" / "Cookies", folder / "Cookies"):
        if candidate.is_file():
            return candidate
    return None


@contextlib.contextmanager
def _snapshot(path: Path) -> Iterator[Path]:
    """Kilitli olabilecek DB'nin geçici kopyası; çıkışta silinir."""
    handle, name = tempfile.mkstemp(prefix="fusion-cookies-", suffix=".sqlite")
    os.close(handle)
    copy = Path(name)
    try:
        shutil.copy2(path, copy)
    except OSError as error:
        copy.unlink(missing_ok=True)
        raise BrowserProfileError(f"Chrome çerez dosyası kopyalanamadı: {error}") from error
    try:
        yield copy
    finally:
        copy.unlink(missing_ok=True)


def _query(path: Path, sql: str) -> list[tuple[Any, ...]]:
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return list(connection.execute(sql))
        finally:
            connection.close()
    except sqlite3.Error as error:
        raise BrowserProfileError(f"Chrome çerez veritabanı okunamadı: {error}") from error


def _unix_expires(expires_utc: object) -> float:
    if not isinstance(expires_utc, (int, float)) or isinstance(expires_utc, bool):
        return SESSION_EXPIRES
    if expires_utc <= 0:
        return SESSION_EXPIRES
    return float(expires_utc) / 1_000_000 - _CHROME_EPOCH_OFFSET_S

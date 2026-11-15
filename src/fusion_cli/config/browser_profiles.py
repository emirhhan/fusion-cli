"""Tarayıcı profilleri deposu — ajanın tarayıcısına taşınan kullanıcı oturumları (P-023).

Her profil `browser_profiles/<ad>/` altında iki dosyadır:

- `profile.json` — AÇIK meta veri: alan adları, çerez sayısı, kaynak, zamanlar ve
  kullanıcının onayladığı alan adı listesi. Çerez DEĞERİ burada yoktur; arayüz ve CLI
  listeleri yalnız bunu okur.
- `cookies.enc` — Playwright `storage_state` sözlüğü (çerezler + `origins` localStorage),
  sır deposuyla AYNI şifreleme
  (`FernetSecretStore`: scrypt + Fernet, atomik yazma, `.bak`). Ana anahtar yoksa
  profil kaydedilemez; sessizce açık yazmak yoktur.

Alan adı bazlı onay: `allowed_domains` doluysa `storage_state` yalnız o alan adlarının
(ve alt alan adlarının) çerezlerini döndürür. Kullanıcı içe aktarırken "bu profil
yalnız şu sitelerde geçerli" der; ajan başka siteye giderse çerezsiz gider.

Ölçüldü (31 Ekim): `web_profiles/` Chrome kullanıcı-veri dizini biçimindeydi ve yalnız
dört web MODEL sağlayıcısı içindi; ajanın `browser_*` araçlarına verilebilecek bir
`storage_state` kaynağı yoktu.
"""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from time import time

from ..core.atomic_file import atomic_replace_text
from ..core.browser_session import BrowserSession
from ..core.cookie_files import (
    Cookie,
    Origin,
    cookie_domains,
    cookies_from_storage_state,
    filter_by_domains,
    filter_origins_by_domains,
    origins_from_storage_state,
    to_storage_state,
    validate_profile_name,
)
from ..core.errors import BrowserProfileError, ConfigError
from .credentials import FernetSecretStore
from .keys import secret_key
from .models import Config
from .paths import browser_profiles_dir

_META_FILE = "profile.json"
_COOKIE_FILE = "cookies.enc"
#: Şifreli dosyadaki tek anahtar: depo "ortam değişkeni → değer" sözlüğü tutar.
_STATE_KEY = "storage_state"
#: Profilin nereden geldiği; arayüz etiketleri bu değerlere bağlıdır.
SOURCE_FILE = "dosya"
SOURCE_CHROME = "chrome"
SOURCE_LOGIN = "giris"
#: Web MODEL oturumundan (ChatGPT/Claude/Gemini/Copilot) tek yönlü, onaylı kopya.
SOURCE_WEB_SESSION = "web_oturumu"

_logger = logging.getLogger(__name__)


def default_browser_profile_store() -> BrowserProfileStore:
    """Kullanıcı veri dizinindeki depo, sır deposuyla AYNI ana anahtarla."""
    return BrowserProfileStore(browser_profiles_dir(), secret_key=secret_key())


def browser_session_from(config: Config) -> BrowserSession:
    """Turun tarayıcı taşıyıcısını `browser:` ayarlarıyla kur (varsayılan profil, pencere kipi)."""
    return BrowserSession(
        profile_name=config.browser.default_profile,
        headless=config.browser.headless,
        profiles_enabled=config.browser.profiles_enabled,
    )


@dataclass(frozen=True)
class BrowserProfileSummary:
    """Arayüze ve CLI'ya giden profil özeti: değer yok, yalnız ad/alan adı/sayı."""

    name: str
    domains: tuple[str, ...]
    cookie_count: int
    source: str
    imported_at: float
    last_used_at: float | None
    #: Onaylı alan adları; boşsa süzme yok (tüm çerezler).
    allowed_domains: tuple[str, ...]


class BrowserProfileStore:
    """`browser_profiles/<ad>/` dizinlerini yöneten depo."""

    def __init__(
        self,
        root: Path,
        *,
        secret_key: str | None,
        clock: Callable[[], float] = time,
    ) -> None:
        self._root = root
        self._secret_key = secret_key
        self._clock = clock

    @property
    def available(self) -> bool:
        """Ana anahtar var mı? Yoksa profil yazılamaz/çözülemez."""
        return self._secret_key is not None

    @property
    def root(self) -> Path:
        return self._root

    def list(self) -> tuple[BrowserProfileSummary, ...]:
        """Kayıtlı profiller, ada göre sıralı; bozuk meta veri atlanır (loglanır)."""
        if not self._root.is_dir():
            return ()
        summaries: list[BrowserProfileSummary] = []
        for folder in sorted(self._root.iterdir()):
            if not (folder / _META_FILE).is_file():
                continue
            try:
                summaries.append(self._read_meta(folder.name))
            except BrowserProfileError as error:
                _logger.warning("Tarayıcı profili okunamadı: %s (%s)", folder.name, error)
        return tuple(summaries)

    def exists(self, name: str) -> bool:
        return (self._root / validate_profile_name(name) / _META_FILE).is_file()

    def summary(self, name: str) -> BrowserProfileSummary:
        """Profil özeti; yoksa anlaşılır hata."""
        clean = validate_profile_name(name)
        if not self.exists(clean):
            raise BrowserProfileError(
                f"'{clean}' adlı tarayıcı profili yok. Mevcutlar: fusion browser profiles"
            )
        return self._read_meta(clean)

    def save(
        self,
        name: str,
        cookies: tuple[Cookie, ...],
        *,
        source: str,
        allowed_domains: tuple[str, ...] | None = None,
        origins: tuple[Origin, ...] = (),
    ) -> BrowserProfileSummary:
        """Profili (yeniden) yaz: çerezler (+ localStorage origins) şifreli, meta veri açık."""
        clean = validate_profile_name(name)
        self._require_key()
        folder = self._root / clean
        folder.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            folder.chmod(0o700)
        summary = BrowserProfileSummary(
            name=clean,
            domains=cookie_domains(cookies),
            cookie_count=len(cookies),
            source=source,
            imported_at=self._clock(),
            last_used_at=None,
            allowed_domains=tuple(allowed_domains or ()),
        )
        self._write_cookies(folder, cookies, origins)
        self._write_meta(folder, summary)
        return summary

    def update_cookies(
        self, name: str, cookies: tuple[Cookie, ...], origins: tuple[Origin, ...] = ()
    ) -> BrowserProfileSummary:
        """Tarayıcıdan dönen tazelenmiş oturumu yaz; onay listesi ve kaynak korunur.

        Onay listesi doluysa dışındaki çerezler/origins YAZILMAZ. Ölçüldü (31 Ekim):
        bağlamın tüm çerezleri yazılıyor, onay dışı sitelerin izleme çerezleri şifreli
        dosyada ve özetin alan adı listesinde birikiyordu.
        """
        previous = self.summary(name)
        self._require_key()
        folder = self._root / previous.name
        allowed = previous.allowed_domains or None
        kept = filter_by_domains(cookies, allowed)
        summary = BrowserProfileSummary(
            name=previous.name,
            domains=cookie_domains(kept),
            cookie_count=len(kept),
            source=previous.source,
            imported_at=previous.imported_at,
            last_used_at=previous.last_used_at,
            allowed_domains=previous.allowed_domains,
        )
        self._write_cookies(folder, kept, filter_origins_by_domains(origins, allowed))
        self._write_meta(folder, summary)
        return summary

    def storage_state(self, name: str) -> dict[str, object]:
        """Onaylı alan adlarına süzülmüş Playwright `storage_state`; son kullanımı işaretler."""
        summary = self.summary(name)
        self._require_key()
        folder = self._root / summary.name
        try:
            raw = self._cookie_store(folder).get(_STATE_KEY)
        except ConfigError as error:
            # Ana anahtar değişmiş (yeni Mac, Keychain kaybı) ya da dosya bozuk: hata profil
            # bağlamıyla dönsün ki araç ve CLI tek tipte yakalayıp anlaşılır göstersin.
            raise BrowserProfileError(
                f"'{summary.name}' profilinin çerez dosyası çözülemedi: {error}"
            ) from error
        if raw is None:
            raise BrowserProfileError(f"'{summary.name}' profilinin çerez dosyası eksik.")
        try:
            state = json.loads(raw)
        except ValueError as error:
            raise BrowserProfileError(
                f"'{summary.name}' profilinin çerez dosyası bozuk."
            ) from error
        allowed = summary.allowed_domains or None
        self._stamp_last_used(folder, summary)
        return to_storage_state(
            filter_by_domains(cookies_from_storage_state(state), allowed),
            filter_origins_by_domains(origins_from_storage_state(state), allowed),
        )

    def _stamp_last_used(self, folder: Path, summary: BrowserProfileSummary) -> None:
        """`last_used_at` yalnız bilgidir: yazılamazsa oturum yine verilir (loglanır)."""
        try:
            self._write_meta(
                folder,
                BrowserProfileSummary(**{**asdict(summary), "last_used_at": self._clock()}),
            )
        except BrowserProfileError as error:
            _logger.warning("Profil son kullanım damgası yazılamadı: %s", error)

    def delete(self, name: str) -> bool:
        """Profil dizinini kaldır. Vardıysa True."""
        clean = validate_profile_name(name)
        folder = self._root / clean
        if not folder.is_dir():
            return False
        shutil.rmtree(folder)
        return True

    # ------------------------------------------------------------------ #

    def _require_key(self) -> None:
        if not self.available:
            raise BrowserProfileError(
                "Tarayıcı profili için şifreleme anahtarı yok: FUSION_SECRET_KEY tanımla ya da "
                "sistem anahtarlığını etkinleştir (fusion doctor)."
            )

    def _cookie_store(self, folder: Path) -> FernetSecretStore:
        return FernetSecretStore(folder / _COOKIE_FILE, secret_key=self._secret_key)

    def _write_cookies(
        self, folder: Path, cookies: tuple[Cookie, ...], origins: tuple[Origin, ...] = ()
    ) -> None:
        try:
            self._cookie_store(folder).set(
                _STATE_KEY, json.dumps(to_storage_state(cookies, origins))
            )
        except ConfigError as error:
            raise BrowserProfileError(f"Çerezler şifrelenip yazılamadı: {error}") from error

    def _write_meta(self, folder: Path, summary: BrowserProfileSummary) -> None:
        # Atomik: yarım yazılmış `profile.json` `list()`te profili sessizce yok ediyordu
        # (masaüstü aynı anda okurken ya da süreç yazma ortasında ölürken; ölçüldü 31 Ekim).
        payload = json.dumps(asdict(summary), ensure_ascii=False, indent=2)
        try:
            atomic_replace_text(folder / _META_FILE, payload)
        except OSError as error:
            raise BrowserProfileError(f"Profil meta verisi yazılamadı: {error}") from error

    def _read_meta(self, name: str) -> BrowserProfileSummary:
        path = self._root / name / _META_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise BrowserProfileError(
                f"'{name}' profilinin meta verisi okunamadı: {error}"
            ) from error
        if not isinstance(data, dict):
            raise BrowserProfileError(f"'{name}' profilinin meta verisi bozuk.")
        try:
            return BrowserProfileSummary(
                name=name,
                domains=tuple(str(item) for item in data.get("domains") or ()),
                cookie_count=int(data.get("cookie_count") or 0),
                source=str(data.get("source") or SOURCE_FILE),
                imported_at=float(data.get("imported_at") or 0.0),
                last_used_at=(
                    float(data["last_used_at"]) if data.get("last_used_at") is not None else None
                ),
                allowed_domains=tuple(str(item) for item in data.get("allowed_domains") or ()),
            )
        except (TypeError, ValueError) as error:
            raise BrowserProfileError(f"'{name}' profilinin meta verisi bozuk: {error}") from error

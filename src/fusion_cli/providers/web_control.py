"""Web tarayıcı sağlayıcılarının panel tarafındaki ortak işlemleri.

Bu sağlayıcılar (ChatGPT, Claude, Gemini, Copilot) kullanıcının KENDİ
aboneliğiyle çalışır ve API anahtarı kullanmaz: giriş ayrı bir tarayıcı
penceresinde yapılır, çerez izole bir Playwright profilinde kalır ve Fusion
çerez değerine hiç dokunmaz.

Modül ASGI'den ve Tauri'den bağımsızdır: hem yerel gateway paneli hem masaüstü
uygulaması aynı davranışı buradan alır. İki yerde ayrı ayrı yazılsaydı biri
düzeltilirken öteki eskirdi.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from ..config.keys import environ_snapshot
from ..config.models import Config, WebSessionConfig
from .web_browser import WEB_BROWSER_PROVIDERS, browser_profile_dir, normalize_account

if TYPE_CHECKING:  # pragma: no cover - yalnız tip denetimi
    from ..core.protocols import LlmProvider


class SecretReader(Protocol):
    """Katalog için gereken EN DAR yüzey.

    `get` bilerek istenmez: katalog yalnız "bu anahtar kayıtlı mı" bilgisini
    kullanır, değerini asla okumaz. Dar protokol, sırra erişebilen bir deponun
    buraya geçmesini gereksiz kılar.
    """

    @property
    def available(self) -> bool: ...
    def list_names(self) -> tuple[str, ...]: ...


def login_argv(provider: str, account: str) -> list[str]:
    """Giriş tarayıcısını açacak komutu üret.

    Kaynak kurulumda `python -m fusion_cli.providers.web_login` çalışır. Ama
    PyInstaller ile paketlenmiş uygulamada `sys.executable` Fusion ikilisidir ve
    `-m` bayrağını TANIMAZ; orada ikilinin kendi `web-login` komutu kullanılır.
    Ayrım yapılmazsa panelden "Giriş yap" sessizce hiçbir şey açmaz.
    """
    if provider not in WEB_BROWSER_PROVIDERS:
        raise ValueError(f"tanınmayan web sağlayıcısı: {provider}")
    normalized = normalize_account(account or "main")
    if getattr(sys, "frozen", False):
        return [sys.executable, "web-login", provider, normalized]
    return [sys.executable, "-m", "fusion_cli.providers.web_login", provider, normalized]


def start_login(provider: str, account: str) -> int:
    """Giriş penceresini başlat ve süreç kimliğini döndür.

    Süreç BEKLENMEZ: kullanıcı pencereyi kapatana kadar yaşar. Panel `pid`'i
    yoklayarak pencerenin kapandığını anlar ve doğrulamayı kendiliğinden çalıştırır;
    kullanıcı elle çerez kopyalamak zorunda kalmaz.
    """
    argv = login_argv(provider, account)
    process = subprocess.Popen(
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return process.pid


def process_alive(pid: int) -> bool:
    """Giriş penceresinin süreci hâlâ yaşıyor mu?"""
    if pid <= 0:
        return False
    import os

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _profile_dir(provider: str, account: str) -> Path:
    return browser_profile_dir(provider, normalize_account(account or "main"))


def _session_for(
    sessions: tuple[WebSessionConfig, ...], provider: str, account: str
) -> WebSessionConfig | None:
    """Sağlayıcı/hesap için kayıtlı oturum. Yoksa None."""
    hedef = normalize_account(account or "main")
    for item in sessions:
        if getattr(item, "provider", None) == provider and (
            normalize_account(str(getattr(item, "account", "main"))) == hedef
        ):
            return item
    return None


def session_model(provider: str, account: str) -> str:
    """Web oturumunun kararlı model kimliği."""
    return f"{provider}/{normalize_account(account or 'main')}/auto"


def register_session(
    config: Config,
    provider: str,
    account: str = "main",
    *,
    tool_support: str = "emulated",
) -> tuple[Config | None, dict[str, Any]]:
    """Giriş sonrası oturumu yapılandırmaya YAZ ve etkinleştir.

    Bu adım eksikti: giriş penceresi kapanıyor, profil klasörü oluşuyor ve panel
    "bağlı" diyordu — ama `web_sessions` boş kaldığı için Fusion o sağlayıcıyı
    model yönlendirmesinde hiç kullanamıyordu.

    Geçilmiş araç ölçümü KORUNUR: ölçüm modelin yeteneğine dairdir, yeniden
    bağlanmak onu geçersiz kılmaz. Aksi hâlde her yeniden giriş, taklit-araç
    modelini sessizce salt-okunur kipe düşürürdü.
    """
    from dataclasses import replace as _replace

    from ..config.models import WebSessionConfig
    from ..config.writer import write_web_sessions
    from .web_browser import web_secret_name

    if provider not in WEB_BROWSER_PROVIDERS:
        return None, {"ok": False, "metin": f"Tanınmayan web sağlayıcısı: {provider}"}
    hesap = normalize_account(account or "main")
    model = session_model(provider, hesap)

    mevcut = _session_for(tuple(config.web_sessions), provider, hesap)
    korunan_olcum = bool(getattr(mevcut, "tool_eval_passed", False)) and (
        getattr(mevcut, "tool_support", None) == tool_support
    )
    oturum = WebSessionConfig(
        model=model,
        provider=provider,
        account=hesap,
        transport="browser",
        credential_ref=web_secret_name(provider, hesap),
        tool_support="emulated" if tool_support != "none" else "none",
        tool_eval_passed=korunan_olcum,
        enabled=True,
    )
    digerleri = tuple(
        item
        for item in config.web_sessions
        if not (item.provider == provider and normalize_account(str(item.account)) == hesap)
        and item.model != model
    )
    yeni = _replace(config, web_sessions=(*digerleri, oturum))
    try:
        write_web_sessions(yeni)
    except Exception as error:  # ConfigError ve OSError türevleri
        return None, {"ok": False, "metin": f"Oturum kaydedilemedi: {error}"}
    return yeni, {"ok": True, "model": model, "metin": "Oturum kaydedildi."}


def remove_session(
    config: Config, provider: str, account: str = "main"
) -> tuple[Config | None, dict[str, Any]]:
    """Oturumu kaldır ve tarayıcı profilini sil.

    Çıkış yapmanın karşılığı budur: profil silinmezse çerez diskte kalır ve
    kullanıcı "çıktım" sanır. Profil silinemezse kayıt YİNE DE kaldırılır ve
    sebep söylenir; yarım bir durumu sessizce başarı göstermek yanlış olurdu.
    """
    from dataclasses import replace as _replace
    from shutil import rmtree

    from ..config.writer import write_web_sessions

    hesap = normalize_account(account or "main")
    kalan = tuple(
        item
        for item in config.web_sessions
        if not (item.provider == provider and normalize_account(str(item.account)) == hesap)
    )
    if len(kalan) == len(config.web_sessions):
        return None, {"ok": False, "metin": "Bu sağlayıcı için kayıtlı oturum yok."}

    yeni = _replace(config, web_sessions=kalan)
    try:
        write_web_sessions(yeni)
    except Exception as error:
        return None, {"ok": False, "metin": f"Oturum kaldırılamadı: {error}"}

    uyari = ""
    profil = _profile_dir(provider, hesap)
    if profil.exists():
        try:
            rmtree(profil)
        except OSError as error:
            uyari = f" Profil klasörü silinemedi: {error}"
    return yeni, {"ok": True, "metin": f"Oturum kapatıldı.{uyari}"}


def _build_web_provider(config: Config, model: str) -> LlmProvider | None:
    """Doğrulama için web sağlayıcısını kur. Kurulamıyorsa None."""
    from .web_registry import web_registry_for

    registry = web_registry_for(config)
    return registry.build(model) if registry else None


async def validate_session(config: Config, provider: str, account: str = "main") -> dict[str, Any]:
    """Gerçek ve KÜÇÜK bir istek gönderip oturumun çalıştığını doğrula.

    Profil klasörünün varlığı giriş yapıldığını KANITLAMAZ: pencere açılıp
    kapatılınca da klasör oluşur. Tek kanıt, o oturumdan gerçekten cevap
    alabilmektir. İstek kasten küçüktür; kullanıcının kendi kotasından
    harcadığı için uzun bir sınama yapılmaz.
    """
    import asyncio

    from ..core.types import CompletionRequest, Message

    hesap = normalize_account(account or "main")
    oturum = _session_for(tuple(config.web_sessions), provider, hesap)
    if oturum is None:
        return {"ok": False, "metin": "Bu sağlayıcı için kayıtlı oturum yok."}

    saglayici = _build_web_provider(config, oturum.model)
    if saglayici is None:
        return {"ok": False, "metin": "Web sağlayıcısı kurulamadı."}

    istek = CompletionRequest(
        messages=(Message("user", "Sadece OK yaz."),),
        temperature=0.0,
        max_tokens=16,
        timeout_s=min(90.0, float(getattr(oturum, "timeout_s", 180.0))),
    )
    try:
        sonuc = await asyncio.wait_for(saglayici.complete(istek), timeout=istek.timeout_s + 5)
    except TimeoutError:
        return {"ok": False, "metin": "Bağlantı sınaması zaman aşımına uğradı."}
    except Exception as error:
        return {"ok": False, "metin": f"Bağlantı sınanamadı: {error}"}

    if not sonuc.ok:
        return {"ok": False, "metin": f"Oturum cevap vermedi: {sonuc.error or 'bilinmeyen hata'}"}
    return {
        "ok": True,
        "gecikme_ms": sonuc.latency_ms,
        "onizleme": sonuc.text[:160],
        "metin": "Oturum çalışıyor.",
    }


def provider_catalog(
    *,
    sessions: tuple[Any, ...],
    secret_store: SecretReader | None,
) -> list[dict[str, Any]]:
    """Panelde çizilecek TEK ve KISA sağlayıcı listesi.

    İki ayrı bölüm (anahtarlı sağlayıcılar + web sağlayıcıları) yerine tek liste
    verilir: kullanıcı uzun anahtar kutuları değil, "ismi yazsın, tıklayınca
    açılsın" istedi. Satır yalnız kimlik, ad, tür ve bağlı olup olmadığını
    taşır; anahtar ya da çerez değeri bu sınırdan HİÇBİR koşulda geçmez.
    """
    from .registry import BUILTIN_PROVIDERS

    rows: list[dict[str, Any]] = [
        {**card, "tur": "web", "eylem": "oturum"}
        for card in provider_cards(sessions=sessions, secret_store=secret_store)
    ]

    stored: set[str] = set()
    if secret_store is not None and secret_store.available:
        try:
            stored = set(secret_store.list_names())
        except Exception:
            stored = set()
    environment = environ_snapshot()

    for provider in BUILTIN_PROVIDERS:
        if not provider.implemented or provider.auth_env is None:
            continue
        rows.append(
            {
                "id": provider.id,
                "ad": provider.name,
                "tur": "anahtar",
                "eylem": "anahtar",
                "ortam": provider.auth_env,
                "bagli": provider.auth_env in stored
                or bool(environment.get(provider.auth_env, "").strip()),
            }
        )
    return rows


def provider_cards(
    *,
    sessions: tuple[Any, ...],
    secret_store: SecretReader | None,
) -> list[dict[str, Any]]:
    """Panelde çizilecek sağlayıcı kartları — yalnız METADATA.

    Çerez, token ya da başka bir sır değeri bu sınırdan HİÇBİR koşulda geçmez;
    "bağlı mı" bilgisi profil dizininin varlığından türetilir.
    """
    cards: list[dict[str, Any]] = []
    for provider_id, definition in WEB_BROWSER_PROVIDERS.items():
        matching = [item for item in sessions if getattr(item, "provider", None) == provider_id]
        account = normalize_account(
            str(getattr(matching[0], "account", "main")) if matching else "main"
        )
        session = matching[0] if matching else None
        profil_var = _profile_dir(provider_id, account).exists()
        cards.append(
            {
                "id": provider_id,
                "ad": definition.name,
                "adres": definition.home_url,
                "hesap": account,
                # Bu sağlayıcılar anahtar kullanmaz; panel anahtar kutusu ÇİZMEZ.
                "anahtar_gerekir": False,
                # "Bağlı" olmak için hem tarayıcı profili hem KAYITLI ve etkin bir
                # oturum gerekir. Eskiden yalnız klasöre bakılıyordu: giriş
                # yapmadan pencereyi kapatmak bile "bağlı" gösteriyordu ve
                # Fusion o sağlayıcıyı yine de kullanamıyordu.
                "bagli": profil_var and bool(getattr(session, "enabled", False)),
                "profil_var": profil_var,
                "model": getattr(session, "model", None),
                "arac_destegi": getattr(session, "tool_support", "none"),
                "olcum_gecti": bool(getattr(session, "tool_eval_passed", False)),
                "etkin": bool(getattr(session, "enabled", False)),
            }
        )
    return cards

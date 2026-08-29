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
from typing import Any, Protocol

from .web_browser import WEB_BROWSER_PROVIDERS, browser_profile_dir, normalize_account


class SecretReader(Protocol):
    @property
    def available(self) -> bool: ...
    def get(self, env_name: str) -> str | None: ...


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
        cards.append(
            {
                "id": provider_id,
                "ad": definition.name,
                "adres": definition.home_url,
                "hesap": account,
                # Bu sağlayıcılar anahtar kullanmaz; panel anahtar kutusu ÇİZMEZ.
                "anahtar_gerekir": False,
                "bagli": _profile_dir(provider_id, account).exists(),
                "model": getattr(session, "model", None),
                "arac_destegi": getattr(session, "tool_support", "none"),
                "olcum_gecti": bool(getattr(session, "tool_eval_passed", False)),
                "etkin": bool(getattr(session, "enabled", False)),
            }
        )
    return cards

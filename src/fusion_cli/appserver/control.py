"""Native kontrol paneli için güvenli durum ve kimlik bilgisi işlemleri."""

from __future__ import annotations

import os
from typing import Any, Protocol

from ..config.keys import environ_snapshot
from ..config.model_select import reset_to_apprentice_default
from ..config.models import Config
from ..config.writer import write_model_section
from ..core.errors import ConfigError
from ..providers.capabilities import apprentice_active
from ..providers.registry import BUILTIN_PROVIDERS, ProviderDefinition


class SecretStore(Protocol):
    @property
    def available(self) -> bool: ...

    def list_names(self) -> tuple[str, ...]: ...
    def set(self, env_name: str, value: str) -> None: ...
    def delete(self, env_name: str) -> bool: ...


def _provider(provider_id: str) -> ProviderDefinition | None:
    return next(
        (
            item
            for item in BUILTIN_PROVIDERS
            if item.id == provider_id and item.implemented and item.auth_env is not None
        ),
        None,
    )


def provider_catalog_rows(config: Config, store: SecretStore) -> dict[str, Any]:
    """`saglayici.katalog`: tek ve kısa sağlayıcı listesi.

    Web sağlayıcıları ve anahtarlı sağlayıcılar AYNI listede döner; panel iki
    ayrı bölüm çizmek yerine tek liste çizer ve ayrıntıyı tıklayınca açar.
    """
    from ..providers.web_control import provider_catalog

    return {
        "ok": True,
        "saglayicilar": provider_catalog(sessions=config.web_sessions, secret_store=store),
    }


def web_provider_cards(config: Config) -> dict[str, Any]:
    """`web.saglayicilar`: dört tarayıcı sağlayıcısının panel kartları.

    Bu sağlayıcılar API anahtarı kullanmaz; kartlar `anahtar_gerekir: False`
    taşır ve panel onlara anahtar kutusu ÇİZMEZ.
    """
    from ..providers.web_control import provider_cards

    return {
        "ok": True,
        "saglayicilar": provider_cards(sessions=config.web_sessions, secret_store=None),
    }


def start_web_login(saglayici: object, hesap: object) -> dict[str, Any]:
    """`web.giris`: ayrı bir tarayıcı penceresi açar ve süreç kimliğini döndürür."""
    from ..providers.web_control import start_login

    try:
        pid = start_login(str(saglayici or ""), str(hesap or "main"))
    except ValueError as error:
        return {"ok": False, "metin": str(error)}
    except OSError as error:
        return {"ok": False, "metin": f"Giriş tarayıcısı açılamadı: {error}"}
    return {"ok": True, "pid": pid}


def web_login_state(pid: object) -> dict[str, Any]:
    """`web.giris_durumu`: giriş penceresi hâlâ açık mı?

    Panel bunu yoklar; pencere kapandığı anda doğrulamayı KENDİLİĞİNDEN çalıştırır,
    kullanıcı elle çerez kopyalamak zorunda kalmaz.
    """
    from ..providers.web_control import login_exit_code, process_alive

    if not isinstance(pid, (int, str)):
        return {"ok": False, "metin": "Geçersiz süreç kimliği."}
    try:
        numeric = int(pid)
    except (TypeError, ValueError):
        return {"ok": False, "metin": "Geçersiz süreç kimliği."}
    alive = process_alive(numeric)
    code = login_exit_code(numeric)
    if not alive and code not in (None, 0):
        return {
            "ok": False,
            "acik": False,
            "metin": "Chrome giriş penceresi hata ile kapandı. Yeniden dene.",
        }
    return {"ok": True, "acik": alive}


def connect_web_session(
    config: Config, saglayici: object, hesap: object
) -> tuple[Config | None, dict[str, Any]]:
    """`web.baglan`: giriş sonrası oturumu yapılandırmaya yaz ve etkinleştir.

    Giriş penceresinin kapanması tek başına yetmez: oturum `web_sessions`'a
    yazılmazsa Fusion o sağlayıcıyı model yönlendirmesinde HİÇ kullanamaz.
    """
    from ..providers.web_control import register_session

    return register_session(config, str(saglayici or ""), str(hesap or "main"))


def disconnect_web_session(
    config: Config, saglayici: object, hesap: object
) -> tuple[Config | None, dict[str, Any]]:
    """`web.cikis`: oturumu kaldır ve tarayıcı profilini sil."""
    from ..providers.web_control import remove_session

    return remove_session(config, str(saglayici or ""), str(hesap or "main"))


async def verify_web_session(config: Config, saglayici: object, hesap: object) -> dict[str, Any]:
    """`web.dogrula`: gerçek ve küçük bir istekle oturumun çalıştığını kanıtla."""
    from ..providers.web_control import validate_session

    return await validate_session(config, str(saglayici or ""), str(hesap or "main"))


def secret_store_error(store: SecretStore) -> str | None:
    """Anahtarlık okunamıyorsa SEBEBİNİ döndür; okunuyorsa None.

    Hatayı yutup boş liste göstermek, kullanıcıya kayıtlı anahtarını kaybetmiş
    gibi görünür ve gerçek arızayı (kilitli anahtarlık, erişim reddi) gizler.
    Sebep taşınır; sırrın kendisi bu sınırdan hiçbir koşulda geçmez.
    """
    if not store.available:
        return "Sistem anahtarlığı bu ortamda kullanılamıyor."
    try:
        store.list_names()
    except Exception as error:  # anahtarlık arızası uygulamayı düşürmemeli
        return f"Sistem anahtarlığı okunamadı: {error}"
    return None


def provider_rows(store: SecretStore) -> list[dict[str, Any]]:
    """Yalnız metadata döndür; sır değeri hiçbir zaman bu sınıra geçmez."""
    try:
        stored = set(store.list_names()) if store.available else set()
    except Exception:
        # Sebep ayrıca `secret_store_error` ile taşınır; burada liste yine de
        # üretilir ki panel boş kalmasın.
        stored = set()
    environment = environ_snapshot()
    return [
        {
            "id": provider.id,
            "ad": provider.name,
            "ortam": provider.auth_env,
            "kurulu": provider.auth_env in stored
            or bool(environment.get(provider.auth_env or "", "").strip()),
        }
        for provider in BUILTIN_PROVIDERS
        if provider.implemented and provider.auth_env is not None
    ]


def _onerilen_cirak_model(config: Config) -> str | None:
    """Kullanıcı "çırağa dön" derse hangi model çalışacak?

    Panel bunu yalnız GÖSTERİR; kullanıcı düğmeye basmadan hiçbir şeyi değiştirmez.
    """
    tier = config.tier_by_name("low")
    return tier.agent.model if tier is not None else None


def snapshot(
    config: Config,
    store: SecretStore,
    *,
    root: str,
    approval: str,
    engine: str,
    gateway: dict[str, Any],
) -> dict[str, Any]:
    web_session = next(
        (session for session in config.web_sessions if session.model == config.agent.model),
        None,
    )
    agent_label = (
        f"{web_session.provider.removesuffix('_web').title()} · "
        f"{web_session.selected_model or 'otomatik'}"
        if web_session is not None else ""
    )
    return {
        "ok": True,
        "kok": root,
        "model": {
            "agent": config.agent.model,
            "agent_label": agent_label,
            "hakem": config.judge.model,
            "adaylar": [candidate.model for candidate in config.candidates],
            "saglayici": config.runtime.provider,
            "yogunluk": config.runtime.reasoning_effort.value,
            # Faz 3, Görev 2 (C5/C9): agent şu an ücretsiz API çırağıyla mı
            # çalışıyor, yoksa bir web oturumuna mı kilitli? Panel bu iki alanla
            # "ücretsiz çırağa dön" CTA'sını gösterip göstermeyeceğine karar verir.
            "cirak_aktif": apprentice_active(config),
            "onerilen_cirak": _onerilen_cirak_model(config),
        },
        "izin": {
            "mod": approval,
            "kokle_sinirli": config.runtime.restrict_to_root,
        },
        "mcp": [{"ad": server.name, "komut": server.command} for server in config.mcp_servers],
        "saglayicilar": provider_rows(store),
        "sir_deposu_hazir": store.available,
        "sir_deposu_hatasi": secret_store_error(store),
        "gateway": gateway,
    }


def save_secret(store: SecretStore, provider_id: str, value: object) -> dict[str, Any]:
    definition = _provider(provider_id)
    secret = value.strip() if isinstance(value, str) else ""
    if definition is None:
        return {"ok": False, "metin": "Sağlayıcı bulunamadı veya anahtar kabul etmiyor."}
    if not secret or len(secret) > 65_536:
        return {"ok": False, "metin": "Anahtar boş ya da izin verilen boyuttan büyük."}
    if not store.available:
        return {"ok": False, "metin": "Sistem anahtarlığı kullanılamıyor."}
    store.set(definition.auth_env or "", secret)
    # Çalışan oturum yeni anahtarı hemen kullanabilsin; değer yanıta/loga girmez.
    os.environ[definition.auth_env or ""] = secret
    return {"ok": True, "saglayici": definition.id, "kurulu": True}


def delete_secret(store: SecretStore, provider_id: str) -> dict[str, Any]:
    definition = _provider(provider_id)
    if definition is None:
        return {"ok": False, "metin": "Sağlayıcı bulunamadı veya anahtar kabul etmiyor."}
    if store.available:
        store.delete(definition.auth_env or "")
    os.environ.pop(definition.auth_env or "", None)
    return {"ok": True, "saglayici": definition.id, "kurulu": False}


def reset_apprentice_default(config: Config) -> tuple[Config, dict[str, Any]]:
    """`kontrol.cirak_varsayilanina_don`: web kilidini kaldır, çırağa dön, kalıcılaştır.

    Yalnızca kullanıcı panelde düğmeye ya da CLI'de karşılık gelen komuta
    BASTIĞINDA çağrılır; hiçbir arka plan kodu bunu kendiliğinden tetiklemez
    (bkz. Faz 3, Görev 2, §6.1). Kalıcılaştırma başarısız olursa (ör. yapılandırma
    dosyası yazılamıyor) oturumdaki değişiklik yine de uygulanır — kullanıcı
    yeniden başlatana kadar çırakla çalışmaya devam eder, yalnızca bir sonraki
    açılışta eski seçim geri gelir; bu yüzden hata SÖYLENİR, akış durdurulmaz.
    """
    yeni = reset_to_apprentice_default(config)
    try:
        write_model_section(yeni)
    except ConfigError as error:
        return yeni, {
            "ok": True,
            "kalicilastirildi": False,
            "metin": f"Çırağa dönüldü ama kalıcılaştırılamadı: {error}",
            "cirak_aktif": apprentice_active(yeni),
            "onerilen_cirak": _onerilen_cirak_model(yeni),
        }
    return yeni, {
        "ok": True,
        "kalicilastirildi": True,
        "cirak_aktif": apprentice_active(yeni),
        "onerilen_cirak": _onerilen_cirak_model(yeni),
    }

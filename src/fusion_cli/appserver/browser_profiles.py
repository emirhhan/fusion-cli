"""`tarayici.*` RPC'leri — Ayarlar › Web oturumları ekranının arka ucu (P-024).

Tel üzerine çerez DEĞERİ hiç çıkmaz: profil satırları alan adı, sayı, kaynak ve zaman
taşır; önizleme yanıtları yalnız alan adı listesi verir. Hatalar `{"ok": False,
"metin": …}` ile kullanıcıya Türkçe döner; iz basılmaz.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..config.browser_profiles import BrowserProfileStore, BrowserProfileSummary
from ..config.models import Config
from ..config.writer import write_browser_setting
from ..core.errors import FusionError
from ..engines.browser_profiles import (
    find_chrome_profile,
    import_chrome_profile,
    import_cookie_file,
    preview_chrome_profile,
    preview_cookie_file,
)
from ..engines.web_session_import import (
    available_web_sessions,
    find_web_session,
    import_web_session,
    preview_web_session,
)
from ..providers.chrome_cookies import list_chrome_profiles

_CHROME_NEED_DOMAIN = (
    "Chrome'dan aktarırken en az bir alan adı seç; bütün Chrome oturumları taşınmaz."
)
#: `tarayici.ayar` ile yazılabilen boolean ayarlar (varsayılan profil ayrı RPC'dir).
#: `panel_agent` (P-045): masaüstünde ajan uygulama içi Tarayıcı panelini paylaşır.
_BOOL_SETTINGS = ("headless", "profiles_enabled", "panel_agent", "tools")
_KEY_MISSING = (
    "Şifreleme anahtarı yok: tarayıcı profilleri kaydedilemez. Sistem anahtarlığını aç ya da "
    "FUSION_SECRET_KEY tanımla."
)


def _row(summary: BrowserProfileSummary) -> dict[str, Any]:
    data = asdict(summary)
    return {
        "ad": data["name"],
        "alan_adlari": list(data["domains"]),
        "onayli_alan_adlari": list(data["allowed_domains"]),
        "cerez_sayisi": data["cookie_count"],
        "kaynak": data["source"],
        "ice_aktarma": data["imported_at"],
        "son_kullanim": data["last_used_at"],
    }


def _fail(error: FusionError) -> dict[str, Any]:
    return {"ok": False, "metin": str(error)}


def _domains(raw: object) -> tuple[str, ...] | None:
    if not isinstance(raw, list):
        return None
    cleaned = tuple(sorted({str(item).strip().lower() for item in raw if str(item).strip()}))
    return cleaned or None


def list_profiles(store: BrowserProfileStore, config: Config) -> dict[str, Any]:
    """`tarayici.profiller`: profil satırları + yapılandırmadaki varsayılan ve kipler."""
    try:
        rows = [_row(item) for item in store.list()]
    except FusionError as error:
        return _fail(error)
    return {
        "ok": True,
        "profiller": rows,
        "varsayilan": config.browser.default_profile,
        "headless": config.browser.headless,
        "etkin": config.browser.profiles_enabled,
        "panel_ajan": config.browser.panel_agent,
        "araclar": getattr(config.browser, "tools", True),
        "anahtar_var": store.available,
        "metin": "" if store.available else _KEY_MISSING,
    }


def preview_file(data: dict[str, Any]) -> dict[str, Any]:
    """`tarayici.dosya_onizle`: dosyadaki alan adları (değer yok)."""
    path = str(data.get("yol") or "").strip()
    if not path:
        return {"ok": False, "metin": "Dosya yolu gerekli."}
    try:
        preview = preview_cookie_file(Path(path).expanduser())
    except FusionError as error:
        return _fail(error)
    return {"ok": True, "alan_adlari": list(preview.domains), "cerez_sayisi": preview.cookie_count}


def chrome_profiles(data: dict[str, Any]) -> dict[str, Any]:
    """`tarayici.chrome_profilleri`: Chrome profilleri; seçiliyse alan adı önizlemesi."""
    try:
        found = list_chrome_profiles()
        rows = [{"dizin": item.directory.name, "ad": item.label} for item in found]
        selected = str(data.get("chrome_profil") or "").strip()
        preview = None
        if selected:
            preview = preview_chrome_profile(find_chrome_profile(selected))
    except FusionError as error:
        return _fail(error)
    result: dict[str, Any] = {"ok": True, "profiller": rows}
    if preview is not None:
        result["alan_adlari"] = list(preview.domains)
    return result


def import_profile(store: BrowserProfileStore, data: dict[str, Any]) -> dict[str, Any]:
    """`tarayici.ice_aktar`: `yol` (dosya) YA DA `chrome_profil`; `alan_adlari` onay listesi."""
    name = str(data.get("ad") or "").strip()
    domains = _domains(data.get("alan_adlari"))
    path = str(data.get("yol") or "").strip()
    chrome = str(data.get("chrome_profil") or "").strip()
    if not store.available:
        return {"ok": False, "metin": _KEY_MISSING}
    try:
        if path:
            summary = import_cookie_file(store, Path(path).expanduser(), name, domains=domains)
        elif chrome:
            if domains is None:
                # CLI'daki `--all-domains` karşılığı yok: arayüz alan adı seçtirir (P-024).
                return {"ok": False, "metin": _CHROME_NEED_DOMAIN}
            summary = import_chrome_profile(
                store, find_chrome_profile(chrome), name, domains=domains
            )
        else:
            return {"ok": False, "metin": "Dosya yolu ya da Chrome profili seçilmeli."}
    except FusionError as error:
        return _fail(error)
    return {"ok": True, "profil": _row(summary), "metin": f"'{summary.name}' profili yazıldı."}


def delete_profile(store: BrowserProfileStore, data: dict[str, Any]) -> dict[str, Any]:
    """`tarayici.sil`: profil dizinini kaldır."""
    name = str(data.get("ad") or "").strip()
    try:
        removed = store.delete(name)
    except FusionError as error:
        return _fail(error)
    if not removed:
        return {"ok": False, "metin": f"Profil yok: {name}"}
    return {"ok": True, "metin": f"'{name}' silindi."}


def set_setting(config: Config, data: dict[str, Any]) -> dict[str, Any]:
    """`tarayici.ayar`: `browser.headless` / `profiles_enabled` / `panel_agent` yaz (boolean)."""
    key = str(data.get("anahtar") or "").strip()
    value = data.get("deger")
    if key not in _BOOL_SETTINGS:
        return {"ok": False, "metin": f"Bilinmeyen tarayıcı ayarı: {key or '(boş)'}"}
    if not isinstance(value, bool):
        return {"ok": False, "metin": f"browser.{key} için true/false bekleniyor."}
    try:
        write_browser_setting(config, key, value)
    except (FusionError, ValueError) as error:
        return {"ok": False, "metin": str(error)}
    return {"ok": True, "anahtar": key, "deger": value}


def start_login(data: dict[str, Any]) -> dict[str, Any]:
    """`tarayici.giris`: görünür giriş penceresini alt süreçte aç; `pid` döndür."""
    from ..providers.web_control import start_browser_profile_login

    name = str(data.get("ad") or "").strip()
    url = str(data.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "metin": "Giriş adresi http:// ya da https:// ile başlamalı."}
    try:
        pid = start_browser_profile_login(name, url)
    except FusionError as error:
        return _fail(error)
    except OSError as error:
        return {"ok": False, "metin": f"Giriş penceresi açılamadı: {error}"}
    return {"ok": True, "pid": pid}


def set_default(config: Config, data: dict[str, Any], store: BrowserProfileStore) -> dict[str, Any]:
    """`tarayici.varsayilan`: `browser.default_profile`'ı yaz (boş = kaldır)."""
    name = str(data.get("ad") or "").strip()
    try:
        if name:
            store.summary(name)
        write_browser_setting(config, "default_profile", name)
    except (FusionError, ValueError) as error:
        return {"ok": False, "metin": str(error)}
    return {"ok": True, "varsayilan": name}


def web_sessions(data: dict[str, Any]) -> dict[str, Any]:
    """`tarayici.web_oturumlari`: web model oturumları; seçiliyse alan adları (değer yok)."""
    try:
        rows = [
            {"saglayici": item.provider, "hesap": item.account} for item in available_web_sessions()
        ]
        provider = str(data.get("saglayici") or "").strip()
        preview = None
        if provider:
            source = find_web_session(provider, str(data.get("hesap") or "main"))
            preview = preview_web_session(source)
    except FusionError as error:
        return _fail(error)
    result: dict[str, Any] = {"ok": True, "oturumlar": rows}
    if preview is not None:
        result["alan_adlari"] = list(preview.domains)
    return result


async def import_from_web_session(
    store: BrowserProfileStore, data: dict[str, Any]
) -> dict[str, Any]:
    """`tarayici.web_oturumu_aktar`: `{saglayici, hesap, ad, alan_adlari}` → şifreli profil.

    Onay masaüstündedir: kullanıcı alan adlarını işaretleyip "Aktar"a basar; hiçbiri hazır
    seçili gelmez ve boş seçimle bu RPC reddeder (CLI'daki `-d` zorunluluğu).
    """
    if not store.available:
        return {"ok": False, "metin": _KEY_MISSING}
    try:
        source = find_web_session(
            str(data.get("saglayici") or ""), str(data.get("hesap") or "main")
        )
        summary = await import_web_session(
            store, source, str(data.get("ad") or "").strip(), _domains(data.get("alan_adlari"))
        )
    except FusionError as error:
        return _fail(error)
    return {"ok": True, "profil": _row(summary), "metin": f"'{summary.name}' profili yazıldı."}

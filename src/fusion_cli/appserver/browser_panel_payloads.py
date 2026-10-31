"""Tarayıcı paneli (P-045) RPC yüklerinin biçimi ve "Panel oturumu" profilinin kurulumu."""

from __future__ import annotations

from typing import Any

from ..config.browser_profiles import BrowserProfileStore
from ..core.errors import BrowserProfileError
from ..tools import browser_picker
from ..tools.browser_live import LiveSnapshot

#: "Keep cookies" karşılığı: panelde gezilen oturumun saklandığı profil adı.
PANEL_PROFILE = "tarayici-paneli"


def ensure_panel_profile(store: BrowserProfileStore) -> str:
    """ "Panel oturumu" profili yoksa boş olarak kur; anahtar yoksa hata metni."""
    if not store.available:
        return "Panel oturumu saklanamaz: sır deposu anahtarı yok (fusion doctor)."
    try:
        if not store.exists(PANEL_PROFILE):
            store.save(PANEL_PROFILE, (), source="panel")
    except BrowserProfileError as error:
        return str(error)
    return ""


def element_payload(element: browser_picker.PickedElement) -> dict[str, Any]:
    return {
        "etiket": element.tag,
        "secici": element.selector,
        "oge_metni": element.text,
        "kutu": element.normalized_box(),
    }


def snapshot_payload(snapshot: LiveSnapshot) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "seq": snapshot.seq,
        "url": snapshot.url,
        "baslik": snapshot.title,
        "sekmeler": [
            {"no": tab.index, "baslik": tab.title, "url": tab.url, "etkin": tab.is_active}
            for tab in snapshot.tabs
        ],
    }
    if snapshot.frame is not None:
        payload["kare"] = {
            "base64": snapshot.frame.data,
            "mime": "image/jpeg",
            "genislik": snapshot.frame.css_width,
            "yukseklik": snapshot.frame.css_height,
        }
    return payload

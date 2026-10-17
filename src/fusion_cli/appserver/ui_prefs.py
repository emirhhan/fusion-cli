"""Arayüz tercihleri: webview `localStorage`'ı güvenilmez olduğu için çekirdekte yedeklenir.

Neden: tarayıcı deposu bu kurulumda yazılmayabiliyor (bkz. `tests/test_theme_persistence.py`,
`WebsiteData/LocalStorage` 0 bayt). Pencere düzeni, kenar çubuğu, proje kayıtları gibi
`fusion.` ile başlayan tercihler burada anahtar → metin olarak durur ve açılışta arayüze
geri yüklenir. Hesap çıkışı bu dosyaya DOKUNMAZ.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .voice import _data_home

PREFIX = "fusion."
#: Tek değer sınırı; proje kaydı gibi küçük JSON'lar için bol, sınırsız büyümeye karşı.
MAX_VALUE = 64_000
MAX_KEYS = 200


def prefs_path() -> Path:
    return _data_home() / "ui-prefs.json"


def _read() -> dict[str, str]:
    try:
        raw = json.loads(prefs_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}


def load() -> dict[str, Any]:
    """`ayar.arayuz`: kayıtlı tüm tercihler."""
    return {"ok": True, "degerler": _read()}


def save(data: object) -> dict[str, Any]:
    """`ayar.arayuz_kaydet`: `{anahtar, deger}`; `deger` null ise anahtar silinir."""
    if not isinstance(data, dict):
        return {"ok": False, "metin": "Geçersiz istek."}
    key, value = data.get("anahtar"), data.get("deger")
    if not isinstance(key, str) or not key.startswith(PREFIX):
        return {"ok": False, "metin": "Tercih anahtarı fusion. ile başlamalı."}
    if value is not None and (not isinstance(value, str) or len(value) > MAX_VALUE):
        return {"ok": False, "metin": "Tercih değeri metin olmalı ve çok büyük olmamalı."}
    current = _read()
    if value is None:
        current.pop(key, None)
    elif key not in current and len(current) >= MAX_KEYS:
        return {"ok": False, "metin": "Çok fazla tercih kaydı var."}
    else:
        current[key] = value
    try:
        path = prefs_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as error:
        return {"ok": False, "metin": f"Tercih kaydedilemedi: {error}"}
    return {"ok": True}

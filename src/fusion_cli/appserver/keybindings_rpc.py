"""Masaüstü kısayol uçları (P-046): `kisayol.liste|ata|kaldir|sifirla`.

Kaynak, terminalle AYNI `~/.fusion/keybindings.json` dosyasının `masaustu` bağlamıdır; yazma
`config/keybinding_edit.py` üzerinden yapılır. Her başarılı yanıt güncel tabloyu da taşır:
arayüz ikinci bir istek atmadan dinleyicisini tazeler.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config.desktop_keys import CONTEXT_DESKTOP, desktop_key_data
from ..config.keybinding_edit import KeyEditResult, bind_action, reset_action, unbind_action
from ..config.keybindings import DEFAULT_KEYMAP, keybindings_path, load_keymap
from ..core.errors import ConfigError

_INVALID_REQUEST = "Geçersiz kısayol isteği."
_CONFLICT = "{key} zaten “{label}” eylemine bağlı."
_WRITE_FAILED = "Kısayol dosyası yazılamadı: {error}"

Handler = Callable[[dict[str, Any]], dict[str, Any]]


def list_bindings(_data: dict[str, Any] | None = None, path: Path | None = None) -> dict[str, Any]:
    """Etkin masaüstü tablosu, varsayılanlar, eylem etiketleri ve bu bağlamın uyarıları."""
    keymap = load_keymap(path or keybindings_path())
    labels = desktop_key_data().labels
    return {
        "ok": True,
        "yol": str(keymap.path),
        "baglar": keymap.bindings(CONTEXT_DESKTOP),
        "varsayilan": dict(desktop_key_data().defaults),
        "eylemler": [{"ad": name, "etiket": label} for name, label in labels.items()],
        # Terminal bağlamlarının uyarıları masaüstünü ilgilendirmez; dosya düzeyindekiler kalır.
        "uyarilar": [
            warning
            for warning in keymap.warnings
            if not warning.startswith(tuple(f"{name}." for name in DEFAULT_KEYMAP))
        ],
    }


def _action(data: dict[str, Any]) -> str | None:
    value = data.get("eylem")
    return value if isinstance(value, str) and value else None


def _respond(path: Path, run: Callable[[], KeyEditResult], key: str = "") -> dict[str, Any]:
    try:
        result = run()
    except ConfigError as error:
        return {"ok": False, "metin": str(error)}
    except OSError as error:
        return {"ok": False, "metin": _WRITE_FAILED.format(error=error)}
    if result.conflict:
        label = desktop_key_data().labels.get(result.conflict, result.conflict)
        taken = result.key or key
        return {
            "ok": False,
            "cakisma": result.conflict,
            "tus": taken,
            "metin": _CONFLICT.format(key=taken, label=label),
        }
    if not result.ok:
        return {"ok": False, "metin": f"Kısayol kaydedilmedi: {result.problem}."}
    return list_bindings(path=path)


def assign(data: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """`{eylem, tus, zorla?}`: eylemi yalnız bu tuşa bağla."""
    target = path or keybindings_path()
    action, key = _action(data), data.get("tus")
    if action is None or not isinstance(key, str) or not key.strip():
        return {"ok": False, "metin": _INVALID_REQUEST}
    force = data.get("zorla") is True
    return _respond(
        target,
        lambda: bind_action(target, CONTEXT_DESKTOP, action, key, force=force),
        key=key.strip(),
    )


def remove(data: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """`{eylem}`: eylemin tuşlarını kaldır."""
    target = path or keybindings_path()
    action = _action(data)
    if action is None:
        return {"ok": False, "metin": _INVALID_REQUEST}
    return _respond(target, lambda: unbind_action(target, CONTEXT_DESKTOP, action))


def reset(data: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """`{eylem?, zorla?}`: eylemi ya da (eylemsiz) bütün masaüstü tablosunu varsayılana döndür.

    Eylemin varsayılan tuşu başka eylemdeyse çakışma (`cakisma`, `tus`) döner; `zorla` alır.
    """
    target = path or keybindings_path()
    action = _action(data)
    if data.get("eylem") is not None and action is None:
        return {"ok": False, "metin": _INVALID_REQUEST}
    force = data.get("zorla") is True
    return _respond(target, lambda: reset_action(target, CONTEXT_DESKTOP, action, force=force))


KEYBINDING_ROUTES: dict[str, Handler] = {
    "kisayol.liste": list_bindings,
    "kisayol.ata": assign,
    "kisayol.kaldir": remove,
    "kisayol.sifirla": reset,
}

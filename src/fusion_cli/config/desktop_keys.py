"""Masaüstü uygulama kısayolları (P-046): `keybindings.json` içindeki `masaustu` bağlamı.

Claude Code masaüstündeki ⌘K/⌘N/⌘B/⌘J/⌘1-9 modeli örnek alınmıştır. Varsayılan tablo, eylem
etiketleri ve ayrılmış tuşlar `data/masaustu-kisayollari.json` dosyasındadır; masaüstü arayüzü
(`app/src/shortcuts/keys.ts`) AYNI dosyayı içe aktarır, iki kopya tutulmaz.

Tuş yazımı platformdan bağımsızdır: `mod` macOS'ta ⌘, Windows/Linux'ta Ctrl'dir. Biçim
`mod+ctrl+alt+shift+<tuş>` sırasıyla kanonikleştirilir (`Mod+Shift+P` → `mod+shift+p`).
Masaüstü bağı en az bir değiştirici (mod/ctrl/alt) ya da F1-F12 ister: değiştiricisiz tuş
yazarken her harfte tetiklenirdi. Kopyala/yapıştır/çıkış gibi sistem tuşları bağlanamaz.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

#: Bağlam adı (`keybindings.json` kökündeki anahtar).
CONTEXT_DESKTOP = "masaustu"
#: Değiştiriciler kanonik sırada.
MODIFIERS = ("mod", "ctrl", "alt", "shift")
#: Tek başına bağlanabilen adlı tuşlar (değiştiricisiz).
_BARE_ALLOWED_PREFIX = "f"
_DATA_FILE = "data/masaustu-kisayollari.json"


@dataclass(frozen=True, slots=True)
class DesktopKeyData:
    """Paylaşılan veri dosyasının tiplenmiş hâli."""

    defaults: dict[str, str]
    labels: dict[str, str]
    reserved: frozenset[str]
    named_keys: frozenset[str]


@cache
def desktop_key_data() -> DesktopKeyData:
    """Paket verisini bir kez oku (import anında dosya erişimi yok)."""
    raw = json.loads(files(__package__).joinpath(_DATA_FILE).read_text(encoding="utf-8"))
    return DesktopKeyData(
        defaults=dict(raw["varsayilan"]),
        labels=dict(raw["eylemler"]),
        reserved=frozenset(raw["ayrilmis"]),
        named_keys=frozenset(raw["adli_tuslar"]),
    )


def desktop_defaults() -> dict[str, str]:
    return dict(desktop_key_data().defaults)


def desktop_actions() -> frozenset[str]:
    return frozenset(desktop_key_data().labels)


def normalize_desktop_key(raw: str) -> str | None:
    """`Mod+Shift+P` → `mod+shift+p`; geçersiz yazımda `None`.

    Son parça tek yazdırılabilir karakter ya da adlı tuş (`f5`, `escape`) olmalı; değiştirici
    tekrar edemez. `+` tuşunun kendisi `mod++` yazılır. Noktalama tuşunda `shift` düşer: karakter
    onu zaten taşır (Türkçe Q klavyede `/` Shift+7'dir; `mod+/` her düzende aynı bağdır).
    """
    text = raw.strip().lower()
    if not text:
        return None
    parts, key = _split(text)
    if any(part not in MODIFIERS for part in parts) or len(set(parts)) != len(parts):
        return None
    if not (len(key) == 1 and key.isprintable() and not key.isspace()) and (
        key not in desktop_key_data().named_keys
    ):
        return None
    if len(key) == 1 and not key.isalnum():
        parts = [part for part in parts if part != "shift"]
    ordered = [modifier for modifier in MODIFIERS if modifier in parts]
    return "+".join([*ordered, key])


def desktop_key_problem(key: str) -> str | None:
    """Kanonik tuş bağlanabilir mi? Değilse kısa Türkçe neden."""
    if key in desktop_key_data().reserved:
        return "sistem kısayolu (kopyala/yapıştır/kapat), bağlanamaz"
    parts, final = _split(key)
    has_modifier = any(part in ("mod", "ctrl", "alt") for part in parts)
    is_function_key = final.startswith(_BARE_ALLOWED_PREFIX) and final[1:].isdigit()
    if not has_modifier and not is_function_key:
        return "mod, ctrl ya da alt ile birlikte olmalı (yalnız F1-F12 tek başına bağlanır)"
    return None


def _split(text: str) -> tuple[list[str], str]:
    """`mod+shift+p` → (["mod", "shift"], "p"); `mod++` → (["mod"], "+")."""
    if text.endswith("++") or text == "+":
        head, key = text[:-2] if len(text) > 1 else "", "+"
    else:
        head, _, key = text.rpartition("+")
    return [part for part in head.split("+") if part], key

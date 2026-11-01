"""Özelleştirilebilir tuş bağları (P-067): `~/.fusion/keybindings.json`, `/keybindings`.

Claude Code `keybindings.json` modeli örnek alınmıştır: bağlam → {tuş: eylem}. Eylem adları
Türkçe sabitlerdir; `komut:<ad>` ile herhangi bir slash komutu tuşa bağlanır; `null`
varsayılan bağı kaldırır. Dosya yoksa varsayılan tablo geçerlidir; dosya değişince REPL
bir sonraki istemde yeniden yükler (yeniden başlatma gerekmez).

Yapısal tuşlar (Enter, Tab, oklar, seçim modalındaki tuşlar) bağlanamaz: bunlar girdinin
ve modalların çalışma biçimidir, eylem değil. Bozuk dosya ya da bilinmeyen eylem oturumu
düşürmez; uyarı listesine girer ve `/keybindings` gösterir.

Aynı dosyanın `masaustu` bağlamı masaüstü uygulamasının kısayollarıdır (P-046, bkz.
`desktop_keys.py`); tuş yazımı orada `mod+k` biçimindedir ve ayrı doğrulanır.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .desktop_keys import (
    CONTEXT_DESKTOP,
    desktop_actions,
    desktop_defaults,
    desktop_key_problem,
    normalize_desktop_key,
)
from .paths import user_config_dir

#: Bağlam adları: satır-içi istem ve tam-ekran uygulama.
CONTEXT_INPUT = "giris"
CONTEXT_TUI = "tui"
#: Komut bağlama öneki: `komut:help` → `/help` gönderir.
COMMAND_PREFIX = "komut:"
#: Dosya adı (kullanıcı yapılandırma dizininde).
FILE_NAME = "keybindings.json"
#: `/keybindings` çıktısında masaüstü bağlamının yerine gösterilen satır.
DESKTOP_HINT = f"[{CONTEXT_DESKTOP}] masaüstü kısayolları uygulamada: Ayarlar › Kısayollar"

#: Varsayılan tablo — `input.py` ve `tui.py` eskiden sabit kodladığı bağların tamamı.
DEFAULT_KEYMAP: dict[str, dict[str, str]] = {
    CONTEXT_INPUT: {"s-tab": "kip_dongusu", "c-v": "yapistirma_katla"},
    CONTEXT_TUI: {
        # Claude Code (#195): Ctrl+C keser / girdiyi temizler / ikinci basışta çıkar; Ctrl+D
        # boş girdide 800 ms içinde iki basışla çıkar. Ctrl+U/Ctrl+R/Ctrl+D satır düzenleme
        # ve geçmiş içindir, kaydırma PageUp/PageDown/Ctrl+Home/Ctrl+End/Shift+oklarda.
        "c-c": "kes_temizle_cik",
        "c-d": "cift_basista_cik",
        "escape": "kes",
        "s-tab": "kip_dongusu",
        "pageup": "sayfa_yukari",
        "pagedown": "sayfa_asagi",
        "home": "en_bas",
        "c-home": "en_bas",
        "end": "en_son",
        "c-end": "en_son",
        "s-up": "kaydir_yukari",
        "s-down": "kaydir_asagi",
        # Süren turu arka plan görevine taşı (P-048; Claude Code Ctrl+B).
        "c-b": "arka_plana_al",
    },
}
#: Bağlam başına geçerli eylemler (`komut:*` hepsinde geçerli).
ACTIONS: dict[str, frozenset[str]] = {
    CONTEXT_INPUT: frozenset({"kip_dongusu", "yapistirma_katla"}),
    CONTEXT_TUI: frozenset(
        {
            "cik",
            "kes",
            "kes_temizle_cik",
            "cift_basista_cik",
            "kip_dongusu",
            "sayfa_yukari",
            "sayfa_asagi",
            "en_bas",
            "en_son",
            "kaydir_yukari",
            "kaydir_asagi",
            "arka_plana_al",
        }
    ),
}
#: Yapısal tuşlar: bağlanamaz (girdi/modal işleyişi).
RESERVED_KEYS = frozenset({"enter", "c-m", "c-j", "tab", "c-i", "up", "down", "left", "right"})


@dataclass(frozen=True, slots=True)
class KeyMap:
    """Çözümlenmiş tuş tablosu + dosya izi (değişim denetimi için)."""

    contexts: dict[str, dict[str, str]]
    path: Path
    mtime: float
    warnings: tuple[str, ...] = field(default=())

    def bindings(self, context: str) -> dict[str, str]:
        return dict(self.contexts.get(context, {}))


def keybindings_path() -> Path:
    return user_config_dir() / FILE_NAME


def default_keymap() -> dict[str, dict[str, str]]:
    """Bütün bağlamların varsayılanları (terminal + masaüstü); her çağrıda yeni kopya."""
    tables = {name: dict(table) for name, table in DEFAULT_KEYMAP.items()}
    tables[CONTEXT_DESKTOP] = desktop_defaults()
    return tables


def is_valid_action(context: str, action: str) -> bool:
    if action.startswith(COMMAND_PREFIX):
        return bool(action[len(COMMAND_PREFIX) :].strip())
    if context == CONTEXT_DESKTOP:
        return action in desktop_actions()
    return action in ACTIONS.get(context, frozenset())


def _valid_actions_hint(context: str) -> str:
    names = desktop_actions() if context == CONTEXT_DESKTOP else ACTIONS[context]
    return ", ".join(sorted(names)) + f", {COMMAND_PREFIX}<ad>"


def normalize_key(context: str, key: object) -> tuple[str | None, str | None]:
    """Bağlama göre tuşu kanonikleştir: (tuş, sorun). Sorun varsa tuş `None`."""
    lowered = str(key).strip().lower()
    if context != CONTEXT_DESKTOP:
        if lowered in RESERVED_KEYS:
            return None, "yapısal tuş, bağlanamaz"
        return lowered, None
    canonical = normalize_desktop_key(lowered)
    if canonical is None:
        return None, "tuş yazımı geçersiz (ör. mod+k, mod+shift+p, f5)"
    problem = desktop_key_problem(canonical)
    return (None, problem) if problem else (canonical, None)


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def load_keymap(path: Path | None = None) -> KeyMap:
    """Varsayılanları kullanıcı dosyasıyla birleştir; hatalar uyarı olur, oturum düşmez."""
    target = path or keybindings_path()
    contexts = default_keymap()
    warnings: list[str] = []
    raw: object = None
    if target.is_file():
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            warnings.append(f"{target}: okunamadı, varsayılanlar kullanılıyor ({error})")
            raw = None
    if isinstance(raw, dict):
        for context, table in raw.items():
            if context not in contexts:
                warnings.append(f"bilinmeyen bağlam yok sayıldı: {context}")
                continue
            if not isinstance(table, dict):
                warnings.append(f"{context}: tuş tablosu sözlük olmalı")
                continue
            for key, action in table.items():
                lowered, problem = normalize_key(context, key)
                if lowered is None:
                    warnings.append(f"{context}.{key}: {problem}")
                    continue
                if action is None:
                    contexts[context].pop(lowered, None)
                    continue
                if not isinstance(action, str) or not is_valid_action(context, action):
                    warnings.append(
                        f"{context}.{key}: bilinmeyen eylem {action!r} "
                        f"(geçerli: {_valid_actions_hint(context)})"
                    )
                    continue
                contexts[context][lowered] = action
    elif raw is not None:
        warnings.append(f"{target}: kök bir sözlük olmalı (bağlam → tuş → eylem)")
    return KeyMap(contexts, target, _mtime(target), tuple(warnings))


def has_changed(keymap: KeyMap) -> bool:
    """Dosya son yüklemeden beri değişti mi? (yeniden başlatmadan uygulamak için)"""
    return _mtime(keymap.path) != keymap.mtime


def write_default_file(path: Path | None = None) -> Path:
    """Dosya yoksa terminal varsayılanlarını örnek olarak yaz (kullanıcı düzenleyip kaydeder).

    Ölçüldü (31 Ekim): örnek dosyaya masaüstü tablosu da dökülüyordu; o bağlam dosyada yalnız
    varsayılandan farkları tutar (Ayarlar › Kısayollar yazar), dökülürse sürüm yükseltmesinde
    değişen varsayılan tuş eski hâlinde sabitlenirdi.
    """
    target = path or keybindings_path()
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(DEFAULT_KEYMAP, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return target


def describe(keymap: KeyMap) -> list[str]:
    """`/keybindings` çıktısı: terminal bağlamlarının tuş → eylem satırları ve uyarılar.

    Masaüstü bağlamı tek satırlık yönlendirmeyle geçilir; uyarıları yine listelenir.
    """
    lines: list[str] = []
    for context, table in keymap.contexts.items():
        if context == CONTEXT_DESKTOP:
            continue
        lines.append(f"[{context}]")
        for key, action in sorted(table.items()):
            lines.append(f"  {key:<10} {action}")
    lines.append(DESKTOP_HINT)
    for warning in keymap.warnings:
        lines.append(f"  ! {warning}")
    return lines

"""Claude Code `~/.claude/keybindings.json` biçimi (#194).

Claude Code dosyası `{"bindings": [{"context": "Chat", "bindings": {"ctrl+e": "chat:..."}}]}`
biçimindedir: bağlam adları (`Global`, `Chat`, `Task`, `Scroll`…), `namespace:action`
eylemleri, `ctrl+x` tuş yazımı ve boşlukla ayrılmış chord'lar (`ctrl+x ctrl+e`). Bu modül
dosyayı okur ve Fusion'ın terminal bağlamlarına (`giris`, `tui`) prompt_toolkit tuş
adlarıyla çevirir. Fusion'ın eski `~/.fusion/keybindings.json` biçimi kullanımdan kalkmış
takma ad olarak okunmaya devam eder (`keybindings.py`); bu dosya onun ÜSTÜNE uygulanır.

Ayrılmış kısayollar (Ctrl+C, Ctrl+D, Ctrl+M, Ctrl+[, Ctrl+I, Ctrl+H) Claude Code'daki gibi
bağlanamaz. Claude'un Fusion'da karşılığı olmayan eylemleri dosyayı geçersiz kılmaz; uyarı
listesine girer ve `/keybindings` gösterir.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

FILE_NAME = "keybindings.json"
SCHEMA_URL = "https://www.schemastore.org/claude-code-keybindings.json"
DOCS_URL = "https://code.claude.com/docs/en/keybindings"
COMMAND_PREFIX = "command:"

#: Claude bağlamı → Fusion terminal bağlamları (`keybindings.CONTEXT_INPUT/CONTEXT_TUI`).
CONTEXT_TARGETS: dict[str, tuple[str, ...]] = {
    "Global": ("giris", "tui"),
    "Chat": ("giris", "tui"),
    "Task": ("tui",),
    "Scroll": ("tui",),
}
#: Claude'un belgelediği, Fusion'da ayrı bir yüzeyi olmayan bağlamlar: geçerli, yok sayılır.
KNOWN_CONTEXTS = frozenset(
    {
        *CONTEXT_TARGETS,
        "Autocomplete",
        "Settings",
        "Confirmation",
        "Tabs",
        "Help",
        "Transcript",
        "HistorySearch",
        "ThemePicker",
        "Attachments",
        "Footer",
        "MessageSelector",
        "DiffDialog",
        "DiffPanel",
        "ModelPicker",
        "EffortSlider",
        "Select",
        "Plugin",
        "AbovePrompt",
        "AbovePromptInput",
        "AbovePromptSelect",
        "Pane",
        "PaneField",
        "Agents",
    }
)
#: Claude eylemi → Fusion eylemi.
ACTION_MAP: dict[str, str] = {
    "chat:cycleMode": "kip_dongusu",
    "app:interrupt": "kes",
    "app:exit": "cift_basista_cik",
    "task:background": "arka_plana_al",
    "chat:sendNow": "simdi_gonder",
    "chat:externalEditor": "dis_editor",
    "chat:undo": "geri_al",
    "chat:clearInput": "yeniden_ciz",
    "chat:clearScreen": "yeniden_ciz",
    "app:redraw": "yeniden_ciz",
    "chat:stash": "sakla",
    "chat:modelPicker": "komut:model",
    "scroll:pageUp": "sayfa_yukari",
    "scroll:halfPageUp": "sayfa_yukari",
    "scroll:fullPageUp": "sayfa_yukari",
    "scroll:pageDown": "sayfa_asagi",
    "scroll:halfPageDown": "sayfa_asagi",
    "scroll:fullPageDown": "sayfa_asagi",
    "scroll:top": "en_bas",
    "scroll:bottom": "en_son",
    "scroll:lineUp": "kaydir_yukari",
    "scroll:lineDown": "kaydir_asagi",
}
#: Ayrılmış kısayollar (Claude Code "Reserved shortcuts").
RESERVED = frozenset({"c-c", "c-d", "c-m", "c-[", "c-i", "c-h"})

#: Ctrl+Enter'ın Fusion tuşu (CSI-u dizisi F24'e eşlenir; `cli/repl/tui_input_keys`).
CTRL_ENTER_KEY = "f24"

_MODIFIERS = {
    "ctrl": "c",
    "control": "c",
    "shift": "s",
    "alt": "m",
    "opt": "m",
    "option": "m",
    "meta": "m",
    "cmd": "cmd",
    "command": "cmd",
    "super": "cmd",
    "win": "cmd",
}
_SPECIAL = {
    "escape": "escape",
    "esc": "escape",
    "enter": "enter",
    "return": "enter",
    "tab": "tab",
    "space": "space",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "pageup": "pageup",
    "pagedown": "pagedown",
    "home": "home",
    "end": "end",
    "backspace": "backspace",
    "delete": "delete",
    "wheelup": "<scroll-up>",
    "wheeldown": "<scroll-down>",
}
#: prompt_toolkit'in Shift/Ctrl+Shift biçimini tanıdığı tuşlar.
_SHIFTABLE = frozenset({"up", "down", "left", "right", "home", "end", "delete", "tab"})
_CTRL_SHIFTABLE = frozenset({"up", "down", "left", "right", "home", "end", "delete"})


@dataclass(frozen=True, slots=True)
class ClaudeBindings:
    """Dosyadan çevrilmiş bağlar: bağlam → {prompt_toolkit tuşu: Fusion eylemi | None}."""

    contexts: dict[str, dict[str, str | None]] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


def claude_keybindings_path() -> Path:
    """`$CLAUDE_CONFIG_DIR/keybindings.json` ya da `~/.claude/keybindings.json`."""
    base = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    return (Path(base).expanduser() if base else Path.home() / ".claude") / FILE_NAME


def stroke_to_key(stroke: str) -> str | None:
    """Tek tuş vuruşunu (`ctrl+k`, `shift+tab`, `meta+p`) prompt_toolkit adına çevir."""
    text = stroke.strip().lower()
    if not text:
        return None
    parts = text.split("+")
    if parts[-1] == "" and len(parts) > 1:  # "ctrl++" gibi: artı tuşu
        parts = [*parts[:-2], "+"]
    *mods_raw, key = parts
    mods = set()
    for mod in mods_raw:
        if mod not in _MODIFIERS:
            return None
        mods.add(_MODIFIERS[mod])
    if "cmd" in mods:
        return None  # Terminal Süper tuşunu bildirmez; Fusion'da karşılığı yok.
    base = _SPECIAL.get(key, key)
    if len(base) != 1 and base not in _SPECIAL.values() and not _is_function_key(base):
        return None
    single = _modified(base, mods - {"m"})
    if single is None:
        return None
    return f"escape {single}" if "m" in mods else single


def _modified(base: str, mods: set[str]) -> str | None:
    if mods == {"c", "s"}:
        return f"c-s-{base}" if base in _CTRL_SHIFTABLE else None
    if mods == {"c"}:
        if base == "space":
            return "c-space"
        if base == "enter":
            return CTRL_ENTER_KEY
        if len(base) == 1 or base in _CTRL_SHIFTABLE or _is_function_key(base):
            return f"c-{base}"
        return None
    if mods == {"s"}:
        if len(base) == 1 and base.isalpha():
            return base.upper()
        return f"s-{base}" if base in _SHIFTABLE or _is_function_key(base) else None
    return " " if base == "space" else base


def _is_function_key(name: str) -> bool:
    return len(name) in (2, 3) and name[0] == "f" and name[1:].isdigit()


def keystroke_to_key(keystroke: str) -> str | None:
    """Chord dahil (`ctrl+x ctrl+e`) Claude yazımını Fusion tuş dizesine çevir.

    Fusion tuş dizesi prompt_toolkit adlarının boşlukla birleşimidir (`c-x c-e`).
    """
    strokes = [stroke_to_key(part) for part in keystroke.split()]
    if not strokes or any(stroke is None for stroke in strokes):
        return None
    return " ".join(stroke for stroke in strokes if stroke is not None)


def translate_action(action: str) -> str | None:
    """Claude eylemini Fusion eylemine çevir; karşılığı yoksa `None`."""
    if action.startswith(COMMAND_PREFIX):
        name = action[len(COMMAND_PREFIX) :].strip().lstrip("/")
        return f"komut:{name}" if name else None
    return ACTION_MAP.get(action)


def load_claude_bindings(path: Path) -> ClaudeBindings:
    """Dosyayı oku ve çevir; hatalar uyarı olur, oturum düşmez."""
    if not path.is_file():
        return ClaudeBindings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return ClaudeBindings(warnings=(f"{path}: okunamadı ({error})",))
    blocks = raw.get("bindings") if isinstance(raw, dict) else None
    if not isinstance(blocks, list):
        return ClaudeBindings(warnings=(f"{path}: kökte 'bindings' dizisi olmalı",))
    contexts: dict[str, dict[str, str | None]] = {}
    warnings: list[str] = []
    for block in blocks:
        _apply_block(block, contexts, warnings)
    return ClaudeBindings(contexts, tuple(warnings))


def _apply_block(
    block: object, contexts: dict[str, dict[str, str | None]], warnings: list[str]
) -> None:
    if not isinstance(block, dict):
        warnings.append("bindings: her öğe {context, bindings} nesnesi olmalı")
        return
    context = block.get("context")
    table = block.get("bindings")
    if not isinstance(context, str) or context not in KNOWN_CONTEXTS:
        warnings.append(f"bilinmeyen bağlam yok sayıldı: {context!r}")
        return
    if not isinstance(table, dict):
        warnings.append(f"{context}: bindings bir nesne olmalı")
        return
    targets = CONTEXT_TARGETS.get(context, ())
    if not targets:
        return  # Belgelenmiş bağlam, Fusion'da ayrı yüzeyi yok: dosya geçerli, bağ yok sayılır.
    for keystroke, action in table.items():
        key = keystroke_to_key(str(keystroke))
        if key is None:
            warnings.append(f"{context}.{keystroke}: tuş yazımı geçersiz (ör. ctrl+k, meta+p)")
            continue
        if key in RESERVED:
            warnings.append(f"{context}.{keystroke}: ayrılmış kısayol, bağlanamaz")
            continue
        if action is None:
            for target in targets:
                contexts.setdefault(target, {})[key] = None
            continue
        fusion_action = translate_action(action) if isinstance(action, str) else None
        if fusion_action is None:
            warnings.append(f"{context}.{keystroke}: {action!r} eyleminin Fusion'da karşılığı yok")
            continue
        for target in targets:
            contexts.setdefault(target, {})[key] = fusion_action


def example_file() -> str:
    """`/keybindings` dosya yoksa yazdığı örnek (Claude Code ile aynı iskelet)."""
    body = {"$schema": SCHEMA_URL, "$docs": DOCS_URL, "bindings": []}
    return json.dumps(body, ensure_ascii=False, indent=2) + "\n"

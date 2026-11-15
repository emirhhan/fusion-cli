"""`/config` — ayarları listele, oku, değiştir (P-029).

- `/config` ya da `/config <filtre>` → erişilebilir ayarlar (yol · değer · tip).
- `/config runtime.max_tokens` → tek değer.
- `/config runtime.max_tokens=8192 runtime.agent_max_steps=40` → her çifti oturuma uygular VE
  kullanıcı dosyasına yazar (Claude Code `/config key=value ...`). Claude adları `model`,
  `theme`, `outputStyle`, `editorMode`, `tui` da kabul edilir (bkz. `config_claude_keys`).
  `/settings` takma addır; `/config --help` kullanımı basar.
"""

from __future__ import annotations

import re

from ...config.settings_access import list_settings, read_setting, write_setting
from ...core.errors import ConfigError
from ...tools.capability_overrides import registry_from_config
from ...ui import messages
from .config_claude_keys import CLAUDE_KEYS, claude_handler
from .state import ReplState

#: Listede yol sütununun hizalama genişliği.
_PATH_WIDTH = 40
#: Yeni bir çifti başlatan anahtar: `bölüm.alan[.alt]` yolu ya da Claude ayar adı.
_PAIR_START = re.compile(
    r"^(?:[A-Za-z_][\w-]*(?:\.[\w-]+)+|" + "|".join(map(re.escape, CLAUDE_KEYS)) + r")="
)


def format_settings(state: ReplState, filter_text: str = "") -> str:
    rows = list_settings(state.config, filter_text)
    if not rows:
        return messages.CONFIG_LIST_EMPTY.format(filter=filter_text)
    lines = [messages.CONFIG_LIST_HEADER]
    for row in rows:
        pad = " " * max(1, _PATH_WIDTH - len(row.path))
        lines.append(f"  {row.path}{pad}{row.value}  ({row.kind})")
    lines.append(messages.CONFIG_LIST_HINT)
    return "\n".join(lines)


def config_command(state: ReplState, argument: str) -> str:
    """`/config [key=value ...]` — Claude adları ve Fusion `bölüm.alan` yolları (#210)."""
    text = argument.strip()
    if text in ("--help", "-h"):
        return messages.CONFIG_HELP
    if "=" in text:
        return "\n".join(_set_pair(state, pair) for pair in split_pairs(text))
    if text and "." in text and " " not in text:
        try:
            return messages.CONFIG_GET.format(path=text, value=read_setting(state.config, text))
        except ConfigError as error:
            return str(error)
    return format_settings(state, text)


def split_pairs(text: str) -> list[str]:
    """Metni `key=value` çiftlerine böl; anahtar gibi görünmeyen kelime önceki değere eklenir.

    Böylece `capabilities.overrides=deploy=off, lint=on` gibi boşluklu değerler bozulmaz.
    """
    pairs: list[str] = []
    for word in text.split():
        if _PAIR_START.match(word) or not pairs:
            pairs.append(word)
        else:
            pairs[-1] = f"{pairs[-1]} {word}"
    return pairs


def _set_pair(state: ReplState, pair: str) -> str:
    """Tek `key=value` çiftini uygula; hata o çiftin satırında döner, ötekiler sürer."""
    path, sep, raw = pair.partition("=")
    path = path.strip()
    if not sep or not path:
        return messages.CONFIG_PAIR_INVALID.format(pair=pair)
    claude = claude_handler(path)
    if claude is not None:
        return claude(state, raw)
    try:
        state.config, target = write_setting(state.config, path, raw)
    except ConfigError as error:
        return str(error)
    if path.startswith("capabilities."):
        # Görünürlük/kapatma bu oturumun beceri kataloğuna hemen yansır (P-051).
        nested = state.capabilities.nested_roots if state.capabilities else ()
        state.capabilities = registry_from_config(
            state.config, state.home, state.root, extra_roots=state.extra_roots
        )
        state.capabilities.add_nested_roots(nested)
    return messages.CONFIG_SET_DONE.format(
        path=path, value=read_setting(state.config, path), file=target
    )

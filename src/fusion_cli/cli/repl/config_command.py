"""`/config` — ayarları listele, oku, değiştir (P-029).

- `/config` ya da `/config <filtre>` → erişilebilir ayarlar (yol · değer · tip).
- `/config runtime.max_tokens` → tek değer.
- `/config runtime.max_tokens=8192` → oturuma uygular VE kullanıcı dosyasına yazar
  (Claude Code `/config key=value` davranışı). Model rolleri için `/model`, `/level`.
"""

from __future__ import annotations

from ...config.settings_access import list_settings, read_setting, write_setting
from ...core.errors import ConfigError
from ...tools.capability_overrides import registry_from_config
from ...ui import messages
from .state import ReplState

#: Listede yol sütununun hizalama genişliği.
_PATH_WIDTH = 40


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
    text = argument.strip()
    if "=" in text:
        path, _, raw = text.partition("=")
        try:
            state.config, target = write_setting(state.config, path.strip(), raw)
        except ConfigError as error:
            return str(error)
        if path.strip().startswith("capabilities."):
            # Görünürlük/kapatma bu oturumun beceri kataloğuna hemen yansır (P-051).
            nested = state.capabilities.nested_roots if state.capabilities else ()
            state.capabilities = registry_from_config(
                state.config, state.home, state.root, extra_roots=state.extra_roots
            )
            state.capabilities.add_nested_roots(nested)
        return messages.CONFIG_SET_DONE.format(
            path=path.strip(), value=read_setting(state.config, path.strip()), file=target
        )
    if text and "." in text and " " not in text:
        try:
            return messages.CONFIG_GET.format(path=text, value=read_setting(state.config, text))
        except ConfigError as error:
            return str(error)
    return format_settings(state, text)

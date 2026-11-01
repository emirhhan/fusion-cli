"""`plugin install --config <key=value>` (Claude Code, #388/#381).

Claude: manifestteki `userConfig` seçeneği kurulumda `--config key=value` ile verilir (tekrar
edilebilir); değerler şemaya göre doğrulanır ve `/plugin configure` ile aynı yoldan saklanır.
`<sunucu>.<anahtar>` biçimi paketlenmiş `.mcpb` sunucularınındır; Fusion `.mcpb` yüklemez.
Biri geçersizse hiçbiri yazılmaz ve yeni kurulan eklenti geri alınır.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..config import plugin_user_config as user_config
from ..config.plugin_store import PluginRecord, plugin_folder
from ..core.plugins import PluginError

ERR_PAIR = "--config değeri anahtar=değer biçiminde olmalı: {pair!r}"
ERR_MCPB = (
    "--config {key}: '<sunucu>.<anahtar>' paketlenmiş .mcpb sunucusu içindir; "
    "Fusion .mcpb paketlerini yüklemez"
)
ERR_NO_SCHEMA = "--config verildi ama eklentinin userConfig seçeneği yok"


def parse_pairs(pairs: Sequence[str]) -> dict[str, str]:
    """`key=value` listesini sözlüğe çevir (sonraki aynı anahtar kazanır)."""
    found: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key.strip():
            raise PluginError(ERR_PAIR.format(pair=pair))
        found[key.strip()] = value
    return found


def apply_config(record: PluginRecord, pairs: Sequence[str], base: Path) -> tuple[str, ...]:
    """Doğrula ve kaydet; kaydedilen anahtarlar. Hata `PluginError` (hiçbiri yazılmaz)."""
    values = parse_pairs(pairs)
    if not values:
        return ()
    schema = user_config.read_schema(plugin_folder(record, base))
    known = {option.key for option in schema}
    for key in values:
        if "." in key and key not in known:
            raise PluginError(ERR_MCPB.format(key=key))
    if not schema:
        raise PluginError(ERR_NO_SCHEMA)
    return user_config.save_values(record.name, schema, values, base)


def missing_required(record: PluginRecord, base: Path) -> tuple[str, ...]:
    """Değeri ve varsayılanı olmayan zorunlu seçenekler (kurulum sonrası ipucu için)."""
    try:
        schema = user_config.read_schema(plugin_folder(record, base))
    except PluginError:
        return ()
    saved = user_config.saved_values(record.name, base, secrets=False)
    secret_saved: set[str] = set()
    if any(option.sensitive and option.required for option in schema):
        secret_saved = set(user_config.saved_values(record.name, base))
    return tuple(
        option.key
        for option in schema
        if option.required
        and option.default is None
        and option.key not in saved
        and option.key not in secret_saved
    )

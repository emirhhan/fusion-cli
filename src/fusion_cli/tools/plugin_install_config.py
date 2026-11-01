"""`plugin install --config <key=value>` (Claude Code, #388/#381).

Claude: manifestteki `userConfig` seçeneği kurulumda `--config key=value` ile verilir (tekrar
edilebilir); değerler şemaya göre doğrulanır ve `/plugin configure` ile aynı yoldan saklanır.
`<sunucu>.<anahtar>` biçimi paketlenmiş `.mcpb` sunucularının `user_config`'idir (#400; tek paket
bildiriyorsa çıplak anahtar da olur).
Biri geçersizse hiçbiri yazılmaz ve yeni kurulan eklenti geri alınır.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..config import plugin_user_config as user_config
from ..config.plugin_mcpb import bundle_schema, config_name, is_mcpb, is_url
from ..config.plugin_storage import storage_key
from ..config.plugin_store import PluginRecord, plugin_folder
from ..config.plugin_user_config import UserOption
from ..core.plugins import PluginError

ERR_PAIR = "--config değeri anahtar=değer biçiminde olmalı: {pair!r}"
ERR_MCPB = "--config {key}: eklentide bu adlı paketlenmiş .mcpb sunucusu yok"
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
    root = plugin_folder(record, base)
    schema = user_config.read_schema(root)
    known = {option.key for option in schema}
    bundles = _bundle_schemas(record, root)
    for key in values:
        if "." in key and key not in known and not _bundle_key(key, bundles):
            raise PluginError(ERR_MCPB.format(key=key))
    plain = {k: v for k, v in values.items() if k in known or not _bundle_key(k, bundles)}
    grouped = _bundle_values(values, plain, bundles)
    if plain and not schema:
        raise PluginError(ERR_NO_SCHEMA)
    for options, chosen in grouped.values():  # önce hepsi doğrulanır
        _check(options, chosen)
    if plain:
        _check(schema, plain)
    saved = user_config.save_values(storage_key(record), schema, plain, base) if plain else ()
    for server, (options, chosen) in grouped.items():
        name = config_name(storage_key(record), server)
        saved += tuple(
            f"{server}.{k}" for k in user_config.save_values(name, options, chosen, base)
        )
    return saved


def _check(options: tuple[UserOption, ...], chosen: dict[str, str]) -> None:
    """Kaydetmeden doğrula (biri geçersizse hiçbiri yazılmasın)."""
    by_key = {option.key: option for option in options}
    for key, text in chosen.items():
        if key not in by_key:
            raise PluginError(user_config.ERR_UNKNOWN.format(key=key))
        user_config.coerce(by_key[key], text)


def _bundle_schemas(record: PluginRecord, root: Path) -> dict[str, tuple[UserOption, ...]]:
    """Eklentinin `.mcpb` paketlerinin `user_config` şemaları (`<sunucu>.<anahtar>`, #400)."""
    from ..config.plugin_scan import scan_plugin

    try:
        layout = scan_plugin(root, record.name)
    except PluginError:
        return {}
    refs = [str(p.relative_to(root)) for p in layout.mcp_files if is_mcpb(p.name)]
    refs += [r for r in layout.manifest.mcp_servers if is_url(r) and is_mcpb(r)]
    found: dict[str, tuple[UserOption, ...]] = {}
    for ref in refs:
        try:
            server, options = bundle_schema(ref, storage_key(record), root)
        except PluginError:
            continue
        found[server] = options
    return found


def _bundle_key(key: str, bundles: dict[str, tuple[UserOption, ...]]) -> bool:
    server, sep, _option = key.partition(".")
    if sep:
        return server in bundles
    owners = [name for name, options in bundles.items() if any(o.key == key for o in options)]
    return len(owners) == 1  # çıplak anahtar: yalnız tek paket bildiriyorsa (Claude)


def _bundle_values(
    values: dict[str, str], plain: dict[str, str], bundles: dict[str, tuple[UserOption, ...]]
) -> dict[str, tuple[tuple[UserOption, ...], dict[str, str]]]:
    grouped: dict[str, tuple[tuple[UserOption, ...], dict[str, str]]] = {}
    for key, value in values.items():
        if key in plain:
            continue
        server, sep, option = key.partition(".")
        if not sep:
            server = next(n for n, opts in bundles.items() if any(o.key == key for o in opts))
            option = key
        options = bundles.get(server)
        if options is None:
            raise PluginError(ERR_MCPB.format(key=key))
        grouped.setdefault(server, (options, {}))[1][option] = value
    return grouped


def missing_required(record: PluginRecord, base: Path) -> tuple[str, ...]:
    """Değeri ve varsayılanı olmayan zorunlu seçenekler (kurulum sonrası ipucu için)."""
    try:
        schema = user_config.read_schema(plugin_folder(record, base))
    except PluginError:
        return ()
    saved = user_config.saved_values(storage_key(record), base, secrets=False)
    secret_saved: set[str] = set()
    if any(option.sensitive and option.required for option in schema):
        secret_saved = set(user_config.saved_values(storage_key(record), base))
    return tuple(
        option.key
        for option in schema
        if option.required
        and option.default is None
        and option.key not in saved
        and option.key not in secret_saved
    )

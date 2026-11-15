"""`fusion plugin configure <eklenti> [--values-stdin] [--json]` (Claude Code, #388)."""

from __future__ import annotations

import json
import sys

import typer

from ..config import plugin_user_config as user_config
from ..config.plugin_storage import storage_key
from ..config.plugin_store import load_state, plugin_folder, plugins_dir
from ..core.plugins import PluginError
from ..tools.plugin_toggle import find_record
from .plugin_commands import app

SAVED = "Yapılandırma kaydedildi. Uygulamak için Fusion'ı yeniden başlat."
FAILED = "Yapılandırma kaydedilemedi: {reason}"
NO_OPTIONS = "Bu eklentinin userConfig seçeneği yok."
ERR_STDIN = "stdin tek satırlık metinlerden oluşan bir JSON nesnesi olmalı"


def _labels(option: user_config.UserOption, saved: set[str]) -> str:
    parts = ["required" if option.required else "optional"]
    if option.sensitive:
        parts.append("sensitive")
    parts.append("set" if option.key in saved else "not set")
    return f"  {option.key}  {' · '.join(parts)}"


def _read_stdin() -> dict[str, str]:
    try:
        raw = json.loads(sys.stdin.read() or "{}")
    except ValueError as error:
        raise PluginError(ERR_STDIN) from error
    if not isinstance(raw, dict):
        raise PluginError(ERR_STDIN)
    return {str(key): value for key, value in raw.items()}


@app.command("configure")
def configure(
    plugin: str = typer.Argument(..., help="Eklenti kimliği (ad@pazar)"),
    values_stdin: bool = typer.Option(
        False, "--values-stdin", help="Değerleri stdin'den JSON nesnesi olarak oku ve kaydet."
    ),
    as_json: bool = typer.Option(False, "--json", help="Sonucu tek JSON nesnesi olarak bas."),
) -> None:
    """Eklentinin userConfig seçeneklerini göster ya da stdin'den kaydet."""
    base = plugins_dir()
    try:
        record = find_record(load_state(base), plugin)
        schema = user_config.read_schema(plugin_folder(record, base))
    except PluginError as error:
        typer.echo(str(error), err=not as_json)
        raise typer.Exit(1) from error
    if values_stdin:
        try:
            saved = user_config.save_values(storage_key(record), schema, _read_stdin(), base)
        except PluginError as error:
            typer.echo(FAILED.format(reason=error))
            if as_json:
                typer.echo(json.dumps({"refused": {"message": str(error)}}, ensure_ascii=False))
            raise typer.Exit(1) from error
        typer.echo(json.dumps({"saved": list(saved)}) if as_json else SAVED)
        return
    stored = set(user_config.saved_values(storage_key(record), base))
    if as_json:
        configured = [o.key for o in schema if o.key in stored]
        unconfigured = [o.key for o in schema if o.key not in stored]
        payload = {"configured": configured, "unconfigured": unconfigured}
        typer.echo(json.dumps(payload, ensure_ascii=False))
        return
    typer.echo("\n".join(_labels(o, stored) for o in schema) if schema else NO_OPTIONS)

"""Eklenti paketinin (P-059, P-071) üst düzey komutlarını tek çağrıyla kaydeder.

`cli/app.py`'de tek satır kalır: `register_extension_commands(app)`.
"""

from __future__ import annotations

import typer

from . import import_commands, plugin_commands


def register_extension_commands(app: typer.Typer) -> None:
    app.command(name="import")(import_commands.import_config)
    app.command(name="release-notes")(import_commands.release_notes)
    app.add_typer(plugin_commands.app, name="eklenti")
    app.add_typer(plugin_commands.app, name="plugin", hidden=True)

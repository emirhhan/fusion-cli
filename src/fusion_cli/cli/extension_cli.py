"""İçe aktarma ve sürüm notlarının (P-071) üst düzey komutlarını tek çağrıyla kaydeder.

`cli/app.py`'de tek satır kalır: `register_extension_commands(app)`.
"""

from __future__ import annotations

import typer

from . import import_commands


def register_extension_commands(app: typer.Typer) -> None:
    app.command(name="import")(import_commands.import_config)
    app.command(name="release-notes")(import_commands.release_notes)

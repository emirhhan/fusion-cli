"""`fusion mcp add-from-claude-desktop [--scope]` (Claude Code; #267).

Claude Desktop yapılandırmasını standart yerinden okur (yalnız macOS ve WSL), seçilen
sunucuları ekler. Geçersiz adlar (harf, rakam, - ve _ dışı) bildirilip atlanır; aynı ad
varsa `_1`, `_2` … eki verilir.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import typer

from ..config.loader import load_config
from ..config.mcp_entry import McpEntryError, parse_entry, valid_server_name
from ..config.models import McpScope, McpServerConfig

DESKTOP_CONFIG = "claude_desktop_config.json"


def desktop_config_path(home: Path | None = None) -> Path | None:
    base = home or Path.home()
    platform: str = sys.platform  # mypy platform daraltması WSL dalını erişilmez sanmasın
    if platform == "darwin":
        return base / "Library" / "Application Support" / "Claude" / DESKTOP_CONFIG
    return _wsl_config_path(platform)


def _wsl_config_path(platform: str) -> Path | None:
    if platform.startswith("linux") and os.environ.get("WSL_DISTRO_NAME"):
        user = os.environ.get("USER", "")
        return Path("/mnt/c/Users") / user / "AppData" / "Roaming" / "Claude" / DESKTOP_CONFIG
    return None


def unique_name(name: str, taken: set[str]) -> str:
    if name not in taken:
        return name
    index = 1
    while f"{name}_{index}" in taken:
        index += 1
    return f"{name}_{index}"


def importable(
    raw: object, taken: set[str], scope: McpScope
) -> tuple[list[McpServerConfig], list[str]]:
    """(eklenebilir kayıtlar, bildirilecek atlamalar)."""
    entries = raw.get("mcpServers", {}) if isinstance(raw, dict) else {}
    servers: list[McpServerConfig] = []
    skipped: list[str] = []
    names = set(taken)
    for name, entry in entries.items() if isinstance(entries, dict) else ():
        if not valid_server_name(str(name)):
            skipped.append(f"{name}: ad yalnız harf, rakam, - ve _ içerebilir; atlandı")
            continue
        try:
            server = parse_entry(str(name), entry, scope=scope, where="claude_desktop_config")
        except McpEntryError as error:
            skipped.append(str(error))
            continue
        final = unique_name(str(name), names)
        names.add(final)
        servers.append(replace(server, name=final))
    return servers, skipped


def add_from_claude_desktop(scope: str) -> None:
    from .mcp_commands import _announce_saved, _parse_scope, _save_or_exit, console

    path = desktop_config_path()
    if path is None:
        raise typer.BadParameter("Bu komut yalnız macOS ve WSL'de çalışır.")
    if not path.is_file():
        console.print(f"Claude Desktop yapılandırması bulunamadı: {path}")
        raise typer.Exit(code=1)
    target_scope = _parse_scope(scope)
    config = load_config()
    raw = json.loads(path.read_text(encoding="utf-8"))
    servers, skipped = importable(raw, {s.name for s in config.mcp_servers}, target_scope)
    for line in skipped:
        console.print(f"Atlandı: {line}")
    if not servers:
        console.print("İçe aktarılacak sunucu yok.")
        return
    for index, server in enumerate(servers, 1):
        console.print(f"  {index}. {server.name}")
    answer = typer.prompt("Hangileri içe aktarılsın? (ör. 1,3; boş = hepsi)", default="")
    chosen = _selection(answer, len(servers))
    for index in chosen:
        server = servers[index]
        saved, replaced = _save_or_exit(config, server)
        _announce_saved(server, saved, replaced)
        config = load_config()


def _selection(answer: str, count: int) -> list[int]:
    text = answer.strip()
    if not text:
        return list(range(count))
    picked = [int(part) - 1 for part in text.replace(" ", "").split(",") if part.isdigit()]
    return [index for index in dict.fromkeys(picked) if 0 <= index < count]

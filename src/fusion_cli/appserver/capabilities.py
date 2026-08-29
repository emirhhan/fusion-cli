"""Native uygulama için güvenli beceri, ajan, talimat ve MCP kataloğu."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config.models import Config
from ..engines.agent.project_instructions import CANDIDATE_FILENAMES
from ..tools.capabilities import (
    Capability,
    CapabilityRegistry,
    load_agent_prompt,
    load_skill_text,
    map_tools,
)

_DETAIL_BUDGET = 12_000
_PERMISSION_LABELS = {
    "read_file": "dosya okuma",
    "view_file": "dosya okuma",
    "write_file": "dosya düzenleme",
    "edit_file": "dosya düzenleme",
    "multi_edit": "dosya düzenleme",
    "grep_search": "dosya arama",
    "search_code": "dosya arama",
    "glob": "dosya arama",
    "list_dir": "dosya okuma",
    "run_shell": "komut çalıştırma",
    "web_search": "ağ erişimi",
    "web_fetch": "ağ erişimi",
    "read_url_content": "ağ erişimi",
    "spawn_agent": "alt ajan",
}


def _permissions(item: Capability) -> list[str]:
    mapped = map_tools(item.tools)
    if mapped is None:
        return ["standart Fusion onayları"]
    labels = {_PERMISSION_LABELS[name] for name in mapped if name in _PERMISSION_LABELS}
    order = (
        "dosya okuma",
        "dosya arama",
        "dosya düzenleme",
        "komut çalıştırma",
        "ağ erişimi",
        "alt ajan",
    )
    return [label for label in order if label in labels]


def _item(item: Capability, *, enabled: bool, kind: str) -> dict[str, Any]:
    return {
        "ad": item.name,
        "aciklama": item.description,
        "kaynak": item.source,
        "tur": kind,
        "etkin": enabled,
        "izinler": _permissions(item),
    }


def catalog(
    registry: CapabilityRegistry,
    config: Config,
    root: Path,
    *,
    disabled_skills: set[str],
    disabled_agents: set[str],
    disabled_mcp: set[str],
) -> dict[str, Any]:
    instructions = [
        {"ad": name, "kaynak": "proje", "etkin": True}
        for name in CANDIDATE_FILENAMES
        if (root / name).is_file()
    ]
    return {
        "ok": True,
        "beceriler": [
            _item(item, enabled=item.name not in disabled_skills, kind="beceri")
            for item in registry.skills()
        ],
        "ajanlar": [
            _item(item, enabled=item.name not in disabled_agents, kind="ajan")
            for item in registry.agents()
        ],
        "talimatlar": instructions,
        "mcp": [
            {
                "ad": server.name,
                "aciklama": f"{server.command} ile çalışan MCP sunucusu",
                "kaynak": "fusion",
                "tur": "mcp",
                "etkin": server.name not in disabled_mcp,
                "izinler": ["yerel komut", "dış araçlar"],
            }
            for server in config.mcp_servers
        ],
    }


def detail(
    registry: CapabilityRegistry,
    config: Config,
    root: Path,
    data: dict[str, Any],
) -> dict[str, Any]:
    kind, name = str(data.get("tur", "")), str(data.get("ad", ""))
    if kind == "beceri":
        item = registry.get_skill(name)
        content = load_skill_text(item.path, budget=_DETAIL_BUDGET) if item else ""
    elif kind == "ajan":
        item = registry.get_agent(name)
        content = load_agent_prompt(item.path)[:_DETAIL_BUDGET] if item else ""
    elif kind == "talimat" and name in CANDIDATE_FILENAMES:
        item = None
        path = root / name
        try:
            content = path.read_text(encoding="utf-8")[:_DETAIL_BUDGET] if path.is_file() else ""
        except OSError:
            content = ""
    elif kind == "mcp":
        item = None
        server = next((entry for entry in config.mcp_servers if entry.name == name), None)
        content = f"Komut: {server.command}\nArgümanlar: {' '.join(server.args)}" if server else ""
    else:
        return {"ok": False, "metin": "Katalog öğesi bulunamadı."}
    if not content:
        return {"ok": False, "metin": "Katalog öğesi bulunamadı."}
    return {
        "ok": True,
        "tur": kind,
        "ad": name,
        "icerik": content,
        "kesildi": len(content) >= _DETAIL_BUDGET,
    }

"""Native uygulama için güvenli beceri, ajan, talimat ve MCP kataloğu."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config.models import Config
from ..core.redaction import redact
from ..engines.agent.instruction_layers import load_instruction_layers
from ..engines.agent.instruction_rules import discover_rules
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
    "spawn_agents": "alt ajan",
    "site_crawl": "ağ erişimi",
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
        "kimlik": item.qualified_name,
        "surum": item.revision,
        "aciklama": item.description,
        "kaynak": item.source,
        "tur": kind,
        "etkin": enabled,
        "izinler": _permissions(item),
    }


def instruction_entries(root: Path, home: Path | None) -> dict[str, tuple[Path, str, str]]:
    """Katalogdaki talimat öğeleri: ad → (yol, kaynak, açıklama).

    Tur başında yüklenen katmanlar (kullanıcı + proje, `@import` dahil) ve `.claude/rules`
    kuralları (P-015/P-016). `detail` yalnız bu listedeki yolu okur; serbest yol kabul etmez.
    """
    entries: dict[str, tuple[Path, str, str]] = {}
    for item in load_instruction_layers(root, home).files:
        kaynak = "kullanici" if item.trusted else "proje"
        aciklama = {
            "kullanici": "Genel talimat; her projede tur başında yüklenir",
            "proje": "Proje talimatı; tur başında yüklenir",
            "import": "@import ile alınan dosya",
            "baglanti": "Talimatın işaret ettiği kural dosyası",
        }.get(item.layer, "")
        entries.setdefault(item.label, (item.path, kaynak, aciklama))
    for rule in discover_rules(root, home):
        kaynak = "kullanici" if rule.trusted else "proje"
        aciklama = (
            f"Kural; yalnız şu dosyalara dokununca: {', '.join(rule.paths)}"
            if rule.is_scoped
            else "Kural; tur başında yüklenir"
        )
        entries.setdefault(rule.label, (rule.path, kaynak, aciklama))
    return entries


def catalog(
    registry: CapabilityRegistry,
    config: Config,
    root: Path,
    *,
    disabled_skills: set[str],
    disabled_agents: set[str],
    disabled_mcp: set[str],
    home: Path | None = None,
) -> dict[str, Any]:
    instructions = [
        {"ad": name, "kaynak": kaynak, "etkin": True, "aciklama": aciklama}
        for name, (_path, kaynak, aciklama) in instruction_entries(root, home).items()
    ]
    return {
        "ok": True,
        "beceriler": [
            _item(
                item,
                enabled=item.name not in disabled_skills
                and item.qualified_name not in disabled_skills,
                kind="beceri",
            )
            for item in registry.skills()
        ],
        "ajanlar": [
            _item(
                item,
                enabled=item.name not in disabled_agents
                and item.qualified_name not in disabled_agents,
                kind="ajan",
            )
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
    *,
    home: Path | None = None,
) -> dict[str, Any]:
    kind, name = str(data.get("tur", "")), str(data.get("ad", ""))
    if kind == "beceri":
        item = registry.get_skill(name)
        content = load_skill_text(item.path, budget=_DETAIL_BUDGET) if item else ""
    elif kind == "ajan":
        item = registry.get_agent(name)
        content = load_agent_prompt(item.path)[:_DETAIL_BUDGET] if item else ""
    elif kind == "talimat" and name in (entries := instruction_entries(root, home)):
        item = None
        path = entries[name][0]
        try:
            content = path.read_text(encoding="utf-8")[:_DETAIL_BUDGET] if path.is_file() else ""
        except OSError:
            content = ""
    elif kind == "mcp":
        item = None
        server = next((entry for entry in config.mcp_servers if entry.name == name), None)
        # Argümana gömülmüş anahtar (`--api-key=…`, URL'de token) arayüze sızmasın.
        content = (
            f"Komut: {server.command}\nArgümanlar: {redact(' '.join(server.args))}"
            if server
            else ""
        )
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

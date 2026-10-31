"""Native uygulama için güvenli beceri, ajan, talimat ve MCP kataloğu."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config.models import Config, SkillVisibility
from ..core.redaction import redact
from ..engines.agent.instruction_layers import load_instruction_layers
from ..engines.agent.instruction_rules import discover_rules
from ..memory.plain_memory import PlainMemoryError, open_agent_memory
from ..tools.capabilities import (
    Capability,
    CapabilityRegistry,
    load_agent_prompt,
    load_skill_text,
    map_tools,
)
from ..tools.capability_overrides import overrides_from, visibility_of

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


def _settings(item: Capability) -> dict[str, Any]:
    """Alt ajan tanımının ayarları (P-034); boş alan gönderilmez."""
    raw: dict[str, Any] = {
        "model": item.model,
        "izin_kipi": item.permission_mode,
        "en_fazla_tur": item.max_turns,
        "beceriler": list(item.skills),
        "mcp": list(item.mcp_servers),
        "bellek": item.memory,
        "efor": item.effort,
        "arka_plan": item.background,
        "yalitim": item.isolation,
        "kancalar": list(item.hooks),
        "yasak_araclar": list(item.disallowed_tools),
        "baglam": item.context,
    }
    return {key: value for key, value in raw.items() if value}


#: `capabilities.overrides` görünürlüğünün arayüz metni (P-051); `on` gösterilmez.
_VISIBILITY_LABELS = {
    SkillVisibility.NAME_ONLY: "dizinde yalnız ad",
    SkillVisibility.USER_INVOCABLE_ONLY: "yalnız /ad ile (model yüklemez)",
    SkillVisibility.OFF: "kapalı (capabilities.overrides)",
}


def _item(
    item: Capability, *, enabled: bool, kind: str, visibility: SkillVisibility = SkillVisibility.ON
) -> dict[str, Any]:
    settings = _settings(item)
    if visibility in _VISIBILITY_LABELS:
        settings["gorunurluk"] = _VISIBILITY_LABELS[visibility]
    return {
        "ad": item.name,
        "kimlik": item.qualified_name,
        "surum": item.revision,
        "aciklama": item.description,
        "kaynak": item.source,
        "tur": kind,
        "etkin": enabled and visibility is not SkillVisibility.OFF,
        "izinler": _permissions(item),
        "ayarlar": settings,
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
    overrides = overrides_from(config)
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
                visibility=visibility_of(item, overrides),
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
    payload: dict[str, Any] = {
        "ok": True,
        "tur": kind,
        "ad": name,
        "icerik": content,
        "kesildi": len(content) >= _DETAIL_BUDGET,
    }
    if kind == "ajan" and item is not None and item.memory:
        payload["bellek"] = agent_memory_view(item, config, root)
    return payload


def agent_memory_view(item: Capability, config: Config, root: Path) -> dict[str, Any] | None:
    """Ajanın kalıcı belleği (P-055): kapsam, dizin, satır sayısı, konular ve indeks metni."""
    memory = open_agent_memory(config, root, item.name, item.memory)
    if memory is None:
        return None
    status = memory.status()
    return {
        "kapsam": item.memory,
        "dizin": str(memory.directory),
        "dosya": str(memory.index_path),
        "satir": status.index_lines,
        "konular": list(status.topics),
        "metin": redact(memory.read()),
    }


def clear_agent_memory(
    registry: CapabilityRegistry, config: Config, root: Path, data: dict[str, Any]
) -> dict[str, Any]:
    """`yetenek.bellek_sil {ad}`: ajanın bellek dizinini sil; yoksa `silindi: false`."""
    item = registry.get_agent(str(data.get("ad", "")))
    if item is None or not item.memory:
        return {"ok": False, "metin": "Bu ajanın kalıcı belleği yok."}
    memory = open_agent_memory(config, root, item.name, item.memory)
    if memory is None:
        return {"ok": False, "metin": "Bu ajanın kalıcı belleği yok."}
    try:
        cleared = memory.clear()
    except PlainMemoryError as error:
        return {"ok": False, "metin": str(error)}
    return {"ok": True, "ad": item.name, "silindi": cleared}

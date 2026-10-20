"""Skill ve agent kütüphanesi keşfi.

Claude Code ekosisteminde uzman talimatlar `SKILL.md` dosyalarında, uzman ajanlar
`.claude/agents/*.md` dosyalarında tutulur. Fusion bunları bulur, arar ve kullanır —
kendi ekosistemini kurmak yerine var olanı okur.

İki tasarım kararı:

- **Frontmatter elle ayrıştırılır.** İhtiyaç duyulan alan üçtür (`name`, `description`,
  `tools`); tam bir YAML ayrıştırıcı bağımlılığı bunun için gereksizdir ve bozuk
  frontmatter'ın tüm keşfi düşürmesini istemeyiz.
- **Liste modele BASILMAZ.** Kütüphane yüzlerce girdi içerebilir; hepsini prompta
  koymak bağlamı boşa harcar. Model `find_skill`/`find_agent` ile ARAR.

Tarama oturumda bir kez yapılır ve önbelleklenir.
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ..config.paths import bundled_roster_dir, bundled_skills_dir, capabilities_dir
from .capability_merge import merge_capability as _merge
from .capability_search import search as search
from .capability_search import search_scored as search_scored
from .skill_pages import (
    SKILL_TEXT_BUDGET as SKILL_TEXT_BUDGET,
)
from .skill_pages import (
    load_skill_page as load_skill_page,
)
from .skill_pages import (
    load_skill_text as load_skill_text,
)
from .skill_pages import (
    skill_file as skill_file,
)
from .skill_pages import (
    skill_files as skill_files,
)

#: Claude araç adları → Fusion araç adları. Bir agent kısıtlı araç seti bildirdiğinde
#: bu eşleme kullanılır; bilinmeyen ad sessizce yok sayılır.
CLAUDE_TOOL_MAP: dict[str, frozenset[str]] = {
    "read": frozenset({"read_file", "view_file"}),
    "write": frozenset({"write_file"}),
    "edit": frozenset({"edit_file", "multi_edit"}),
    "grep": frozenset({"grep_search", "search_code"}),
    "glob": frozenset({"glob"}),
    "bash": frozenset({"run_shell"}),
    "websearch": frozenset({"web_search"}),
    "webfetch": frozenset({"web_fetch", "read_url_content"}),
    "ls": frozenset({"list_dir"}),
    "task": frozenset({"spawn_agent"}),
}

#: Kişilik alanları: frontmatter anahtarı → `Capability` alanı. Türkçe ve İngilizce
#: yazım ikisi de kabul edilir; kullanıcı kendi ajanını hangisiyle yazarsa.
_PERSONA_KEYS: dict[str, str] = {
    "unvan": "title",
    "title": "title",
    "avatar": "avatar",
    "renk": "color",
    "color": "color",
}

#: Bir skill talimatından modele verilecek en fazla karakter.
#: Frontmatter ararken dosyanın başından okunacak karakter.
_HEAD_CHARS = 4_000


@dataclass(frozen=True, slots=True)
class Capability:
    """Bulunan bir skill ya da agent."""

    name: str
    description: str
    path: Path
    #: Nereden geldiği: claude | claude-plugin | proje | codex | hermes.
    #: Aynı ad birden çok kaynakta varsa etiketler birleşir: "claude+codex".
    source: str
    #: Agent'lar için bildirilen Claude araç adları. Boş ya da ("*",) → tam yetki.
    tools: tuple[str, ...] = ()
    #: Kişilik: arayüzde ajan kartında görünen ünvan, avatar kimliği ve renk adı.
    #: Claude/Codex agent biçiminde olmayan alanlardır; o araçlar yok sayar.
    #: Boşsa arayüz addan türetilmiş bir varsayılan gösterir.
    title: str = ""
    avatar: str = ""
    color: str = ""

    @property
    def qualified_name(self) -> str:
        """İçerik değişse de aynı kaynağı seçen kararlı katalog kimliği."""
        identity = hashlib.sha256(str(self.path.resolve()).encode()).hexdigest()[:12]
        return f"{self.name}@{self.source}:{identity}"

    @property
    def revision(self) -> str:
        """Gösterilen/yüklenen içeriğin sürümü; okunamıyorsa bilinmiyor."""
        try:
            return hashlib.sha256(self.path.read_bytes()).hexdigest()
        except OSError:
            return ""


def parse_frontmatter(text: str) -> dict[str, object]:
    """`---` blokları arasındaki `name`, `description` ve `tools` alanlarını oku.

    Basit bir YAML alt kümesidir; frontmatter yoksa ya da bozuksa boş sözlük döner
    (keşif tek bir bozuk dosya yüzünden düşmemelidir).
    """
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return {}
    end = stripped.find("\n---", 3)
    if end == -1:
        return {}

    fields: dict[str, object] = {}
    for line in stripped[3:end].splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        name = key.strip().lower()
        if name == "tools":
            fields["tools"] = _parse_tools(value.strip())
        elif name in ("name", "description"):
            fields[name] = value.strip().strip("'\"")
        elif name in _PERSONA_KEYS:
            fields[_PERSONA_KEYS[name]] = value.strip().strip("'\"")
    return fields


def map_tools(claude_tools: tuple[str, ...]) -> set[str] | None:
    """Claude araç adlarını Fusion adlarına çevir. `*` ya da boş → None (tam set)."""
    if not claude_tools or claude_tools == ("*",):
        return None
    allowed: set[str] = set()
    for name in claude_tools:
        allowed |= CLAUDE_TOOL_MAP.get(name.strip().lower(), frozenset())
    return allowed


def load_agent_prompt(path: Path) -> str:
    """Agent tanımının gövdesi (frontmatter sonrası)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"HATA: agent okunamadı: {exc}"
    if path.suffix.lower() == ".toml":
        try:
            data: object = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return ""
        if not isinstance(data, dict):
            return ""
        instructions = data.get("developer_instructions")
        return instructions if isinstance(instructions, str) else ""
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return text
    end = stripped.find("\n---", 3)
    return text if end == -1 else stripped[end + 4 :].lstrip()


class CapabilityRegistry:
    """Skill ve agent keşfi. Tarama oturumda bir kez yapılır."""

    def __init__(
        self,
        home: Path,
        root: Path,
        *,
        disabled_skills: frozenset[str] = frozenset(),
        disabled_agents: frozenset[str] = frozenset(),
    ) -> None:
        self._home = home
        self._root = root
        self._disabled_skills = disabled_skills
        self._disabled_agents = disabled_agents
        self._skills: tuple[Capability, ...] | None = None
        self._agents: tuple[Capability, ...] | None = None

    def skills(self) -> tuple[Capability, ...]:
        if self._skills is None:
            self._skills = tuple(
                item
                for item in self._discover_skills()
                if item.name not in self._disabled_skills
                and item.qualified_name not in self._disabled_skills
            )
        return self._skills

    def agents(self) -> tuple[Capability, ...]:
        if self._agents is None:
            self._agents = tuple(
                item
                for item in self._discover_agents()
                if item.name not in self._disabled_agents
                and item.qualified_name not in self._disabled_agents
            )
        return self._agents

    def get_skill(self, name: str) -> Capability | None:
        return _select(self.skills(), name)

    def get_agent(self, name: str) -> Capability | None:
        return _select(self.agents(), name, bundled_override=True)

    # ----------------------------------------------------------------------- #

    def _skill_roots(self) -> tuple[tuple[Path, str], ...]:
        # Sıra ÖNCELİKTİR: aynı adlı skill'de ilk bulunan kazanır (bkz. _discover_skills).
        # Claude önce gelir çünkü kullanıcının birincil kütüphanesi odur; Codex ve
        # Hermes aynı SKILL.md biçimini kullandığı için ayrıştırıcı değişmez.
        return (
            (self._home / ".claude" / "skills", "claude"),
            (self._home / ".claude" / "plugins", "claude-plugin"),
            (self._root / ".claude" / "skills", "proje"),
            (self._root / ".fusion" / "skills", "proje"),
            (self._home / ".codex" / "skills", "codex"),
            (self._home / ".hermes" / "skills", "hermes"),
            # `fusion yetenek kur` ile kurulan repolar (ör. stickman-video-director).
            (capabilities_dir(), "kurulu"),
            # Yerleşik beceriler EN SONDA: kullanıcı aynı adla kendi becerisini yazarsa o kazanır.
            (bundled_skills_dir(), "fusion"),
        )

    def _agent_roots(self) -> tuple[tuple[Path, str], ...]:
        return (
            (self._home / ".claude" / "agents", "claude"),
            (self._root / ".claude" / "agents", "proje"),
            (self._home / ".codex" / "agents", "codex"),
            *((folder / "agents", "kurulu") for folder in _installed_folders()),
            # Yerleşik ekip EN SONDA: kullanıcı aynı adla kendi ajanını yazarsa o kazanır.
            (bundled_roster_dir(), "fusion"),
        )

    def _discover_skills(self) -> tuple[Capability, ...]:
        found: dict[str, Capability] = {}
        for root, source in self._skill_roots():
            if not root.exists():
                continue
            for path in sorted(root.rglob("SKILL.md")):
                capability = _to_capability(path, source, fallback=path.parent.name)
                # İlk bulunan İÇERİĞİ verir: tüm Claude/proje kökleri dış kaynaklardan
                # önce gelir. Sonrakiler yalnız kaynak etiketine eklenir.
                _merge(found, capability)
        return tuple(found.values())

    def _discover_agents(self) -> tuple[Capability, ...]:
        found: dict[str, Capability] = {}
        for root, source in self._agent_roots():
            if not root.exists():
                continue
            for path in sorted(root.glob("*.md")):
                capability = _to_capability(path, source, fallback=path.stem)
                _merge(found, capability)
            # Codex agent'ları TOML tutar; aynı kökte iki biçim yan yana olabilir.
            for path in sorted(root.glob("*.toml")):
                toml_capability = _toml_capability(path, source)
                if toml_capability is not None:
                    _merge(found, toml_capability)
        return tuple(found.values())


def _installed_folders() -> tuple[Path, ...]:
    root = capabilities_dir()
    if not root.is_dir():
        return ()
    return tuple(sorted(child for child in root.iterdir() if child.is_dir()))


def _toml_capability(path: Path, source: str) -> Capability | None:
    """Codex biçimi TOML agent'ını `Capability`'ye çevir. Bozuksa `None`.

    Codex agent'ları markdown değil TOML tutar: `name`, `description` ve
    `developer_instructions` alanları vardır. Ayrıştırma başarısız olursa o dosya
    atlanır — tek bir bozuk agent tüm keşfi düşürmemelidir.
    """
    try:
        data: object = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return Capability(
        name=str(data.get("name") or path.stem),
        description=str(data.get("description") or ""),
        path=path,
        source=source,
        tools=(),
    )


def _to_capability(path: Path, source: str, *, fallback: str) -> Capability:
    fields = parse_frontmatter(_read_head(path))
    tools = fields.get("tools")
    return Capability(
        name=str(fields.get("name") or fallback),
        description=str(fields.get("description") or ""),
        path=path,
        source=source,
        tools=tuple(tools) if isinstance(tools, tuple) else (),
        title=str(fields.get("title") or ""),
        avatar=str(fields.get("avatar") or ""),
        color=str(fields.get("color") or ""),
    )


def _read_head(path: Path, limit: int = _HEAD_CHARS) -> str:
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except OSError:
        return ""


def _parse_tools(value: str) -> tuple[str, ...]:
    """`tools:` alanını oku: `[a, b]`, `a, b` ya da `'*'` biçimlerini destekler."""
    if value in ("'*'", '"*"', "*"):
        return ("*",)
    inner = value[1:-1] if value.startswith("[") and value.endswith("]") else value
    return tuple(item.strip().strip("'\"") for item in inner.split(",") if item.strip())


def _select(
    items: tuple[Capability, ...], name: str, *, bundled_override: bool = False
) -> Capability | None:
    exact = next((item for item in items if item.qualified_name == name), None)
    if exact is not None:
        return exact
    matches = [item for item in items if item.name == name]
    if bundled_override and len(matches) > 1:
        # Yerleşik ajan için kullanıcının açık override sözleşmesini koru.
        matches = [item for item in matches if item.source != "fusion"]
    return matches[0] if len(matches) == 1 else None

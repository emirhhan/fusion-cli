"""Skill ve agent kütüphanesi keşfi.

Claude Code ekosisteminde uzman talimatlar `SKILL.md` dosyalarında, uzman ajanlar
`.claude/agents/*.md` dosyalarında tutulur. Fusion bunları bulur, arar ve kullanır —
kendi ekosistemini kurmak yerine var olanı okur.

İki tasarım kararı:

- **Frontmatter elle ayrıştırılır.** İhtiyaç duyulan alan üçtür (`name`, `description`,
  `tools`); tam bir YAML ayrıştırıcı bağımlılığı bunun için gereksizdir ve bozuk
  frontmatter'ın tüm keşfi düşürmesini istemeyiz.
- **Gövde modele BASILMAZ, dizin basılır.** Kütüphane yüzlerce girdi içerebilir; gövdeleri
  prompta koymak bağlamı boşa harcar. Kök turda yalnız `ad — açıklama` dizini bütçeli girer
  (`engines/agent/skill_index.py`, P-018); model gövdeyi `read_skill` ile, listede olmayanı
  `find_skill` ile alır.

Tarama oturumda bir kez yapılır ve önbelleklenir.
"""

from __future__ import annotations

import functools
import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ..config.paths import bundled_roster_dir, bundled_skills_dir, capabilities_dir
from .capability_merge import merge_capability as _merge
from .capability_search import search as search
from .capability_search import search_scored as search_scored
from .frontmatter import NO_TOOLS as NO_TOOLS
from .frontmatter import parse_frontmatter as parse_frontmatter
from .frontmatter import parse_tools as _parse_tools
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

#: Codex `sandbox_mode = "read-only"` ajanının Fusion karşılığı olan salt-okur araç seti.
_READ_ONLY_TOOLS: tuple[str, ...] = ("Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch")

#: Üçüncü tarafın doldurduğu kökler: oradaki sembolik bağ kök DIŞINA (`~/.ssh/id_rsa`)
#: çıkıyorsa içerik sızdırma yolu olur (T1-15). Kullanıcının kendi kökleri (`~/.claude`,
#: proje) dotfile yöneticilerinin bağlarını kullanabilir ve denetlenmez.
_UNTRUSTED_SOURCES = frozenset({"kurulu", "claude-plugin"})

#: Frontmatter ararken dosyanın başından okunacak karakter. 4000 iken uzun açıklamalı
#: skill'lerde bitiş işareti görülmüyor, `{}` dönüp ad dizin adına düşüyordu (ölçüldü, 30 Ekim).
_HEAD_CHARS = 16_000


@functools.lru_cache(maxsize=4096)
def _path_identity(path: str) -> str:
    """Yolun kararlı kısa özeti; `resolve()`+SHA-256 her filtre/seçimde tekrarlanmasın."""
    return hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()[:12]


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
    #: "beceri" (SKILL.md) | "komut" (`.claude/commands/x.md` tek dosya; gövde görevdir).
    kind: str = "beceri"
    #: Skill frontmatter alanları (P-020). `allowed_tools` Claude araç adlarıdır; boş = kısıt yok.
    allowed_tools: tuple[str, ...] = ()
    model: str = ""
    effort: str = ""
    #: `context: fork` → alt ajanda çalıştır.
    context: str = ""
    #: `disable-model-invocation: true` → beceri dizinine ve find_skill sonucuna girmez;
    #: yalnız kullanıcı `/ad` ile çağırır.
    model_invocable: bool = True
    #: `user-invocable: false` → slash komutu olarak sunulmaz (yalnız model yükler).
    user_invocable: bool = True
    #: `argument-hint` → yardım ve tamamlamada gösterilen argüman biçimi.
    argument_hint: str = ""

    @property
    def qualified_name(self) -> str:
        """İçerik değişse de aynı kaynağı seçen kararlı katalog kimliği."""
        return f"{self.name}@{self.source}:{_path_identity(str(self.path))}"

    @property
    def revision(self) -> str:
        """Gösterilen/yüklenen içeriğin sürümü; okunamıyorsa bilinmiyor."""
        try:
            return hashlib.sha256(self.path.read_bytes()).hexdigest()
        except OSError:
            return ""


def map_tools(claude_tools: tuple[str, ...]) -> set[str] | None:
    """Claude araç adlarını Fusion adlarına çevir. `*` ya da boş → None (tam set)."""
    if claude_tools == NO_TOOLS:
        return set()
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

    def candidates(self, name: str) -> tuple[str, ...]:
        """Bu ada sahip skill'lerin nitelikli adları (`ad@kaynak:kimlik`).

        `get_skill(ad)` farklı içerikli birden çok kaynakta None döner (kaynak seçimi
        bilinçlidir); çağıran modele "yok" demek yerine bu adayları sunabilir.
        """
        return tuple(item.qualified_name for item in self.skills() if item.name == name)

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
                if not _trusted_path(path, root, source):
                    continue
                capability = _to_capability(path, source, fallback=path.parent.name)
                # İlk bulunan İÇERİĞİ verir: tüm Claude/proje kökleri dış kaynaklardan
                # önce gelir. Sonrakiler yalnız kaynak etiketine eklenir.
                _merge(found, capability)
        # `.claude/commands/*.md` tek dosyalı komutlar da `/ad` ile çağrılır; aynı adlı
        # SKILL.md kazanır (Claude Code'da ikisi aynı komutu üretir).
        from .skill_commands import discover_commands

        for command in discover_commands(self._home, self._root):
            if isinstance(command, Capability) and command.name not in found:
                found[command.name] = command
        return tuple(found.values())

    def _discover_agents(self) -> tuple[Capability, ...]:
        found: dict[str, Capability] = {}
        for root, source in self._agent_roots():
            if not root.exists():
                continue
            # Kurulu repoda `agents/` klasörünün kendisi de bağ olabilir: sınır repo kökü.
            bound = root.parent if source == "kurulu" else root
            for path in sorted(root.glob("*.md")):
                if not _trusted_path(path, bound, source):
                    continue
                capability = _to_capability(path, source, fallback=path.stem)
                _merge(found, capability)
            # Codex agent'ları TOML tutar; aynı kökte iki biçim yan yana olabilir.
            for path in sorted(root.glob("*.toml")):
                if not _trusted_path(path, bound, source):
                    continue
                toml_capability = _toml_capability(path, source)
                if toml_capability is not None:
                    _merge(found, toml_capability)
        return tuple(found.values())


def _trusted_path(path: Path, bound: Path, source: str) -> bool:
    """Üçüncü taraf kökündeki dosya, `bound` dışına çıkan bir sembolik bağ DEĞİL mi?"""
    if source not in _UNTRUSTED_SOURCES or not path.is_symlink():
        return True
    try:
        return path.resolve().is_relative_to(bound.resolve())
    except OSError:
        return False


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
        tools=_toml_tools(data),
    )


def _toml_tools(data: dict[str, object]) -> tuple[str, ...]:
    """TOML ajanının araç kısıtı: `tools` listesi, yoksa `sandbox_mode = "read-only"`.

    Eskiden hiç okunmuyordu: Codex'te salt-okur tanımlı ajan Fusion'da tam yetkiliydi.
    """
    tools = data.get("tools")
    if isinstance(tools, list):
        return tuple(str(item).strip() for item in tools if str(item).strip()) or NO_TOOLS
    if isinstance(tools, str):
        return _parse_tools(tools.strip()) or NO_TOOLS
    return _READ_ONLY_TOOLS if data.get("sandbox_mode") == "read-only" else ()


def _to_capability(path: Path, source: str, *, fallback: str) -> Capability:
    fields = parse_frontmatter(_read_head(path))
    tools = fields.get("tools")
    allowed = fields.get("allowed_tools")
    description = str(fields.get("description") or "")
    when = str(fields.get("when_to_use") or "")
    if when:  # Claude Code `when_to_use` açıklamanın devamıdır; arama ve dizin ikisini görür
        description = f"{description} {when}".strip()
    return Capability(
        name=str(fields.get("name") or fallback),
        description=description,
        path=path,
        source=source,
        tools=tuple(tools) if isinstance(tools, tuple) else (),
        title=str(fields.get("title") or ""),
        avatar=str(fields.get("avatar") or ""),
        color=str(fields.get("color") or ""),
        allowed_tools=tuple(allowed) if isinstance(allowed, tuple) and allowed != NO_TOOLS else (),
        model=str(fields.get("model") or ""),
        effort=str(fields.get("effort") or ""),
        context=str(fields.get("context") or ""),
        model_invocable=bool(fields.get("model_invocable", True)),
        user_invocable=bool(fields.get("user_invocable", True)),
        argument_hint=str(fields.get("argument_hint") or ""),
    )


def _read_head(path: Path, limit: int = _HEAD_CHARS) -> str:
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except OSError:
        return ""


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

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
import logging
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..config.models import McpServerConfig, SkillVisibility
from ..config.paths import bundled_roster_dir, bundled_skills_dir, capabilities_dir
from ..config.plugin_store import state_signature
from ..core.hooks.events import HookSet
from ..core.mcp_tool_names import canonical_mcp_name, split_mcp_tool_name
from ..core.memory import RoutineSpec
from ..core.proposal_invocation import (
    ProposalInvocation,
    ProposalPolicy,
    proposal_metadata,
    visible_proposal,
)
from .agent_catalog_metadata import apply_agent_metadata, bind_agent_source
from .agent_colors import normalize_agent_color
from .agent_file_rules import agent_file_problem, log_skipped
from .bundled_plugins import legacy_team_agent
from .capability_merge import merge_capability as _merge
from .capability_merge import shadow_agent
from .capability_overrides import apply_overrides
from .capability_roots import agent_roots, ancestor_skill_dirs, roots_signature, skill_roots
from .capability_search import search as search
from .capability_search import search_scored as search_scored
from .frontmatter import NO_TOOLS as NO_TOOLS
from .frontmatter import body_after_frontmatter
from .frontmatter import parse_frontmatter as parse_frontmatter
from .frontmatter import parse_tools as _parse_tools
from .plugin_capabilities import (
    PLUGIN_SOURCE,
    plugin_agents,
    plugin_commands,
    plugin_skills,
    with_plugin_root,
)
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
    "task": frozenset(
        {"Agent", "spawn_agent", "spawn_agents", "find_agent", "invoke_agent", "invoke_subagent"}
    ),
    # Claude Code'un yeni adları (P-034): alt ajan, beceri, soru, defter, görev listesi.
    "agent": frozenset(
        {"Agent", "spawn_agent", "spawn_agents", "find_agent", "invoke_agent", "invoke_subagent"}
    ),
    "sendmessage": frozenset({"SendMessage", "send_message"}),
    "listagents": frozenset({"ListAgents", "list_agents"}),
    "taskstop": frozenset({"TaskStop", "stop_agent"}),
    "skill": frozenset({"Skill", "find_skill", "read_skill"}),
    "askuserquestion": frozenset({"ask_user"}),
    "workflow": frozenset({"workflow_run"}),
    "schedulewakeup": frozenset({"schedule_wakeup"}),
    # Fusion'da ayrı defter aracı yok; `.ipynb` de dosya düzenlemesiyle yazılır.
    "notebookedit": frozenset({"edit_file", "write_file"}),
    "todowrite": frozenset({"todo_write"}),
}

#: Claude'un MCP araç adı öneki: `mcp__<sunucu>__<araç>` Fusion kayıt adıyla aynıdır (#242);
#: `mcp__<sunucu>` (araçsız) o sunucunun TÜM araçları demektir ve `*`la eşlenir.
_MCP_PREFIX = "mcp__"
_TRUE_WORDS = frozenset({"true", "yes", "evet", "1", "on"})

#: Codex `sandbox_mode = "read-only"` ajanının Fusion karşılığı olan salt-okur araç seti.
_READ_ONLY_TOOLS: tuple[str, ...] = ("Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch")

#: Üçüncü tarafın doldurduğu kökler: oradaki sembolik bağ kök DIŞINA (`~/.ssh/id_rsa`)
#: çıkıyorsa içerik sızdırma yolu olur (T1-15). Kullanıcının kendi kökleri (`~/.claude`,
#: proje) dotfile yöneticilerinin bağlarını kullanabilir ve denetlenmez.
_UNTRUSTED_SOURCES = frozenset({"kurulu", "claude-plugin", "eklenti"})

#: Frontmatter ararken dosyanın başından okunacak karakter. 4000 iken uzun açıklamalı
#: skill'lerde bitiş işareti görülmüyor, `{}` dönüp ad dizin adına düşüyordu (ölçüldü, 30 Ekim).
_HEAD_CHARS = 16_000

#: Eski Fusion kimlikleri korunur; Claude uyumluluk adları aynı yerleşik kayda çözülür.
BUILTIN_AGENT_ALIASES: Mapping[str, str] = {"Explore": "explore", "Plan": "plan"}

#: Claude Code'un belgeli yerleşik ajanları; `extra_agent_sources=False` iken yerleşik
#: rosterdan yalnız bunlar kalır (Claude'da olmayan Türkçe ekip rolleri düşer, #38).
CLAUDE_BUILTIN_AGENTS = frozenset(
    {"general-purpose", "explore", "plan", "claude", "statusline-setup", "claude-code-guide"}
)


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
    proposal: ProposalInvocation | None = None
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
    #: Beceri/alt ajan modeli. Alt ajanda (P-034) `<sağlayıcı>/<model>`; `inherit`/kısa
    #: takma ad (`sonnet`) üst ajanı kullanır. Boş = miras.
    model: str = ""
    effort: str = ""
    #: `context: fork` → alt ajanda çalıştır (P-054).
    context: str = ""
    #: `agent`: `context: fork` becerisinin koşacağı alt ajan tanımının adı; boş = genel.
    agent: str = ""
    #: `disable-model-invocation: true` → beceri dizinine ve find_skill sonucuna girmez;
    #: yalnız kullanıcı `/ad` ile çağırır.
    model_invocable: bool = True
    #: `user-invocable: false` → slash komutu olarak sunulmaz (yalnız model yükler).
    user_invocable: bool = True
    #: `argument-hint` → yardım ve tamamlamada gösterilen argüman biçimi.
    argument_hint: str = ""
    #: Beceri `arguments`: `$ad` yerleştirmesinde konumlara sırayla eşlenen adlar (#169).
    arguments: tuple[str, ...] = ()
    #: Beceri `paths`: yalnız eşleşen dosyalarla çalışırken otomatik yükleme globları (#169).
    paths: tuple[str, ...] = ()
    #: Beceri `shell`: `!`cmd`` kabuğu (`bash` | `powershell`); boş = bash.
    shell: str = ""
    #: Beceri `background` (yalnız `context: fork`): False → fork sonucu tur içinde beklenir.
    skill_background: bool = True
    #: Alt ajan ayarları (P-034; Claude Code `.claude/agents` frontmatter'ı). Boş = miras.
    #: `permissionMode`: yalnız SIKILAŞTIRIR (bypass miras alınmaz).
    permission_mode: str = ""
    #: `maxTurns`: alt ajanın model çağrısı tavanı; 0 = derinliğe göre varsayılan.
    max_turns: int = 0
    #: `skills`: başlangıçta tam içeriğiyle yüklenecek beceri adları.
    skills: tuple[str, ...] = ()
    #: `mcpServers`: bu ajana açılacak MCP sunucuları; boş = hepsi.
    mcp_servers: tuple[str, ...] = ()
    #: `memory`: user | project | local (P-055); boş = ajan belleği yok.
    memory: str = ""
    #: `background`: bekleme istense de arka planda kal; `isolation: worktree`: ayrı git
    #: çalışma ağacı; `hooks`: olay adları (tam tanım `hook_definitions`ta).
    background: bool = False
    isolation: str = ""
    hooks: tuple[str, ...] = ()
    #: `disallowedTools`: Claude adlarıyla; `tools`'tan sonra uygulanır.
    disallowed_tools: tuple[str, ...] = ()
    #: `capabilities.overrides: {ad: name-only}` → dizinde yalnız ad (P-051).
    describe_in_index: bool = True
    #: CLI tanımının gövdesi; None dosyadan okumayı, boş metin açık boş promptu belirtir.
    inline_prompt: str | None = None
    initial_prompt: str = ""
    omit_claude_md: bool = False
    #: `autoCompactWindow` (belirteç); 0 = oturumun eşiği.
    auto_compact_window: int = 0
    #: `experimental.cacheTtl`: `5m` | `1h`; boş = varsayılan.
    cache_ttl: str = ""
    hook_definitions: HookSet = field(default_factory=HookSet, repr=False)
    inline_mcp_servers: tuple[McpServerConfig, ...] = field(default=(), repr=False)

    @property
    def qualified_name(self) -> str:
        """İçerik değişse de aynı kaynağı seçen kararlı katalog kimliği."""
        return f"{self.name}@{self.source}:{_path_identity(str(self.path))}"

    @property
    def revision(self) -> str:
        """Gösterilen/yüklenen içeriğin sürümü; okunamıyorsa bilinmiyor."""
        if self.inline_prompt is not None:
            return hashlib.sha256(self.inline_prompt.encode()).hexdigest()
        try:
            return hashlib.sha256(self.path.read_bytes()).hexdigest()
        except OSError:
            return ""


def map_tools(claude_tools: tuple[str, ...]) -> set[str] | None:
    """Claude araç adlarını Fusion adlarına çevir. `*` ya da boş → None (tam set).

    `mcp__<sunucu>__<araç>` kayıt adıyla aynen kalır, `mcp__<sunucu>` ise
    `mcp__<sunucu>__*` desenine çevrilir (bkz. `expand_tool_patterns`).
    """
    if claude_tools == NO_TOOLS:
        return set()
    if not claude_tools or claude_tools == ("*",):
        return None
    allowed: set[str] = set()
    for name in claude_tools:
        mcp = _mcp_tool_name(name)
        if mcp is not None:
            allowed.add(mcp)
            continue
        allowed |= CLAUDE_TOOL_MAP.get(name.strip().lower(), frozenset())
    return allowed


def unmapped_tools(claude_tools: tuple[str, ...]) -> tuple[str, ...]:
    """Fusion'da karşılığı olmayan Claude araç adları (uyarı için; P-034)."""
    if not claude_tools or claude_tools in (NO_TOOLS, ("*",)):
        return ()
    return tuple(
        name
        for name in claude_tools
        if _mcp_tool_name(name) is None and name.strip().lower() not in CLAUDE_TOOL_MAP
    )


def expand_tool_patterns(names: set[str], available: tuple[str, ...]) -> set[str]:
    """`mcp__sunucu__*` desenlerini mevcut araç adlarına aç; düz adlar aynen kalır.

    MCP adları (#242) `mcp__` önekli ya da eski öneksiz yazımla karşılaştırılır: eski
    `sunucu__*` deseni ve `sunucu__araç` adı yeni kayıt adını da bulur.
    """
    expanded: set[str] = set()
    for name in names:
        if name.endswith("__*"):
            prefix = name[:-1]
            if not prefix.startswith(_MCP_PREFIX):
                prefix = f"{_MCP_PREFIX}{prefix}"
            expanded.update(t for t in available if canonical_mcp_name(t).startswith(prefix))
            continue
        expanded.add(name)
        if split_mcp_tool_name(name) is not None:
            wanted = canonical_mcp_name(name)
            expanded.update(t for t in available if canonical_mcp_name(t) == wanted)
    return expanded


def _mcp_tool_name(name: str) -> str | None:
    cleaned = name.strip()
    if not cleaned.lower().startswith(_MCP_PREFIX):
        return None
    rest = cleaned[len(_MCP_PREFIX) :]
    if not rest:
        return None
    full = f"{_MCP_PREFIX}{rest}"  # kayıt adı da `mcp__` önekli (#242)
    return full if "__" in rest else f"{full}__*"


def parse_setting_int(value: object) -> int:
    """`maxTurns` gibi sayısal alan; bozuk/negatif değer 0 (= varsayılan) sayılır."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def parse_setting_bool(value: object) -> bool:
    return str(value).strip().lower() in _TRUE_WORDS


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
    text = with_plugin_root(text, path)
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return text
    end = stripped.find("\n---", 3)
    return text if end == -1 else stripped[end + 4 :].lstrip()


def agent_prompt(capability: Capability) -> str:
    """CLI gövdesini veya mevcut korumalı dosya okuma yolunu kullan."""
    if capability.inline_prompt is not None:
        return capability.inline_prompt
    return load_agent_prompt(capability.path)


class CapabilityRegistry:
    """Skill ve agent keşfi.

    Tarama tembeldir ve önbelleklenir; kök dizinlerin mtime imzası değişince (yeni beceri
    klasörü eklendi/silindi) kendiliğinden yenilenir, `invalidate()` içerik değişikliği için
    elle yeniler (`/skills reload`, `yetenek.yenile`; P-051). `extra_roots` (`--add-dir`)
    köklerinin `.claude/skills`, `.agents/skills`, `.fusion/skills` ve `.claude/agents`
    dizinleri "ek-kok" etiketiyle taranır (P-052).
    """

    def __init__(
        self,
        home: Path,
        root: Path,
        *,
        disabled_skills: frozenset[str] = frozenset(),
        disabled_agents: frozenset[str] = frozenset(),
        extra_roots: tuple[Path, ...] = (),
        overrides: Mapping[str, SkillVisibility] | None = None,
        proposal_policy: ProposalPolicy | None = None,
        managed_roots: tuple[Path, ...] = (),
        session_agents: tuple[Capability, ...] = (),
        working_directory: Path | None = None,
        disabled_builtin_agents: frozenset[str] = frozenset(),
        extra_agent_sources: bool = True,
    ) -> None:
        self._proposal_policy = proposal_policy or ProposalPolicy()
        self._home = home
        self._root = root
        self._disabled_skills = disabled_skills
        self._disabled_agents = disabled_agents | frozenset(
            alias
            for name, target in BUILTIN_AGENT_ALIASES.items()
            if name in disabled_agents or target in disabled_agents
            for alias in (name, target)
        )
        self._extra_roots = extra_roots
        self._overrides: Mapping[str, SkillVisibility] = dict(overrides or {})
        self._managed_roots = managed_roots
        self._session_agents = session_agents
        self._working_directory = working_directory
        #: Yalnız paketle gelen (`fusion`) tanımlar; aynı adlı kullanıcı/proje tanımı kalır.
        self._disabled_builtin_agents = disabled_builtin_agents
        #: `agent_launch.extra_agent_sources`: Claude kapsamları dışı kaynaklar (#38).
        self._extra_agent_sources = extra_agent_sources
        #: Alt klasörlerde tembel keşfedilen beceri dizinleri (P-052); bkz. `add_nested_roots`.
        self._nested_roots: tuple[Path, ...] = ()
        self._skills: tuple[Capability, ...] | None = None
        self._agents: tuple[Capability, ...] | None = None
        self._signature: tuple[tuple[str, int], ...] | None = None

    def add_nested_roots(self, folders: tuple[Path, ...]) -> tuple[Capability, ...]:
        """Alt klasör beceri dizinlerini kataloğa ekle; YENİ görünen becerileri döndür.

        Model monorepo alt paketindeki bir dosyaya erişince çağrılır (P-052). Zaten bilinen
        dizin yeniden taranmaz; aynı adda kök/kullanıcı becerisi varsa o kazanır.
        """
        fresh = tuple(
            folder
            for folder in dict.fromkeys(folders)
            if folder not in self._nested_roots and folder.is_dir()
        )
        if not fresh:
            return ()
        before = {item.qualified_name for item in self.skills()}
        self._nested_roots = (*self._nested_roots, *fresh)
        self._skills = None
        return tuple(item for item in self.skills() if item.qualified_name not in before)

    @property
    def nested_roots(self) -> tuple[Path, ...]:
        """Tembel keşfedilmiş alt klasör beceri dizinleri (yeniden kurulan deftere taşınır)."""
        return self._nested_roots

    def with_extra_roots(self, extra_roots: tuple[Path, ...]) -> CapabilityRegistry:
        """Aynı kapatma listeleriyle, ek kökleri değişmiş yeni bir defter."""
        clone = self._with_extra_roots(extra_roots)
        clone._nested_roots = self._nested_roots
        return clone

    def with_overrides(self, overrides: Mapping[str, SkillVisibility]) -> CapabilityRegistry:
        """Aynı kökler, farklı görünürlük (`/skills` paneli: `off` olanlar da listelenir; #176)."""
        clone = self._with_extra_roots(self._extra_roots)
        clone._overrides = dict(overrides)
        clone._nested_roots = self._nested_roots
        return clone

    def _with_extra_roots(self, extra_roots: tuple[Path, ...]) -> CapabilityRegistry:
        return CapabilityRegistry(
            self._home,
            self._root,
            disabled_skills=self._disabled_skills,
            disabled_agents=self._disabled_agents,
            extra_roots=extra_roots,
            overrides=self._overrides,
            proposal_policy=self._proposal_policy,
            managed_roots=self._managed_roots,
            session_agents=self._session_agents,
            working_directory=self._working_directory,
            disabled_builtin_agents=self._disabled_builtin_agents,
            extra_agent_sources=self._extra_agent_sources,
        )

    @property
    def home(self) -> Path:
        """Kataloğun okuduğu ev dizini (Claude eklenti kurulumları buradan okunur)."""
        return self._home

    def invalidate(self) -> None:
        """Önbelleği boşalt; bir sonraki erişim diski yeniden tarar."""
        self._skills = None
        self._agents = None
        self._signature = None

    def _refresh_if_changed(self) -> None:
        """Kök dizinlerden biri eklendi/silindi/değişti mi? Değiştiyse önbelleği düşür."""
        signature = self._current_signature()
        if self._signature is not None and signature != self._signature:
            self._skills = None
            self._agents = None
        self._signature = signature

    def _current_signature(self) -> tuple[tuple[str, int], ...]:
        # Eklenti kaydı (P-059) değişince (kur/kapat/kaldır) katalog da yenilenir.
        plugins = state_signature(root=self._root)
        signature = roots_signature(
            self._skill_roots(), self._agent_roots(), self._home, self._root
        )
        return (*signature, plugins) if plugins else signature

    def skills(self) -> tuple[Capability, ...]:
        # Sonuç yerel değişkenden döner: `invalidate()` (masaüstü yenile RPC'si) başka
        # thread'den alanı `None` yaparsa çağıran `for … in None` ile düşmesin.
        self._refresh_if_changed()
        skills = self._skills
        if skills is None:
            skills = apply_overrides(
                tuple(
                    item
                    for item in self._discover_skills()
                    if item.name not in self._disabled_skills
                    and item.qualified_name not in self._disabled_skills
                ),
                self._overrides,
            )
            self._skills = skills
        return tuple(
            item for item in skills if visible_proposal(item.proposal, self._proposal_policy)
        )

    def with_proposal_policy(self, policy: ProposalPolicy) -> CapabilityRegistry:
        """Önbellek ve ek kökleri koruyan değişmez tüketim görünümü."""
        clone = self.with_extra_roots(self._extra_roots)
        clone._proposal_policy = policy
        return clone

    def agents(self) -> tuple[Capability, ...]:
        self._refresh_if_changed()
        agents = self._agents
        if agents is None:
            agents = tuple(
                item
                for item in self._discover_agents()
                if item.name not in self._disabled_agents
                and item.qualified_name not in self._disabled_agents
                and not (
                    item.source == "fusion"
                    and (
                        item.name in self._disabled_builtin_agents
                        or "*" in self._disabled_builtin_agents
                    )
                )
            )
            self._agents = agents
        return agents

    def get_skill(self, name: str) -> Capability | None:
        return _select(self.skills(), name)

    def candidates(self, name: str) -> tuple[str, ...]:
        """Bu ada sahip skill'lerin nitelikli adları (`ad@kaynak:kimlik`).

        `get_skill(ad)` farklı içerikli birden çok kaynakta None döner (kaynak seçimi
        bilinçlidir); çağıran modele "yok" demek yerine bu adayları sunabilir.
        """
        return tuple(item.qualified_name for item in self.skills() if item.name == name)

    def get_agent(self, name: str) -> Capability | None:
        agents = self.agents()
        selected = _select(agents, name, bundled_override=True)
        alias = BUILTIN_AGENT_ALIASES.get(name)
        if selected is None and alias is not None and all(item.name != name for item in agents):
            selected = _select(agents, alias, bundled_override=True)
        if selected is not None or ":" in name:
            return selected
        # Claude Code: tek eklentide bulunan ajan yalın adla da seçilir (`--agent kodcu`).
        scoped = [
            item
            for item in agents
            if PLUGIN_SOURCE in item.source.split("+") and item.name.rsplit(":", 1)[-1] == name
        ]
        if len(scoped) == 1:
            return scoped[0]
        if scoped or not self._extra_agent_sources or name in self._disabled_agents:
            return None
        return legacy_team_agent(name, _to_agent_capability)

    # ----------------------------------------------------------------------- #

    def _skill_roots(self) -> tuple[tuple[Path, str], ...]:
        # Yerleşik/kurulu kökler burada çözülür: testler bu modülün adlarını yamalar.
        return skill_roots(
            self._home,
            self._root,
            self._extra_roots,
            installed=capabilities_dir(),
            bundled=bundled_skills_dir(),
            nested=self._nested_roots,
            ancestors=ancestor_skill_dirs(self._root),
            managed=managed_skill_dirs(),
        )

    def _agent_roots(self) -> tuple[tuple[Path, str], ...]:
        return agent_roots(
            self._home,
            self._root,
            self._extra_roots,
            installed=capabilities_dir(),
            bundled=bundled_roster_dir(),
            managed_roots=self._managed_roots,
            working_directory=self._working_directory,
            extra_sources=self._extra_agent_sources,
        )

    def _keeps_source(self, capability: Capability) -> bool:
        """Ek kaynaklar kapalıyken yerleşik rosterdan yalnız Claude'un yerleşikleri kalır."""
        return (
            self._extra_agent_sources
            or capability.source != "fusion"
            or capability.name in CLAUDE_BUILTIN_AGENTS
        )

    def _discover_skills(self) -> tuple[Capability, ...]:
        found: dict[str, Capability] = {}
        for root, source in self._skill_roots():
            if not root.exists():
                continue
            warn_deprecated_root(root, self._home, self._root)
            for path in sorted(root.rglob("SKILL.md")):
                if not _trusted_path(path, root, source):
                    continue
                if source == "claude" and _in_skills_dir_plugin(path, root):
                    continue  # `<ad>@skills-dir` eklentisi: önekli eklenti becerisi (#401)
                capability = _to_capability(path, source, fallback=path.parent.name)
                if root in self._nested_roots and any(
                    item.name == capability.name for item in found.values()
                ):
                    # Claude Code (#158): ikisi de kalır; `/ad` kök beceriyi, `/<dizin>:ad`
                    # iç içe olanı çalıştırır, açıklaması uygulandığı dizini söyler.
                    capability = qualify_nested(capability, root, self._root)
                # İlk bulunan İÇERİĞİ verir: tüm Claude/proje kökleri dış kaynaklardan
                # önce gelir. Sonrakiler yalnız kaynak etiketine eklenir.
                _merge(found, capability)
        # `.claude/commands/*.md` tek dosyalı komutlar da `/ad` ile çağrılır; aynı adlı
        # SKILL.md kazanır (Claude Code'da ikisi aynı komutu üretir).
        from .skill_commands import discover_commands

        for command in discover_commands(self._home, self._root):
            if isinstance(command, Capability) and command.name not in found:
                found[command.name] = command
        # Etkin eklentiler (P-059): adlar `eklenti:ad` önekli, kimseyi gölgelemez.
        home = self._home
        for capability in (
            *plugin_skills(_to_capability, home, self._root),
            *plugin_commands(_to_capability, home, self._root),
        ):
            _merge(found, capability)
        return tuple(found.values())

    def _discover_agents(self) -> tuple[Capability, ...]:
        found: dict[str, Capability] = {}
        for capability in self._session_agents:
            shadow_agent(found, bind_agent_source(capability, "cli"))
        for root, source in self._agent_roots():
            if not root.exists():
                continue
            # Kurulu repoda `agents/` klasörünün kendisi de bağ olabilir: sınır repo kökü.
            bound = root.parent if source == "kurulu" else root
            for path in sorted(root.rglob("*.md")):
                if not _trusted_path(path, bound, source):
                    continue
                agent_file = _agent_file(path, source)
                if agent_file is not None and self._keeps_source(agent_file):
                    shadow_agent(found, agent_file)
            # Codex agent'ları TOML tutar; aynı kökte iki biçim yan yana olabilir. Claude
            # TOML okumaz: ek kaynaklar kapalıyken hiç taranmaz (#38).
            toml_paths = sorted(root.rglob("*.toml")) if self._extra_agent_sources else []
            for path in toml_paths:
                if not _trusted_path(path, bound, source):
                    continue
                toml_capability = _toml_capability(path, source)
                if toml_capability is not None:
                    shadow_agent(found, toml_capability)
        for capability in plugin_agents(_to_agent_capability, self._home, self._root):
            shadow_agent(found, capability)
        return tuple(found.values())


def _in_skills_dir_plugin(path: Path, root: Path) -> bool:
    from ..config.plugin_skills_dir import skills_dir_plugin_of

    return skills_dir_plugin_of(path, root)


def _trusted_path(path: Path, bound: Path, source: str) -> bool:
    """Üçüncü taraf kökündeki dosya, `bound` dışına çıkan bir sembolik bağ DEĞİL mi?"""
    if source not in _UNTRUSTED_SOURCES or not path.is_symlink():
        return True
    try:
        return path.resolve().is_relative_to(bound.resolve())
    except OSError:
        return False


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
        model=str(data.get("model") or ""),
        permission_mode=str(data.get("permission_mode") or ""),
        max_turns=parse_setting_int(data.get("max_turns", 0)),
        memory=str(data.get("memory") or ""),
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


def _agent_file(path: Path, source: str) -> Capability | None:
    """Kapsam dizinindeki ajan dosyası; Claude Code'un atladığı dosyada `None` (#19, #41)."""
    raw = _read_head(path, None)
    problem = agent_file_problem(raw, parse_frontmatter(raw))
    if problem:
        log_skipped(path, problem)
        return None
    return _to_agent_capability(path, source, fallback=path.stem)


def _to_agent_capability(path: Path, source: str, *, fallback: str) -> Capability:
    """Ajan açıklaması büyükse uyarılabilsin; frontmatter kapanışını kesme."""
    return _to_capability(path, source, fallback=fallback, limit=None)


def _to_capability(
    path: Path, source: str, *, fallback: str, limit: int | None = _HEAD_CHARS
) -> Capability:
    raw = _read_head(path, limit)
    fields = parse_frontmatter(raw)
    if path.name == "SKILL.md" and not str(fields.get("description") or "").strip():
        # Claude Code: description yoksa gövdenin ilk dolu satırı açıklamadır (#180).
        fields = {**fields, "description": _first_body_line(raw)}
    try:
        proposal = proposal_metadata(raw)
    except (ValueError, TypeError):
        proposal = ProposalInvocation("invalid", "", RoutineSpec("", "", "", (), ()), "")
    return _capability_from_fields(path, source, fields, fallback=fallback, proposal=proposal)


def _first_body_line(raw: str) -> str:
    for line in body_after_frontmatter(raw).splitlines():
        cleaned = line.strip().lstrip("#").strip()
        if cleaned:
            return cleaned
    return ""


def _capability_from_fields(
    path: Path,
    source: str,
    fields: Mapping[str, object],
    *,
    fallback: str,
    proposal: ProposalInvocation | None = None,
) -> Capability:
    """Dosya ve dosyasız CLI tanımında aynı alan dönüşümünü uygula."""
    allowed = fields.get("allowed_tools")
    description = str(fields.get("description") or "")
    when = str(fields.get("when_to_use") or "")
    if when:  # Claude Code `when_to_use` açıklamanın devamıdır; arama ve dizin ikisini görür
        description = f"{description} {when}".strip()
    capability = Capability(
        name=str(fields.get("name") or fallback),
        proposal=proposal,
        description=description,
        path=path,
        source=source,
        tools=_tuple_field(fields, "tools"),
        title=str(fields.get("title") or ""),
        avatar=str(fields.get("avatar") or ""),
        color=normalize_agent_color(str(fields.get("color") or "")),
        allowed_tools=tuple(allowed) if isinstance(allowed, tuple) and allowed != NO_TOOLS else (),
        model=str(fields.get("model") or ""),
        effort=str(fields.get("effort") or "").lower(),
        context=str(fields.get("context") or "").lower(),
        agent=str(fields.get("agent") or ""),
        model_invocable=bool(fields.get("model_invocable", True)),
        user_invocable=bool(fields.get("user_invocable", True)),
        argument_hint=str(fields.get("argument_hint") or ""),
        arguments=_tuple_field(fields, "arguments"),
        paths=_tuple_field(fields, "paths"),
        shell=str(fields.get("shell") or "").lower(),
        skill_background=parse_setting_bool(fields.get("background", "true")),
        permission_mode=str(fields.get("permission_mode") or ""),
        max_turns=parse_setting_int(fields.get("max_turns", 0)),
        skills=_tuple_field(fields, "skills"),
        mcp_servers=_tuple_field(fields, "mcp_servers"),
        memory=str(fields.get("memory") or "").lower(),
        background=parse_setting_bool(fields.get("background", "")),
        isolation=str(fields.get("isolation") or "").lower(),
        hooks=_tuple_field(fields, "hooks"),
        disallowed_tools=_disallowed_tools(fields),
    )
    return apply_agent_metadata(capability, fields)


def _disallowed_tools(fields: Mapping[str, object]) -> tuple[str, ...]:
    """Frontmatter yasağı belirteç taşısa da tüm araç ailesini kaldırır.

    CLI izin kuralları ayrı ayrıştırılır; onların komut/yol kapsamı burada çözülmez.
    `tools` izin listesi de bu dönüşümden geçmez (ör. `Agent(tip)`).
    """
    return tuple(
        item.partition("(")[0].strip()
        for item in _tuple_field(fields, "disallowed_tools")
        if item != NO_TOOLS[0]
    )


def _tuple_field(fields: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = fields.get(key)
    return tuple(str(item) for item in value) if isinstance(value, tuple) else ()


def _read_head(path: Path, limit: int | None = _HEAD_CHARS) -> str:
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except OSError:
        return ""


def managed_skill_dirs() -> tuple[Path, ...]:
    """Kurumsal beceri kökü: Claude Code yönetilen dizinin `.claude/skills`'i (#157)."""
    from ..config.claude_settings import managed_dir

    folder = managed_dir()
    return (folder / ".claude" / "skills",) if folder is not None else ()


_LOG = logging.getLogger(__name__)
_WARNED_ROOTS: set[Path] = set()


def warn_deprecated_root(folder: Path, home: Path, root: Path) -> None:
    """Claude Code'da olmayan kök bir sürüm okunur; kök başına bir kez uyarı loglanır (#157)."""
    from .capability_roots import deprecated_root

    label = deprecated_root(folder, home, root)
    if not label or folder in _WARNED_ROOTS or not any(folder.rglob("SKILL.md")):
        return
    _WARNED_ROOTS.add(folder)
    _LOG.warning(
        "%s beceri kökü kullanımdan kalktı (Claude Code okumaz); becerileri "
        "~/.claude/skills ya da .claude/skills altına taşı",
        label,
    )


def qualify_nested(capability: Capability, folder: Path, root: Path) -> Capability:
    """Aynı adlı iç içe beceriyi `<dizin>:<ad>` adıyla ve dizinini anan açıklamayla sun (#158)."""
    owner = folder.parent.parent  # <dizin>/.claude/skills → <dizin>
    try:
        prefix = owner.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        prefix = owner.name
    description = f"{prefix}/ altındaki dosyalar için. {capability.description}".strip()
    return replace(capability, name=f"{prefix}:{capability.name}", description=description)


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

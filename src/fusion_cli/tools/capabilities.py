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

import functools
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
    # Claude Code'un yeni adları (P-034): alt ajan, beceri, soru, defter, görev listesi.
    "agent": frozenset({"spawn_agent", "spawn_agents", "find_agent", "invoke_agent"}),
    "skill": frozenset({"find_skill", "read_skill"}),
    "askuserquestion": frozenset({"ask_user"}),
    # Fusion'da ayrı defter aracı yok; `.ipynb` de dosya düzenlemesiyle yazılır.
    "notebookedit": frozenset({"edit_file", "write_file"}),
    "todowrite": frozenset({"todo_write"}),
}

#: Claude'un MCP araç adı öneki: `mcp__<sunucu>__<araç>` → Fusion `<sunucu>__<araç>`;
#: `mcp__<sunucu>` (araçsız) o sunucunun TÜM araçları demektir ve `*`la eşlenir.
_MCP_PREFIX = "mcp__"

#: Alt ajan tanımının ayar alanları (P-034): frontmatter anahtarı → `Capability` alanı.
#: Claude Code'un camelCase adları, snake_case ve Türkçe karşılıklar kabul edilir.
AGENT_SETTING_KEYS: dict[str, str] = {
    "model": "model",
    "permissionmode": "permission_mode",
    "permission_mode": "permission_mode",
    "izin_kipi": "permission_mode",
    "maxturns": "max_turns",
    "max_turns": "max_turns",
    "en_fazla_tur": "max_turns",
    "memory": "memory",
    "bellek": "memory",
    "background": "background",
    "arka_plan": "background",
    "effort": "effort",
    "efor": "effort",
    "isolation": "isolation",
    "yalitim": "isolation",
    "context": "context",
    "baglam": "context",
}
#: Liste alanları: anahtar → alan. `tools` ile aynı yazımlar (`[a, b]`, `a, b`, `- a`).
_LIST_KEYS: dict[str, str] = {
    "tools": "tools",
    "araclar": "tools",
    "skills": "skills",
    "beceriler": "skills",
    "mcpservers": "mcp_servers",
    "mcp_servers": "mcp_servers",
    "disallowedtools": "disallowed_tools",
    "disallowed_tools": "disallowed_tools",
    "yasak_araclar": "disallowed_tools",
}
_TRUE_WORDS = frozenset({"true", "yes", "evet", "1", "on"})

#: `tools:` anahtarı VAR ama hiçbir araç çözülemedi (`tools:` boş, `[]`): kısıt YOK değil,
#: HİÇ ARAÇ YOK demektir. Boş tuple "alan hiç yazılmamış" (tam yetki) anlamına gelir; ikisi
#: karışırsa salt-okur sanılan ajan `run_shell` yetkisiyle çalışır (T1-13).
NO_TOOLS: tuple[str, ...] = ("-",)
#: Codex `sandbox_mode = "read-only"` ajanının Fusion karşılığı olan salt-okur araç seti.
_READ_ONLY_TOOLS: tuple[str, ...] = ("Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch")

#: Üçüncü tarafın doldurduğu kökler: oradaki sembolik bağ kök DIŞINA (`~/.ssh/id_rsa`)
#: çıkıyorsa içerik sızdırma yolu olur (T1-15). Kullanıcının kendi kökleri (`~/.claude`,
#: proje) dotfile yöneticilerinin bağlarını kullanabilir ve denetlenmez.
_UNTRUSTED_SOURCES = frozenset({"kurulu", "claude-plugin"})

#: Kişilik alanları: frontmatter anahtarı → `Capability` alanı. Türkçe ve İngilizce
#: yazım ikisi de kabul edilir; kullanıcı kendi ajanını hangisiyle yazarsa.
_PERSONA_KEYS: dict[str, str] = {
    "unvan": "title",
    "title": "title",
    "avatar": "avatar",
    "renk": "color",
    "color": "color",
}

#: Frontmatter ararken dosyanın başından okunacak karakter. 4000 iken uzun açıklamalı
#: skill'lerde bitiş işareti görülmüyor, `{}` dönüp ad dizin adına düşüyordu (ölçüldü, 30 Ekim).
_HEAD_CHARS = 16_000
_BLOCK_SCALARS = frozenset({">", "|", ">-", "|-", ">+", "|+"})


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
    #: Alt ajan ayarları (P-034; Claude Code `.claude/agents` frontmatter'ı). Boş = miras.
    #: `model`: `<sağlayıcı>/<model>`; `inherit`/kısa takma ad (`sonnet`) üst ajanı kullanır.
    model: str = ""
    #: `permissionMode`: yalnız SIKILAŞTIRIR (bypass miras alınmaz).
    permission_mode: str = ""
    #: `maxTurns`: alt ajanın model çağrısı tavanı; 0 = derinliğe göre varsayılan.
    max_turns: int = 0
    #: `skills`: başlangıçta yüklenecek beceri adları (en fazla `SKILL_PRELOAD_LIMIT`).
    skills: tuple[str, ...] = ()
    #: `mcpServers`: bu ajana açılacak MCP sunucuları; boş = hepsi.
    mcp_servers: tuple[str, ...] = ()
    #: `memory`: user | project | local (P-055); boş = ajan belleği yok.
    memory: str = ""
    #: `background`, `isolation: worktree`, `hooks`: okunur ve katalogda gösterilir;
    #: Fusion'da alt ajan tur içinde biter ve kendi worktree'si yoktur (bkz. docs).
    background: bool = False
    effort: str = ""
    isolation: str = ""
    hooks: tuple[str, ...] = ()
    #: `disallowedTools`: Claude adlarıyla; `tools`'tan sonra uygulanır.
    disallowed_tools: tuple[str, ...] = ()
    #: Beceriler için `context: fork` (P-054): beceri izole alt ajanda çalıştırılmak ister.
    context: str = ""

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
    lines = stripped[3:end].splitlines()
    index = 0
    while index < len(lines):
        key, separator, value = lines[index].partition(":")
        index += 1
        if not separator:
            continue
        name = key.strip().lower()
        if name in _LIST_KEYS:
            # `tools:` + alt satırlarda `- Read` blok listesi YAML'ın olağan yazımıdır;
            # `skills`, `mcpServers`, `disallowedTools` aynı yazımları paylaşır.
            items = list(_parse_tools(value.strip()))
            while not value.strip() and index < len(lines) and _is_list_item(lines[index]):
                items.append(_list_item(lines[index]))
                index += 1
            field_name = _LIST_KEYS[name]
            cleaned = tuple(item for item in items if item)
            fields[field_name] = (cleaned or NO_TOOLS) if field_name == "tools" else cleaned
        elif name == "hooks":
            # İç içe blok: `hooks:` altındaki girintili `PreToolUse:` gibi anahtarlar olay
            # adlarıdır; gövdeleri (matcher/komut) burada yorumlanmaz.
            events: list[str] = []
            while index < len(lines) and (not lines[index].strip() or lines[index][:1] in " \t"):
                line = lines[index].strip()
                if line and not line.startswith("-") and ":" in line and lines[index][:1] in " \t":
                    indent = len(lines[index]) - len(lines[index].lstrip())
                    if indent <= 2 or not events:
                        events.append(line.partition(":")[0].strip().strip("'\""))
                index += 1
            fields["hooks"] = tuple(dict.fromkeys(event for event in events if event))
        elif name in AGENT_SETTING_KEYS:
            fields[AGENT_SETTING_KEYS[name]] = value.strip().strip("'\"")
        elif name in ("name", "description"):
            text = value.strip()
            if text in _BLOCK_SCALARS:
                # YAML blok skaleri: girintili satırlar değerdir (`>` birleştirir, `|` korur).
                block: list[str] = []
                while index < len(lines) and (
                    not lines[index].strip() or lines[index][:1] in " \t"
                ):
                    block.append(lines[index].strip())
                    index += 1
                joiner = " " if text.startswith(">") else "\n"
                fields[name] = joiner.join(part for part in block if part).strip()
            else:
                fields[name] = text.strip("'\"")
        elif name in _PERSONA_KEYS:
            fields[_PERSONA_KEYS[name]] = value.strip().strip("'\"")
    return fields


def map_tools(claude_tools: tuple[str, ...]) -> set[str] | None:
    """Claude araç adlarını Fusion adlarına çevir. `*` ya da boş → None (tam set).

    `mcp__<sunucu>__<araç>` Fusion'ın `<sunucu>__<araç>` adına, `mcp__<sunucu>` ise
    `<sunucu>__*` desenine çevrilir (bkz. `expand_tool_patterns`).
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
    """`sunucu__*` desenlerini mevcut araç adlarına aç; düz adlar aynen kalır."""
    expanded: set[str] = set()
    for name in names:
        if name.endswith("__*"):
            prefix = name[:-1]
            expanded.update(tool for tool in available if tool.startswith(prefix))
        else:
            expanded.add(name)
    return expanded


def _mcp_tool_name(name: str) -> str | None:
    cleaned = name.strip()
    if not cleaned.lower().startswith(_MCP_PREFIX):
        return None
    rest = cleaned[len(_MCP_PREFIX) :]
    if not rest:
        return None
    return rest if "__" in rest else f"{rest}__*"


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


def _to_capability(path: Path, source: str, *, fallback: str) -> Capability:
    fields = parse_frontmatter(_read_head(path))
    return Capability(
        name=str(fields.get("name") or fallback),
        description=str(fields.get("description") or ""),
        path=path,
        source=source,
        tools=_tuple_field(fields, "tools"),
        title=str(fields.get("title") or ""),
        avatar=str(fields.get("avatar") or ""),
        color=str(fields.get("color") or ""),
        model=str(fields.get("model") or ""),
        permission_mode=str(fields.get("permission_mode") or ""),
        max_turns=parse_setting_int(fields.get("max_turns", 0)),
        skills=_tuple_field(fields, "skills"),
        mcp_servers=_tuple_field(fields, "mcp_servers"),
        memory=str(fields.get("memory") or "").lower(),
        background=parse_setting_bool(fields.get("background", "")),
        effort=str(fields.get("effort") or "").lower(),
        isolation=str(fields.get("isolation") or "").lower(),
        hooks=_tuple_field(fields, "hooks"),
        disallowed_tools=_tuple_field(fields, "disallowed_tools"),
        context=str(fields.get("context") or "").lower(),
    )


def _tuple_field(fields: dict[str, object], key: str) -> tuple[str, ...]:
    value = fields.get(key)
    return tuple(str(item) for item in value) if isinstance(value, tuple) else ()


def _read_head(path: Path, limit: int = _HEAD_CHARS) -> str:
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except OSError:
        return ""


def _is_list_item(line: str) -> bool:
    return line.lstrip().startswith("-") and not line.lstrip().startswith("---")


def _list_item(line: str) -> str:
    """`  - 'Read'   # açıklama` → `Read`."""
    body = line.lstrip()[1:].split(" #", 1)[0]
    return body.strip().strip("'\"")


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

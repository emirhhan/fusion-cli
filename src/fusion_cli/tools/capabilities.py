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

import re
from dataclasses import dataclass
from pathlib import Path

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

#: Bir skill talimatından modele verilecek en fazla karakter.
SKILL_TEXT_BUDGET = 6_000
#: Frontmatter ararken dosyanın başından okunacak karakter.
_HEAD_CHARS = 4_000


@dataclass(frozen=True, slots=True)
class Capability:
    """Bulunan bir skill ya da agent."""

    name: str
    description: str
    path: Path
    #: Nereden geldiği: global | plugin | proje
    source: str
    #: Agent'lar için bildirilen Claude araç adları. Boş ya da ("*",) → tam yetki.
    tools: tuple[str, ...] = ()


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
    return fields


def map_tools(claude_tools: tuple[str, ...]) -> set[str] | None:
    """Claude araç adlarını Fusion adlarına çevir. `*` ya da boş → None (tam set)."""
    if not claude_tools or claude_tools == ("*",):
        return None
    allowed: set[str] = set()
    for name in claude_tools:
        allowed |= CLAUDE_TOOL_MAP.get(name.strip().lower(), frozenset())
    return allowed


def search(items: tuple[Capability, ...], query: str, limit: int = 6) -> tuple[Capability, ...]:
    """Ad ve açıklama üzerinde kelime örtüşmesine göre ara.

    Basit ve öngörülebilir: hiç eşleşmeyenler elenir, en çok örtüşen öne gelir.
    Boş sorgu ilk `limit` girdiyi döndürür.
    """
    terms = [word for word in query.lower().split() if word]
    if not terms:
        return items[:limit]
    scored = [(item, _score(item, terms)) for item in items]
    matching = [(item, score) for item, score in scored if score > 0]
    matching.sort(key=lambda pair: pair[1], reverse=True)
    return tuple(item for item, _ in matching[:limit])


def load_skill_text(path: Path, budget: int = SKILL_TEXT_BUDGET) -> str:
    """Bir skill talimatının tam metnini oku."""
    try:
        return path.read_text(encoding="utf-8")[:budget]
    except OSError as exc:
        return f"HATA: skill okunamadı: {exc}"


def load_agent_prompt(path: Path) -> str:
    """Agent tanımının gövdesi (frontmatter sonrası)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"HATA: agent okunamadı: {exc}"
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return text
    end = stripped.find("\n---", 3)
    return text if end == -1 else stripped[end + 4 :].lstrip()


class CapabilityRegistry:
    """Skill ve agent keşfi. Tarama oturumda bir kez yapılır."""

    def __init__(self, home: Path, root: Path) -> None:
        self._home = home
        self._root = root
        self._skills: tuple[Capability, ...] | None = None
        self._agents: tuple[Capability, ...] | None = None

    def skills(self) -> tuple[Capability, ...]:
        if self._skills is None:
            self._skills = self._discover_skills()
        return self._skills

    def agents(self) -> tuple[Capability, ...]:
        if self._agents is None:
            self._agents = self._discover_agents()
        return self._agents

    def get_skill(self, name: str) -> Capability | None:
        return next((item for item in self.skills() if item.name == name), None)

    def get_agent(self, name: str) -> Capability | None:
        return next((item for item in self.agents() if item.name == name), None)

    # ----------------------------------------------------------------------- #

    def _skill_roots(self) -> tuple[tuple[Path, str], ...]:
        # Sıra ÖNCELİKTİR: aynı adlı skill'de ilk bulunan kazanır (bkz. _discover_skills).
        # Claude önce gelir çünkü kullanıcının birincil kütüphanesi odur; Codex ve
        # Hermes aynı SKILL.md biçimini kullandığı için ayrıştırıcı değişmez.
        return (
            (self._home / ".claude" / "skills", "global"),
            (self._home / ".claude" / "plugins", "plugin"),
            (self._home / ".codex" / "skills", "codex"),
            (self._home / ".hermes" / "skills", "hermes"),
            (self._root / ".claude" / "skills", "proje"),
            (self._root / ".fusion" / "skills", "proje"),
        )

    def _agent_roots(self) -> tuple[tuple[Path, str], ...]:
        return (
            (self._home / ".claude" / "agents", "global"),
            (self._root / ".claude" / "agents", "proje"),
        )

    def _discover_skills(self) -> tuple[Capability, ...]:
        found: dict[str, Capability] = {}
        for root, source in self._skill_roots():
            if not root.exists():
                continue
            for path in sorted(root.rglob("SKILL.md")):
                capability = _to_capability(path, source, fallback=path.parent.name)
                # İlk bulunan kazanır: global > plugin > proje sırası bilinçlidir.
                found.setdefault(capability.name, capability)
        return tuple(found.values())

    def _discover_agents(self) -> tuple[Capability, ...]:
        found: dict[str, Capability] = {}
        for root, source in self._agent_roots():
            if not root.exists():
                continue
            for path in sorted(root.glob("*.md")):
                capability = _to_capability(path, source, fallback=path.stem)
                found.setdefault(capability.name, capability)
        return tuple(found.values())


def _to_capability(path: Path, source: str, *, fallback: str) -> Capability:
    fields = parse_frontmatter(_read_head(path))
    tools = fields.get("tools")
    return Capability(
        name=str(fields.get("name") or fallback),
        description=str(fields.get("description") or ""),
        path=path,
        source=source,
        tools=tuple(tools) if isinstance(tools, tuple) else (),
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


def _score(item: Capability, terms: list[str]) -> int:
    """Kaç arama terimi ad/açıklamada KELİME olarak geçiyor.

    Alt-dize değil kelime eşleşmesi: Türkçe görev metnindeki kısa kelimeler
    ("ve", "in", "er") İngilizce açıklamaların İÇİNDE eşleşip ("de-ve-lopment",
    "serv-er") tamamen alakasız skill'leri öne çıkarıyordu.
    """
    haystack = set(re.split(r"[^a-z0-9]+", f"{item.name} {item.description}".lower()))
    return sum(1 for term in terms if term in haystack)

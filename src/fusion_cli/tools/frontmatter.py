"""SKILL.md / agent frontmatter ayrıştırıcısı — elle yazılmış küçük bir YAML alt kümesi.

Tam YAML bağımlılığı gereksizdir ve bozuk bir frontmatter tüm keşfi düşürmemelidir: hata
yerine boş sözlük döner. Claude Code'un skill alanları Türkçe ve İngilizce anahtarla okunur
(P-020): `allowed-tools`, `disallowed-tools`, `model`, `effort`, `context: fork`, `agent`,
`disable-model-invocation`, `user-invocable`, `argument-hint`, `when_to_use`. Ajanlar için
`tools`, kişilik alanları ve alt ajan ayarları (P-034: `model`, `permissionMode`, `maxTurns`,
`skills`, `mcpServers`, `memory`, `background`, `isolation`, `hooks`, `disallowedTools`).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

import yaml

from ..config.hooks import MAX_HOOK_TIMEOUT_S, parse_hooks_block
from ..config.mcp_json import parse_project_mcp
from ..config.models import McpServerConfig
from ..core.errors import ConfigError
from ..core.hooks.events import HookSet

_LOG = logging.getLogger(__name__)

#: `tools:` anahtarı VAR ama hiçbir araç çözülemedi (`tools:` boş, `[]`): kısıt YOK değil,
#: HİÇ ARAÇ YOK demektir. Boş tuple "alan hiç yazılmamış" (tam yetki) anlamına gelir; ikisi
#: karışırsa salt-okur sanılan ajan `run_shell` yetkisiyle çalışır (T1-13).
NO_TOOLS: tuple[str, ...] = ("-",)

#: Kişilik alanları: frontmatter anahtarı → `Capability` alanı. Türkçe ve İngilizce
#: yazım ikisi de kabul edilir; kullanıcı kendi ajanını hangisiyle yazarsa.
_PERSONA_KEYS: dict[str, str] = {
    "unvan": "title",
    "title": "title",
    "avatar": "avatar",
    "renk": "color",
    "color": "color",
}

#: Düz metin skill alanları: anahtar (küçük harf, `-`/`_` eşdeğer) → alan adı.
_TEXT_KEYS: dict[str, str] = {
    "model": "model",
    "effort": "effort",
    "caba": "effort",
    "efor": "effort",
    "context": "context",
    "baglam": "context",
    "argument-hint": "argument_hint",
    "arguman-ipucu": "argument_hint",
    "when-to-use": "when_to_use",
    "ne-zaman": "when_to_use",
    # `context: fork` becerisinin koşacağı alt ajan tanımı (Claude Code `agent:`).
    "agent": "agent",
    "ajan": "agent",
}

#: Alt ajan tanımının düz metin ayar alanları (P-034): frontmatter anahtarı → `Capability`
#: alanı. Claude Code'un camelCase adları (küçük harfe inmiş), snake/kebab yazım ve Türkçe
#: karşılıklar kabul edilir. Değerler ham metindir; sayı/boole çevirisi `Capability`'de.
AGENT_SETTING_KEYS: dict[str, str] = {
    "permissionmode": "permission_mode",
    "permission-mode": "permission_mode",
    "izin-kipi": "permission_mode",
    "maxturns": "max_turns",
    "max-turns": "max_turns",
    "en-fazla-tur": "max_turns",
    "memory": "memory",
    "bellek": "memory",
    "background": "background",
    "arka-plan": "background",
    "isolation": "isolation",
    "yalitim": "isolation",
}

#: Boolean skill alanları: anahtar → (alan adı, değer tersine mi çevrilir).
_BOOL_KEYS: dict[str, tuple[str, bool]] = {
    "disable-model-invocation": ("model_invocable", True),
    "model-cagirmasin": ("model_invocable", True),
    "user-invocable": ("user_invocable", False),
    "kullanici-cagirabilir": ("user_invocable", False),
}

#: Araç listesi alanları: anahtar → alan adı.
_TOOL_LIST_KEYS: dict[str, str] = {
    "tools": "tools",
    "araclar": "tools",
    "allowed-tools": "allowed_tools",
    "allowedtools": "allowed_tools",
    "izinli-araclar": "allowed_tools",
    "disallowed-tools": "disallowed_tools",
    "disallowedtools": "disallowed_tools",
    "yasak-araclar": "disallowed_tools",
}

#: Araç olmayan liste alanları (P-034): `tools` ile aynı yazımlar (`[a, b]`, `a, b`, `- a`).
#: Boş liste "hiç yazılmamış" ile aynıdır; `NO_TOOLS` yalnız araç kısıtında anlamlıdır.
_PLAIN_LIST_KEYS: dict[str, str] = {
    "skills": "skills",
    "beceriler": "skills",
    "mcpservers": "mcp_servers",
    "mcp-servers": "mcp_servers",
}

_BLOCK_SCALARS = frozenset({">", "|", ">-", "|-", ">+", "|+"})
_TRUE_WORDS = frozenset({"true", "yes", "evet", "1", "on"})


def parse_frontmatter(text: str) -> dict[str, object]:
    """`---` blokları arasındaki alanları oku; frontmatter yoksa ya da bozuksa boş sözlük."""
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
        if not separator or lines[index - 1][:1] in " \t":
            continue
        name = key.strip().lower().replace("_", "-")
        if name in _TOOL_LIST_KEYS or name in _PLAIN_LIST_KEYS:
            # `tools:` + alt satırlarda `- Read` blok listesi YAML'ın olağan yazımıdır;
            # `skills`, `mcpServers`, `disallowedTools` aynı yazımları paylaşır.
            items = list(parse_tools(value.strip()))
            while not value.strip() and index < len(lines) and _is_list_item(lines[index]):
                items.append(_list_item(lines[index]))
                index += 1
            cleaned = tuple(item for item in items if item)
            if name in _TOOL_LIST_KEYS:
                fields[_TOOL_LIST_KEYS[name]] = cleaned or NO_TOOLS
            else:
                fields[_PLAIN_LIST_KEYS[name]] = cleaned
        elif name == "hooks":
            # İç içe blok: `hooks:` altındaki girintili `PreToolUse:` gibi anahtarlar olay
            # adlarıdır; gövdeleri (matcher/komut) burada yorumlanmaz.
            index, fields["hooks"] = _hook_events(lines, index)
        elif name in ("name", "description"):
            text_value = value.strip()
            if text_value in _BLOCK_SCALARS:
                # YAML blok skaleri: girintili satırlar değerdir (`>` birleştirir, `|` korur).
                block: list[str] = []
                while index < len(lines) and (
                    not lines[index].strip() or lines[index][:1] in " \t"
                ):
                    block.append(lines[index].strip())
                    index += 1
                joiner = " " if text_value.startswith(">") else "\n"
                fields[name] = joiner.join(part for part in block if part).strip()
            else:
                fields[name] = text_value.strip("'\"")
        elif name in _PERSONA_KEYS:
            fields[_PERSONA_KEYS[name]] = value.strip().strip("'\"")
        elif name in _TEXT_KEYS:
            fields[_TEXT_KEYS[name]] = value.strip().strip("'\"")
        elif name in AGENT_SETTING_KEYS:
            fields[AGENT_SETTING_KEYS[name]] = value.strip().strip("'\"")
        elif name in _BOOL_KEYS:
            field_name, invert = _BOOL_KEYS[name]
            truthy = value.strip().strip("'\"").lower() in _TRUE_WORDS
            fields[field_name] = (not truthy) if invert else truthy
    fields.update(_structured_agent_fields(stripped[3:end]))
    return fields


def _hook_events(lines: list[str], index: int) -> tuple[int, tuple[str, ...]]:
    """`hooks:` altındaki girintili blokta olay adlarını topla; bloğun bittiği satırı döndür."""
    events: list[str] = []
    while index < len(lines) and (not lines[index].strip() or lines[index][:1] in " \t"):
        line = lines[index].strip()
        if line and not line.startswith("-") and ":" in line and lines[index][:1] in " \t":
            indent = len(lines[index]) - len(lines[index].lstrip())
            if indent <= 2 or not events:
                events.append(line.partition(":")[0].strip().strip("'\""))
        index += 1
    return index, tuple(dict.fromkeys(event for event in events if event))


def _is_list_item(line: str) -> bool:
    return line.lstrip().startswith("-") and not line.lstrip().startswith("---")


def _list_item(line: str) -> str:
    """`  - 'Read'   # açıklama` → `Read`."""
    body = line.lstrip()[1:].split(" #", 1)[0]
    return body.strip().strip("'\"")


def parse_tools(value: str) -> tuple[str, ...]:
    """`tools:` alanını oku: `[a, b]`, `a, b`, `a b` ya da `'*'` biçimlerini destekler.

    Açık Agent Skills standardı `allowed-tools: Read Grep` (boşluk) yazar, Claude Code
    `Read, Grep`; `Bash(git add:*, git commit:*)` içindeki virgül/boşluk ayırıcı değildir.
    Ölçüldü (31 Ekim): yalnız virgülle bölünüyor, `Read Grep` tek ad sayılıp hiçbir araca
    eşlenmiyordu.
    """
    if value in ("'*'", '"*"', "*"):
        return ("*",)
    inner = value[1:-1] if value.startswith("[") and value.endswith("]") else value
    return tuple(item.strip().strip("'\"") for item in split_tool_names(inner) if item.strip())


def split_tool_names(text: str) -> list[str]:
    """Parantez dışındaki virgül ve boşluklarda böl."""
    items: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if depth == 0 and (char == "," or char.isspace()):
            if current:
                items.append("".join(current))
                current = []
            continue
        current.append(char)
    if current:
        items.append("".join(current))
    return items


def body_after_frontmatter(text: str) -> str:
    """Frontmatter sonrası gövde; frontmatter yoksa metnin kendisi."""
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return text
    end = stripped.find("\n---", 3)
    return text if end == -1 else stripped[end + 4 :].lstrip()


def _structured_agent_fields(frontmatter: str) -> dict[str, object]:
    """İç içe YAML alanlarını güvenli ayrıştır; bozuk tanım hiçbir komut açmaz."""
    try:
        raw = yaml.safe_load(frontmatter)
    except yaml.YAMLError:
        _LOG.warning("Ajanın yapılandırılmış frontmatter alanları geçersiz YAML; uygulanmadı.")
        return {}
    if not isinstance(raw, dict):
        return {}
    fields = normalize_agent_fields(raw)
    # Dosya blok skalerinin kapanış satırsonunu eski katalog sözleşmesi gibi kırp.
    description = fields.get("description")
    if isinstance(description, str):
        fields["description"] = description.rstrip("\n")
    return fields


def normalize_agent_fields(raw: Mapping[str, object]) -> dict[str, object]:
    """Dosya YAML'ı ve doğrulanmış CLI JSON'u için aynı tools-içi alan dönüşümü."""
    fields: dict[str, object] = {}
    for key, value in raw.items():
        name = key.lower().replace("_", "-")
        if name in {"name", "description"} and isinstance(value, str):
            fields[name] = value
        elif name in _PERSONA_KEYS and isinstance(value, str):
            fields[_PERSONA_KEYS[name]] = value
        elif name in _TEXT_KEYS and isinstance(value, str):
            fields[_TEXT_KEYS[name]] = value
        elif name in AGENT_SETTING_KEYS:
            fields[AGENT_SETTING_KEYS[name]] = str(value)
        elif name in _TOOL_LIST_KEYS or name in _PLAIN_LIST_KEYS:
            items = _normalized_list(value)
            if name in _TOOL_LIST_KEYS:
                fields[_TOOL_LIST_KEYS[name]] = items or NO_TOOLS
            elif name not in {"mcpservers", "mcp-servers"}:
                fields[_PLAIN_LIST_KEYS[name]] = items
        elif name in _BOOL_KEYS:
            target, invert = _BOOL_KEYS[name]
            truthy = value is True or (isinstance(value, str) and value.lower() in _TRUE_WORDS)
            fields[target] = not truthy if invert else truthy
    fields.update(_agent_metadata_fields(raw))
    return fields


def _normalized_list(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return parse_tools(value)
    if isinstance(value, list | tuple):
        return tuple(item for item in value if isinstance(item, str) and item)
    return ()


def _agent_metadata_fields(raw: Mapping[str, object]) -> dict[str, object]:
    """Yapılandırılmış metadata yalnız tools sınırından tipli nesnelerle çıkar."""
    fields: dict[str, object] = {}
    initial = raw.get("initialPrompt", raw.get("initial-prompt", ""))
    if isinstance(initial, str):
        fields["initial_prompt"] = initial
    fields["omit_claude_md"] = raw.get("omitClaudeMd", False) is True
    block = raw.get("hooks")
    if "hooks" in raw:
        commands, skipped = parse_hooks_block(
            block, source="", path=Path(), default_timeout_s=MAX_HOOK_TIMEOUT_S
        )
        fields["hook_definitions"] = HookSet(commands=commands, skipped=skipped)
        fields["hooks"] = tuple(str(event) for event in block) if isinstance(block, dict) else ()
    servers = raw.get("mcpServers", raw.get("mcp-servers"))
    if isinstance(servers, list):
        fields.update(_inline_mcp_fields(servers))
    elif isinstance(servers, str):
        fields["mcp_servers"] = parse_tools(servers)
    return fields


def _inline_mcp_fields(raw: list[object]) -> dict[str, object]:
    """Ad başvurusu ile inline MCP tanımını mevcut .mcp.json çözümleyicisinden geçir."""
    names: list[str] = []
    definitions: list[McpServerConfig] = []
    for item in raw:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            for name, entry in item.items():
                try:
                    parsed = parse_project_mcp({"mcpServers": {str(name): entry}})
                except ConfigError:
                    _LOG.warning(
                        "Ajanın inline MCP tanımı desteklenmiyor veya geçersiz; uygulanmadı."
                    )
                    continue
                names.append(str(name))
                definitions.extend(parsed)
    return {"mcp_servers": tuple(names), "inline_mcp_servers": tuple(definitions)}

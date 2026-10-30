"""SKILL.md / agent frontmatter ayrıştırıcısı — elle yazılmış küçük bir YAML alt kümesi.

Tam YAML bağımlılığı gereksizdir ve bozuk bir frontmatter tüm keşfi düşürmemelidir: hata
yerine boş sözlük döner. Claude Code'un skill alanları Türkçe ve İngilizce anahtarla okunur
(P-020): `allowed-tools`, `model`, `effort`, `context: fork`, `disable-model-invocation`,
`user-invocable`, `argument-hint`, `when_to_use`. Ajanlar için `tools` ve kişilik alanları.
"""

from __future__ import annotations

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
    "context": "context",
    "baglam": "context",
    "argument-hint": "argument_hint",
    "arguman-ipucu": "argument_hint",
    "when-to-use": "when_to_use",
    "ne-zaman": "when_to_use",
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
    "allowed-tools": "allowed_tools",
    "izinli-araclar": "allowed_tools",
    "disallowed-tools": "disallowed_tools",
    "yasak-araclar": "disallowed_tools",
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
        if name in _TOOL_LIST_KEYS:
            # `tools:` + alt satırlarda `- Read` blok listesi YAML'ın olağan yazımıdır.
            items = list(parse_tools(value.strip()))
            while not value.strip() and index < len(lines) and _is_list_item(lines[index]):
                items.append(_list_item(lines[index]))
                index += 1
            fields[_TOOL_LIST_KEYS[name]] = tuple(item for item in items if item) or NO_TOOLS
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
        elif name in _BOOL_KEYS:
            field_name, invert = _BOOL_KEYS[name]
            truthy = value.strip().strip("'\"").lower() in _TRUE_WORDS
            fields[field_name] = (not truthy) if invert else truthy
    return fields


def _is_list_item(line: str) -> bool:
    return line.lstrip().startswith("-") and not line.lstrip().startswith("---")


def _list_item(line: str) -> str:
    """`  - 'Read'   # açıklama` → `Read`."""
    body = line.lstrip()[1:].split(" #", 1)[0]
    return body.strip().strip("'\"")


def parse_tools(value: str) -> tuple[str, ...]:
    """`tools:` alanını oku: `[a, b]`, `a, b` ya da `'*'` biçimlerini destekler."""
    if value in ("'*'", '"*"', "*"):
        return ("*",)
    inner = value[1:-1] if value.startswith("[") and value.endswith("]") else value
    return tuple(item.strip().strip("'\"") for item in inner.split(",") if item.strip())


def body_after_frontmatter(text: str) -> str:
    """Frontmatter sonrası gövde; frontmatter yoksa metnin kendisi."""
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return text
    end = stripped.find("\n---", 3)
    return text if end == -1 else stripped[end + 4 :].lstrip()

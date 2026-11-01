"""Çıktı stilleri (P-068): `/output-style` — Claude Code output styles karşılığı.

Yerleşik stiller paket verisidir (`prompts/cikti_stilleri/*.md`); özel stiller kullanıcı ve
proje dizinlerinden okunur (`~/.fusion/cikti-stilleri`, `~/.claude/output-styles`,
`.fusion/cikti-stilleri`, `.claude/output-styles`). Dosya biçimi Claude Code ile aynıdır:
frontmatter `name`/`description`, gövde stil talimatı. Seçilen stilin gövdesi sistem
istemine kodlama talimatlarından SONRA eklenir (`loop._run_agent` extra_system zinciri);
`default` hiçbir şey eklemez. Bağlam sıkıştırma özeti stilden bağımsızdır (kendi istemi).

`keep-coding-instructions: false` Claude Code'da kodlama talimatını çıkarır; Fusion'ın
kimlik/araç sözleşmesi çıkarılamaz, bu yüzden alan OKUNUR ama yalnız listede işaretlenir.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from pathlib import Path

from ...config.models import Config
from ...config.trust import resolve_project_trust
from ...tools.capabilities import parse_frontmatter
from ...tools.plugin_capabilities import plugin_output_style_dirs

_LOG = logging.getLogger(__name__)

#: Yerleşik stil dosyalarının dizini.
BUILTIN_DIR = Path(__file__).parent / "prompts" / "cikti_stilleri"
#: Hiçbir talimat eklemeyen stil (Claude Code `default`).
DEFAULT_STYLE = "default"
#: Claude Code yerleşik adları: default, Proactive, Concise, Explanatory, Learning (#193).
#: Fusion'ın eski Türkçe adları bir sürüm boyunca kullanımdan kalkmış takma addır.
LEGACY_STYLE_ALIASES = {
    "varsayilan": "default",
    "varsayılan": "default",
    "ozlu": "concise",
    "özlü": "concise",
    "aciklayici": "explanatory",
    "açıklayıcı": "explanatory",
    "ogretici": "learning",
    "öğretici": "learning",
}
_WARNED_ALIASES: set[str] = set()


def canonical_style_name(name: str) -> str:
    """Stil adını küçük harfe indir; eski Türkçe adı Claude adına çevir (bir kez uyarır).

    Claude Code'da `/output-style` büyük/küçük harf duyarsızdır; Fusion ayarı da öyle okunur.
    """
    wanted = name.strip().lower()
    canonical = LEGACY_STYLE_ALIASES.get(wanted)
    if canonical is None:
        return wanted
    if wanted not in _WARNED_ALIASES:
        _WARNED_ALIASES.add(wanted)
        _LOG.warning("çıktı stili '%s' kullanımdan kalktı; '%s' kullanın", wanted, canonical)
    return canonical
#: Kullanıcı/proje köküne göre özel stil dizinleri (öncelik sırası: sonraki öncekini ezer).
CUSTOM_DIRS = (".fusion/cikti-stilleri", ".claude/output-styles")
#: Bir stil gövdesinin sistem istemine alınacak en fazla karakteri.
STYLE_MAX_CHARS = 6_000


@dataclass(frozen=True, slots=True)
class OutputStyle:
    name: str
    description: str
    prompt: str
    #: `yerleşik` | `kullanıcı` | `proje`
    source: str
    keep_coding_instructions: bool = True


_KEEP_FALSE = re.compile(
    r"^\s*keep-coding-instructions\s*:\s*false\s*$", re.IGNORECASE | re.MULTILINE
)


def _frontmatter(text: str) -> str:
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return ""
    end = stripped.find("\n---", 3)
    return "" if end == -1 else stripped[3:end]


def _body(text: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith("---"):
        end = stripped.find("\n---", 3)
        if end != -1:
            stripped = stripped[end + 4 :]
    return stripped.strip()


def _load(path: Path, source: str) -> OutputStyle | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fields = parse_frontmatter(text)
    name = str(fields.get("name") or path.stem).strip().lower()
    # `parse_frontmatter` yalnız ad/açıklama okur; bu bayrak frontmatter bloğundan ayrıca süzülür.
    keep = _KEEP_FALSE.search(_frontmatter(text)) is None
    return OutputStyle(
        name=name,
        description=str(fields.get("description") or ""),
        prompt=_body(text)[:STYLE_MAX_CHARS],
        source=source,
        keep_coding_instructions=keep,
    )


def _scan(directory: Path, source: str) -> list[OutputStyle]:
    try:
        files = sorted(directory.glob("*.md"))
    except OSError:
        return []
    return [style for style in (_load(path, source) for path in files) if style is not None]


def discover_styles(home: Path | None, root: Path | None) -> tuple[OutputStyle, ...]:
    """Yerleşik + özel stiller; aynı ad varsa güvenilen projede proje > kullanıcı > yerleşik.

    Ölçüldü (31 Ekim): proje `.claude/output-styles/ozlu.md` yerleşik `ozlu`yu (artık `concise`) eziyordu;
    kötü niyetli depo kullanıcının seçtiği zararsız stilin yerine kendi talimatını sistem
    istemine sokabiliyordu. Güven kaydı olmayan projenin stili yerleşik/kullanıcı adını
    GÖLGELEYEMEZ (yeni adlar yine listelenir); `fusion trust` sonrası Claude Code sırası.
    """
    found: dict[str, OutputStyle] = {}
    for style in _scan(BUILTIN_DIR, "yerleşik"):
        found[style.name] = style
    for base, source in ((home, "kullanıcı"), (root, "proje")):
        if base is None:
            continue
        shadow_allowed = source != "proje" or _project_trusted(base)
        for relative in CUSTOM_DIRS:
            for style in _scan(base / relative, source):
                if not shadow_allowed and style.name in found:
                    _LOG.warning(
                        "proje çıktı stili '%s' güven kaydı olmadan %s stilini gölgeleyemez: %s",
                        style.name,
                        found[style.name].source,
                        base / relative,
                    )
                    continue
                found[style.name] = style
    # Eklenti stilleri (P-059) `eklenti:ad` önekiyle eklenir; kimsenin adını gölgelemez.
    for plugin, path in plugin_output_style_dirs():
        loaded = _load(path, "eklenti")
        if loaded is not None:
            prefixed = replace(loaded, name=f"{plugin}:{loaded.name}")
            found.setdefault(prefixed.name, prefixed)
    return tuple(found.values())


def _project_trusted(root: Path) -> bool:
    try:
        return resolve_project_trust(root).trusted
    except Exception:  # güven kaydı okunamazsa güvenilmez sayılır
        return False


def find_style(name: str, home: Path | None, root: Path | None) -> OutputStyle | None:
    wanted = canonical_style_name(name)
    return next((style for style in discover_styles(home, root) if style.name == wanted), None)


def style_prompt(config: Config, *, home: Path | None, root: Path | None) -> str:
    """Seçili stilin sistem istemine eklenecek metni; varsayılan ya da bulunamayan stilde boş."""
    name = str(getattr(config.runtime, "output_style", DEFAULT_STYLE) or DEFAULT_STYLE)
    if canonical_style_name(name) == DEFAULT_STYLE:
        return ""
    style = find_style(name, home, root)
    if style is None:
        _LOG.warning("çıktı stili bulunamadı, varsayılan kullanılıyor: %s", name)
        return ""
    return style.prompt

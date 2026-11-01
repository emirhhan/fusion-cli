"""Çıktı stilleri (P-068): `/output-style` — Claude Code output styles karşılığı.

Yerleşik stiller paket verisidir (`prompts/cikti_stilleri/*.md`); özel stiller kullanıcı ve
proje dizinlerinden okunur (`~/.fusion/cikti-stilleri`, `~/.claude/output-styles`,
`.fusion/cikti-stilleri`, `.claude/output-styles`). Dosya biçimi Claude Code ile aynıdır:
frontmatter `name`/`description`, gövde stil talimatı. Seçilen stilin gövdesi sistem
istemine kodlama talimatlarından SONRA eklenir (`loop._run_agent` extra_system zinciri);
`default` hiçbir şey eklemez. Bağlam sıkıştırma özeti stilden bağımsızdır (kendi istemi).

Claude Code ile aynı (#215): özel stil `keep-coding-instructions: true` demedikçe sistem
isteminin yazılım mühendisliği bölümleri (`# Kod değişiklikleri`, `# Doğrulama`) çıkarılır;
yerleşik stiller bu bölümleri korur. Eklenti stili `force-for-plugin: true` ise kullanıcı
seçimini ezer (ilk yüklenen kazanır). Seçim Claude katmanlarındaki `outputStyle` alanından
okunur (`~/.claude/settings.json` < proje `.claude/settings.json` < `.claude/settings.local.json`;
değer büyük/küçük harf duyarlı, eşleşmeyen değer `default` olur); Fusion'ın eski
`runtime.output_style` ayarı yalnız hiçbir katmanda `outputStyle` yokken okunur. Proje
stilleri çalışma dizini ile depo kökü arasındaki her `.claude/output-styles`'tan yüklenir;
aynı adda çalışma dizinine en yakın olan kazanır.
"""

from __future__ import annotations

import json
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
    #: Frontmatter'daki adın özgün yazımı (`outputStyle` ayarı bununla tam eşleşir).
    display: str = ""
    #: Eklenti stili, etkin eklentide kendiliğinden uygulanır (`force-for-plugin`).
    force_for_plugin: bool = False


def _flag(name: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*{name}\s*:\s*true\s*$", re.IGNORECASE | re.MULTILINE)


_KEEP_TRUE = _flag("keep-coding-instructions")
_FORCE_TRUE = _flag("force-for-plugin")
#: Sistem isteminin yazılım mühendisliği bölümleri (Claude Code "software engineering
#: instructions"); özel stil `keep-coding-instructions: true` demedikçe çıkarılır.
CODING_SECTIONS = ("# Kod değişiklikleri", "# Doğrulama")
#: Claude ayar katmanlarındaki alan adı.
SETTING_KEY = "outputStyle"


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
    display = str(fields.get("name") or path.stem).strip()
    # `parse_frontmatter` yalnız ad/açıklama okur; bayraklar frontmatter bloğundan süzülür.
    # Claude Code: `keep-coding-instructions` varsayılanı false; yerleşikler korur.
    head = _frontmatter(text)
    keep = source == "yerleşik" or _KEEP_TRUE.search(head) is not None
    return OutputStyle(
        name=display.lower(),
        description=str(fields.get("description") or ""),
        prompt=_body(text)[:STYLE_MAX_CHARS],
        source=source,
        keep_coding_instructions=keep,
        display=display,
        force_for_plugin=source == "eklenti" and _FORCE_TRUE.search(head) is not None,
    )


def _scan(directory: Path, source: str) -> list[OutputStyle]:
    try:
        files = sorted(directory.glob("*.md"))
    except OSError:
        return []
    return [style for style in (_load(path, source) for path in files) if style is not None]


def discover_styles(home: Path | None, root: Path | None) -> tuple[OutputStyle, ...]:
    """Yerleşik + özel stiller; aynı ad varsa güvenilen projede proje > kullanıcı > yerleşik.

    Ölçüldü (31 Ekim): proje `.claude/output-styles/ozlu.md` yerleşik `ozlu`yu (artık
    `concise`) eziyordu;
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
        for directory in _style_dirs(base, source):
            for style in _scan(directory, source):
                if not shadow_allowed and style.name in found:
                    _LOG.warning(
                        "proje çıktı stili '%s' güven kaydı olmadan %s stilini gölgeleyemez: %s",
                        style.name,
                        found[style.name].source,
                        directory,
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


def _style_dirs(base: Path, source: str) -> list[Path]:
    """Taranacak dizinler; proje için depo kökünden çalışma dizinine (en yakın en son)."""
    if source != "proje":
        return [base / relative for relative in CUSTOM_DIRS]
    chain = [base]
    for parent in base.parents:
        if (chain[-1] / ".git").exists():
            break
        chain.append(parent)
    if not (chain[-1] / ".git").exists():
        chain = [base]  # depo yoksa yalnız çalışma dizini
    return [folder / relative for folder in reversed(chain) for relative in CUSTOM_DIRS]


def _project_trusted(root: Path) -> bool:
    try:
        return resolve_project_trust(root).trusted
    except Exception:  # güven kaydı okunamazsa güvenilmez sayılır
        return False


def find_style(name: str, home: Path | None, root: Path | None) -> OutputStyle | None:
    wanted = canonical_style_name(name)
    return next((style for style in discover_styles(home, root) if style.name == wanted), None)


def claude_setting(home: Path | None, root: Path | None) -> str | None:
    """Claude katmanlarındaki `outputStyle` (sonraki katman kazanır); hiçbirinde yoksa None."""
    layers: list[Path] = []
    if home is not None:
        layers.append(home / ".claude" / "settings.json")
    if root is not None:
        layers += [root / ".claude" / "settings.json", root / ".claude" / "settings.local.json"]
    value: str | None = None
    for path in layers:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as error:
            _LOG.debug("ayar okunamadı (%s): %s", path, type(error).__name__)
            continue
        found = data.get(SETTING_KEY) if isinstance(data, dict) else None
        if isinstance(found, str) and found.strip():
            value = found.strip()
    return value


def selected_style(config: Config, *, home: Path | None, root: Path | None) -> OutputStyle | None:
    """Etkin stil; `default` ya da bulunamayan stilde None."""
    styles = discover_styles(home, root)
    forced = next((style for style in styles if style.force_for_plugin), None)
    if forced is not None:
        return forced
    setting = claude_setting(home, root)
    if setting is not None:
        # Claude Code: değer büyük/küçük harf duyarlı; tam eşleşmeyen değer default'tur.
        return next((s for s in styles if s.display == setting and s.name != DEFAULT_STYLE), None)
    name = str(getattr(config.runtime, "output_style", DEFAULT_STYLE) or DEFAULT_STYLE)
    wanted = canonical_style_name(name)
    if wanted == DEFAULT_STYLE:
        return None
    style = next((s for s in styles if s.name == wanted), None)
    if style is None:
        _LOG.warning("çıktı stili bulunamadı, varsayılan kullanılıyor: %s", name)
    return style


def style_prompt(config: Config, *, home: Path | None, root: Path | None) -> str:
    """Seçili stilin sistem istemine eklenecek metni; varsayılan ya da bulunamayan stilde boş."""
    style = selected_style(config, home=home, root=root)
    return "" if style is None else style.prompt


def strip_coding_instructions(prompt: str) -> str:
    """Sistem isteminden yazılım mühendisliği bölümlerini çıkar (başlıktan sonraki `# `'e dek)."""
    kept: list[str] = []
    skipping = False
    for line in prompt.splitlines(keepends=True):
        if line.startswith("# "):
            skipping = line.strip() in CODING_SECTIONS
        if not skipping:
            kept.append(line)
    return "".join(kept)


def base_system_prompt(
    base: str, config: Config, *, home: Path | None, root: Path | None
) -> str | None:
    """Stil kodlama talimatını istemiyorsa kırpılmış temel istem; değişiklik yoksa None."""
    style = selected_style(config, home=home, root=root)
    if style is None or style.keep_coding_instructions:
        return None
    return strip_coding_instructions(base)

"""Sürüm notları (P-071) — `/release-notes`, `fusion release-notes`, masaüstü `surum.notlari`.

Kaynak TEK dosyadır: deponun `CHANGELOG.md`'si (Keep a Changelog; `## <başlık>` bölümleri).
Kaynak kodundan (geliştirme kurulumu, `pip install -e`, masaüstü paketinin kaynak ağacı)
çalışan Fusion dosyayı paketin iki üst dizininde bulur; paketli masaüstü çalışma zamanı
(PyInstaller onedir) onu `fusion_cli/`nin yanına, çalışma zamanı köküne koyar. Wheel'den
kurulan sürümde dosya yoktur; o zaman `RELEASES_URL` gösterilir — ikinci bir kopya
tutulmaz (RULES.md "Yapılandırma").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: Kaynak ağacındaki dosya adı.
CHANGELOG_NAME = "CHANGELOG.md"
#: Dosya yoksa yönlendirilen yayın sayfası (README ile aynı).
RELEASES_URL = "https://github.com/emirhhan/fusion-cli/releases"
#: Liste görünümünde en fazla bölüm.
MAX_SECTIONS = 30
#: Bir bölümden gösterilecek en fazla karakter (uzun "Yayımlanmamış" bölümü ekranı boğmasın).
MAX_SECTION_CHARS = 12_000

_HEADING = re.compile(r"^## +(.+?)\s*$", re.M)
_VERSION = re.compile(r"\[?v?(\d+\.\d+[\w.\-]*)\]?")
_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")

NOT_FOUND = "Sürüm notları bu kurulumda yok ({name} bulunamadı). Yayınlar: {url}"
NO_MATCH = "'{wanted}' için sürüm notu yok. Bilinenler: {known}"
TRIMMED = "\n[…kırpıldı; tamamı: {path}]"


@dataclass(frozen=True, slots=True)
class ReleaseSection:
    """CHANGELOG'daki tek `##` bölümü."""

    title: str
    #: Başlıktaki sürüm (`0.7.18`); "Yayımlanmamış" bölümlerinde boş.
    version: str
    date: str
    body: str


def changelog_path(package_dir: Path | None = None) -> Path | None:
    """Kaynak ağacındaki CHANGELOG; yoksa `None`."""
    base = package_dir or Path(__file__).resolve().parent.parent
    for candidate in (base.parent.parent / CHANGELOG_NAME, base.parent / CHANGELOG_NAME):
        if candidate.is_file():
            return candidate
    return None


def parse_changelog(text: str) -> tuple[ReleaseSection, ...]:
    """`## ` başlıklarına göre bölümle; başlık öncesi giriş metni atlanır."""
    matches = list(_HEADING.finditer(text))
    sections: list[ReleaseSection] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        title = match.group(1).strip()
        version = _VERSION.search(title)
        date = _DATE.search(title)
        sections.append(
            ReleaseSection(
                title,
                version.group(1) if version and not title.lower().startswith("yay") else "",
                date.group(1) if date else "",
                text[match.end() : end].strip(),
            )
        )
    return tuple(sections)


def find_section(sections: tuple[ReleaseSection, ...], wanted: str) -> ReleaseSection | None:
    """Sürüm (`0.7.18`), başlık parçası (`yayımlanmamış`) ya da boşsa en yeni bölüm."""
    query = wanted.strip().lower().lstrip("v")
    if not sections:
        return None
    if not query:
        return sections[0]
    exact = next((s for s in sections if s.version.lower() == query), None)
    if exact is not None:
        return exact
    return next((s for s in sections if query in s.title.lower()), None)


def load_sections(path: Path | None = None) -> tuple[ReleaseSection, ...] | None:
    """Dosyayı oku ve bölümle; dosya yoksa ya da okunamazsa `None`."""
    target = path or changelog_path()
    if target is None:
        return None
    try:
        return parse_changelog(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None


def render_section(section: ReleaseSection, path: Path | None = None) -> str:
    body = section.body
    if len(body) > MAX_SECTION_CHARS:
        body = body[:MAX_SECTION_CHARS] + TRIMMED.format(path=path or CHANGELOG_NAME)
    return f"## {section.title}\n\n{body}"


def release_notes_text(wanted: str = "", *, path: Path | None = None) -> str:
    """Tek bölümün metni ya da (`liste`) bölüm başlıkları; dosya yoksa yayın sayfası."""
    target = path or changelog_path()
    sections = load_sections(target)
    if sections is None:
        return NOT_FOUND.format(name=CHANGELOG_NAME, url=RELEASES_URL)
    if wanted.strip().lower() in {"liste", "list", "hepsi", "all"}:
        return "\n".join(f"- {s.title}" for s in sections[:MAX_SECTIONS])
    section = find_section(sections, wanted)
    if section is None:
        known = ", ".join(s.version for s in sections if s.version)[:400]
        return NO_MATCH.format(wanted=wanted, known=known)
    return render_section(section, target)

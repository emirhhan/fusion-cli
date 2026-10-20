"""Beceri ana yönergesi ve ek dosyaları için sınırlı sayfalama."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

SKILL_TEXT_BUDGET = 6_000


def load_skill_text(path: Path, budget: int = SKILL_TEXT_BUDGET) -> str:
    """Bir skill talimatının tam metnini oku."""
    try:
        return path.read_text(encoding="utf-8")[:budget]
    except OSError as exc:
        return f"HATA: skill okunamadı: {exc}"


def load_skill_page(path: Path, *, offset: int = 0, budget: int = SKILL_TEXT_BUDGET) -> str:
    """Skill talimatını sayfa sayfa ver; kesilen kısım AÇIKÇA bildirilir.

    Ölçüldü: bütçeyi aşan talimatın gerisi hiçbir işaret bırakmadan düşüyordu.
    Model eksik yönergeyi tam sanıp ilerliyor, atlanan bölümdeki zorunlu adım
    (proje kurulumu, dosya biçimi) hiç uygulanmıyordu. `read_file` ile aynı
    sözleşme: kesilen çıktı, devamının nasıl alınacağını da söyler.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"HATA: skill okunamadı: {exc}"
    start = max(0, offset)
    if start >= len(text) and text:
        return f"(skill {len(text)} karakter; offset={start} metnin sonundan sonra)"
    page = text[start : start + budget]
    remaining = len(text) - (start + len(page))
    if remaining <= 0:
        return page
    return (
        f"{page}\n\n[KIRPILDI: {remaining} karakter daha var. "
        f"Devamı için read_skill(offset={start + len(page)}).]"
    )


#: Skill ek dosyası olarak okunabilen uzantılar (metin). Görsel/ikili dosya verilmez.
#: Kod şablonları da metindir: Remotion/animasyon becerilerinin örnekleri .tsx/.css/.html
#: dosyalarında duruyor ve eskiden okunamıyordu.
_SKILL_TEXT_SUFFIXES = frozenset(
    {
        ".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".py", ".sh",
        ".ts", ".tsx", ".js", ".jsx", ".mjs", ".css", ".html", ".svg",
    }
)  # fmt: skip
#: Listelenecek en fazla ek dosya.
_MAX_SKILL_FILES = 40


def skill_files(skill_md: Path) -> list[str]:
    """SKILL.md yanındaki okunabilir ek dosyalar (skill klasörüne göreli)."""
    folder = skill_md.parent
    found = [
        path.relative_to(folder).as_posix()
        for path in sorted(folder.rglob("*"))
        if path.is_file() and path != skill_md and path.suffix.lower() in _SKILL_TEXT_SUFFIXES
    ]
    return found[:_MAX_SKILL_FILES]


def skill_file(skill_md: Path, relative: str) -> Path | None:
    """Ek dosyanın yolu; skill klasörü dışına çıkıyorsa ya da listede yoksa None."""
    folder = skill_md.parent.resolve()
    target = (folder / relative).resolve()
    if not target.is_relative_to(folder) or not target.is_file():
        return None
    return target if target.suffix.lower() in _SKILL_TEXT_SUFFIXES else None


@dataclass(frozen=True, slots=True)
class SkillPage:
    text: str
    revision: str
    offset: int
    next_offset: int | None
    error: str = ""


def read_skill_page(
    path: Path,
    *,
    offset: int = 0,
    revision: str = "",
    budget: int = SKILL_TEXT_BUDGET,
) -> SkillPage:
    """Tek snapshot üzerinden hash ile sayfayı bağla; eski devamı reddet."""
    try:
        payload = path.read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeError):
        return SkillPage("", "", offset, None, "Beceri dosyası okunamadı.")
    observed = hashlib.sha256(payload).hexdigest()
    if offset and revision != observed:
        return SkillPage(
            "", observed, offset, None, "Beceri sürümü değişti; offset=0 ile yeniden oku."
        )
    page = text[offset : offset + budget]
    next_offset = offset + len(page) if offset + len(page) < len(text) else None
    return SkillPage(page, observed, offset, next_offset)

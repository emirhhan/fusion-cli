"""Dar ve yüksek güvenli uzmanlık notu: görev türü kesin anlaşılınca kısa beceri özeti.

Ölçüldü: model becerileri kendisi çekmiyor (5.-17. koşuların 1.696 araç çağrısında
find_skill/read_skill 0; Hermes'in "Skills (mandatory)" istemi de aynı modelde 0
çağrı verdi). Öte yandan tur başına GENİŞ uzmanlık basmak geçmişte zarar verdi:
WEBSITE sanılan bir turda 21 KB'lık web referansı yanlış bağlam oldu (bkz.
`loop.py`). Bu yüzden burada:

- yalnız açık anahtar kelimeyle eşleşen TEK beceri seçilir (belirsizse hiçbiri),
- metin kısa tutulur (`MAX_EXPERTISE_CHARS`), tamamının yolu verilir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ...config.paths import bundled_skills_dir
from ...core.events import EventPublisher, SkillLoaded
from ...tools.capabilities import CapabilityRegistry
from ...tools.skill_pages import read_skill_page

#: Modele basılacak beceri metninin üst sınırı (karakter). Yerleşik beceriler bu
#: sınıra sığacak şekilde yazıldı (~3 KB); 21 KB'lık eski referansın yedide biri.
MAX_EXPERTISE_CHARS = 4_000


@dataclass(frozen=True, slots=True)
class _Rule:
    skill: str
    pattern: re.Pattern[str]
    exclude: re.Pattern[str] | None = None


#: Sıra önceliktir: ilk eşleşen kural kazanır (Remotion videosu da "animasyonlu"dur).
_RULES = (
    _Rule("remotion-video", re.compile(r"\bremotion\b", re.IGNORECASE)),
    _Rule(
        "html-oyun",
        re.compile(
            r"(?:\boyun|\bgame\b).{0,80}(?:html|canvas|tarayıcı|browser|web)"
            r"|(?:html|canvas|tarayıcı|browser|web).{0,80}(?:\boyun|\bgame\b)",
            re.IGNORECASE | re.DOTALL,
        ),
        exclude=re.compile(r"godot|unity|unreal", re.IGNORECASE),
    ),
    _Rule(
        "hareket",
        re.compile(r"animasyon|animated|animation|hareketli|motion design", re.IGNORECASE),
        exclude=re.compile(r"godot|video|remotion", re.IGNORECASE),
    ),
)


def _skill_body(folder: Path, name: str) -> str:
    try:
        metin = (folder / name / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    # Ön madde (--- … ---) modele gerekmez; adı ve yolu aşağıda verilir.
    govde = metin.split("---", 2)[-1].strip() if metin.startswith("---") else metin
    # Beceri yanındaki dosyalara (ör. remotion-video/kit) gerçek yolla başvurabilsin.
    govde = govde.replace("{SKILL_DIR}", str(folder / name))
    return govde[:MAX_EXPERTISE_CHARS]


def expertise_hint(
    task: str,
    skills_dir: Path | None = None,
    *,
    registry: CapabilityRegistry | None = None,
    publisher: EventPublisher | None = None,
) -> str | None:
    """Tek açık uzmanlığı gerçek katalog kaynağından, toplam sınır içinde yükle."""
    matches = [
        rule
        for rule in _RULES
        if rule.pattern.search(task) is not None
        and (rule.exclude is None or rule.exclude.search(task) is None)
    ]
    if len(matches) != 1:
        return None
    rule = matches[0]
    if registry is None:
        body = _skill_body(skills_dir or bundled_skills_dir(), rule.skill)
        if not body:
            return None
        prefix = f"UZMANLIK NOTU ({rule.skill} becerisi; tamamı read_skill('{rule.skill}')):\n"
        return (prefix + body)[:MAX_EXPERTISE_CHARS]
    skill = registry.get_skill(rule.skill)
    if skill is None:
        return None
    prefix = f"UZMANLIK NOTU ({skill.name}; tamamı read_skill('{skill.qualified_name}')):\n"
    page = read_skill_page(skill.path, budget=MAX_EXPERTISE_CHARS - len(prefix))
    if page.error or not page.text:
        return None
    body = page.text.replace("{SKILL_DIR}", str(skill.path.parent))
    prompt = (prefix + body)[:MAX_EXPERTISE_CHARS]
    if publisher is not None:
        publisher.publish(
            SkillLoaded(
                qualified_name=skill.qualified_name,
                revision=page.revision,
                mode="implicit",
                next_offset=page.next_offset,
            )
        )
    return prompt


def is_game_task(task: str) -> bool:
    """İstek bir tarayıcı oyunu mu (html-oyun becerisinin kuralıyla aynı karar)?"""
    kural = next(k for k in _RULES if k.skill == "html-oyun")
    if kural.pattern.search(task) is None:
        return False
    return kural.exclude is None or kural.exclude.search(task) is None


_DESKTOP_TASK = re.compile(
    r"masa(ü|u)st(ü|u)|pencere|arka\s*plan|finder|safari|takvim|notlar\b|uygulama(y(ı|i)|s(ı|i))?\b"
    r"|desktop|window|background app|bilgisayar(ım|im)?da|ekran(ı|i)?mda"
    r"|chatgpt|codex|claude|slack|whatsapp|telegram|spotify|vs\s*code|xcode|figma|canva|terminal\b"
    r"|\bmail\b|chrome|tarayıcı",
    re.IGNORECASE,
)


def is_desktop_task(task: str) -> bool:
    """İstek masaüstü penceresi/uygulaması üzerinde mi (arka plan araçlarını açar)?"""
    return _DESKTOP_TASK.search(task) is not None


def is_remotion_task(task: str) -> bool:
    """İstek bir Remotion videosu mu (remotion-video becerisinin kuralıyla aynı karar)?"""
    kural = next(k for k in _RULES if k.skill == "remotion-video")
    return kural.pattern.search(task) is not None

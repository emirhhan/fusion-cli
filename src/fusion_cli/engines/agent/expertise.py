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


def expertise_hint(task: str, skills_dir: Path | None = None) -> str | None:
    """Görev açıkça bir uzmanlık alanına aitse o becerinin kısa metni; değilse None."""
    klasor = skills_dir or bundled_skills_dir()
    for kural in _RULES:
        if kural.pattern.search(task) is None:
            continue
        if kural.exclude is not None and kural.exclude.search(task) is not None:
            continue
        govde = _skill_body(klasor, kural.skill)
        if not govde:
            return None
        return (
            f"UZMANLIK NOTU ({kural.skill} becerisi; tamamı read_skill('{kural.skill}')):\n{govde}"
        )
    return None


def is_game_task(task: str) -> bool:
    """İstek bir tarayıcı oyunu mu (html-oyun becerisinin kuralıyla aynı karar)?"""
    kural = next(k for k in _RULES if k.skill == "html-oyun")
    if kural.pattern.search(task) is None:
        return False
    return kural.exclude is None or kural.exclude.search(task) is None


def is_remotion_task(task: str) -> bool:
    """İstek bir Remotion videosu mu (remotion-video becerisinin kuralıyla aynı karar)?"""
    kural = next(k for k in _RULES if k.skill == "remotion-video")
    return kural.pattern.search(task) is not None

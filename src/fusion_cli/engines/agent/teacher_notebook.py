"""Öğretmen oturum günlüğü — `.fusion/ogretmen.md` (Faz 4, Görev 3).

`.fusion/tools` (bkz. `tools/forge.py`) ile aynı yerleşik dizin kuralını izler.
Bu dosya İNSAN-OKUNUR bir denetim günlüğüdür ve modele GERİ BESLENMEZ (plan §6.3)
— aranabilir/geri-çağrılabilir ders için `ChromaLessonMemory` kullanılır (bkz.
`teacher_lessons.sync_teacher_lesson`, ayrı ve açılır/kapanır bir yol). Bu günlük
her `ask_teacher` çağrısında YAZILIR; ders belleği eşitlemesi kapalı olsa bile.
"""

from __future__ import annotations

from pathlib import Path

#: `.fusion/tools` (`forge.py`) ile aynı kökte, aynı yazım biçiminde.
NOTEBOOK_PATH = ".fusion/ogretmen.md"

_HEADER = (
    "# Öğretmen günlüğü\n\n"
    "`ask_teacher` ile yapılan danışmaların kaydı. Bu dosya insan-okunurdur ve "
    "modele geri beslenmez.\n"
)


def append_entry(
    root: Path,
    *,
    timestamp: str,
    question: str,
    durum: str = "",
    answer: str,
    lesson_written: bool,
    lesson_skip_reason: str = "",
) -> Path:
    """Bir öğretmen danışmasını günlüğe ekle; dosyanın yolunu döndür."""
    hedef = root / NOTEBOOK_PATH
    hedef.parent.mkdir(parents=True, exist_ok=True)
    mevcut = hedef.read_text(encoding="utf-8") if hedef.exists() else _HEADER
    hedef.write_text(
        mevcut
        + _format_entry(
            timestamp=timestamp,
            question=question,
            durum=durum,
            answer=answer,
            lesson_written=lesson_written,
            lesson_skip_reason=lesson_skip_reason,
        ),
        encoding="utf-8",
    )
    return hedef


def _format_entry(
    *,
    timestamp: str,
    question: str,
    durum: str,
    answer: str,
    lesson_written: bool,
    lesson_skip_reason: str,
) -> str:
    parcalar = [f"\n## {timestamp}\n\n**Soru:** {question}\n"]
    if durum:
        parcalar.append(f"**Durum:** {durum}\n")
    parcalar.append(f"\n**Cevap:**\n\n{answer}\n")
    if lesson_written:
        parcalar.append("\n_Ders belleğe kaydedildi._\n")
    elif lesson_skip_reason:
        parcalar.append(f"\n_Ders belleğe kaydedilmedi: {lesson_skip_reason}_\n")
    return "".join(parcalar)

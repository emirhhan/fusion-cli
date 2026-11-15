"""Öğretmen oturum günlüğü — `.fusion/ogretmen.md` (Faz 4, Görev 3).

`.fusion/tools` (bkz. `tools/forge.py`) ile aynı yerleşik dizin kuralını izler.
Bu dosya İNSAN-OKUNUR bir denetim günlüğüdür ve modele GERİ BESLENMEZ (plan §6.3)
— aranabilir/geri-çağrılabilir ders için `ChromaLessonMemory` kullanılır (bkz.
`teacher_lessons.sync_teacher_lesson`, ayrı ve açılır/kapanır bir yol). Bu günlük
her `ask_teacher` çağrısında YAZILIR; ders belleği eşitlemesi kapalı olsa bile.
"""

from __future__ import annotations

from pathlib import Path

from ...core.redaction import redact

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
    advice_id: str = "",
) -> Path:
    """Bir öğretmen danışmasını günlüğe ekle; dosyanın yolunu döndür."""
    hedef = root / NOTEBOOK_PATH
    hedef.parent.mkdir(parents=True, exist_ok=True)
    # Soru/durum/cevap kod parçası ve sır taşıyabilir; `.fusion/` git'e eklenirse sızmasın
    # (A4-37). Ekleme kipi: her çağrıda tüm dosyayı okuyup yeniden yazmak O(n)'di, bozuk
    # UTF-8'de çöküyordu ve eşzamanlı eklemede kayıp veriyordu.
    giris = _format_entry(
        timestamp=timestamp,
        question=redact(question),
        durum=redact(durum),
        answer=redact(answer),
        lesson_written=lesson_written,
        lesson_skip_reason=redact(lesson_skip_reason),
        advice_id=redact(advice_id),
    )
    yeni = not hedef.exists()
    with hedef.open("a", encoding="utf-8", errors="replace") as dosya:
        dosya.write((_HEADER if yeni else "") + giris)
    return hedef


def _format_entry(
    *,
    timestamp: str,
    question: str,
    durum: str,
    answer: str,
    lesson_written: bool,
    lesson_skip_reason: str,
    advice_id: str = "",
) -> str:
    parcalar = [f"\n## {timestamp}\n\n**Soru:** {question}\n"]
    if advice_id:
        parcalar.append(f"**Tavsiye kimliği:** {advice_id}\n")
    if durum:
        parcalar.append(f"**Durum:** {durum}\n")
    parcalar.append(f"\n**Cevap:**\n\n{answer}\n")
    if lesson_written:
        parcalar.append("\n_Ders belleğe kaydedildi._\n")
    elif lesson_skip_reason:
        parcalar.append(f"\n_Ders belleğe kaydedilmedi: {lesson_skip_reason}_\n")
    return "".join(parcalar)


def append_outcome(root: Path, advice_id: str, refs: tuple[str, ...], written: bool) -> None:
    """Aynı tavsiye kaydına son doğrulama durumunu ekle."""
    status = "doğrulandı" if refs else "kullanım/sonuç bağı bilinmiyor"
    evidence = ", ".join(refs) or "yok"
    with (root / NOTEBOOK_PATH).open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(
            redact(
                f"\n**Tavsiye sonucu:** {advice_id}; {status}; "
                f"kanıt: {evidence}; ders yazıldı: {written}\n"
            )
        )

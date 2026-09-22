"""Öğretmen cevabını ders belleğine (opsiyonel) yaz — çakışma kontrolüyle.

Faz 4, Görev 3, §6.3 kararı: öğretmen dersleri VARSAYILAN olarak
`ChromaLessonMemory`'ye de yazılır (model `recall_lessons` ile geri
çağırabilsin), ama bu `runtime.teacher_lesson_sync` ile açılıp kapatılabilir.
İKİ PARALEL DERS SİSTEMİ açılmaz: `.fusion/ogretmen.md` (insan-okunur günlük,
`teacher_notebook.py`) ve bu modül AYNI kaynaktan (öğretmenin cevabı) beslenir
ama farklı amaçlar taşır — biri denetim, biri geri-çağrılabilir bellek.
"""

from __future__ import annotations

from ...core.memory import Lesson, LessonKind, LessonMemory, LessonSource

#: Bir ders metninde olumsuzlama/yasaklama işareti. Kaba bir sezgi: iki ders
#: AYNI konudan bahsediyorsa (`recall` zaten bunu garanti eder — yeterince
#: benzer olmasalar geri gelmezler) ama yalnız BİRİNDE bu işaretlerden biri
#: varsa, muhtemelen TERS yönde talimat veriyorlardır. Kusursuz değil — yanlış
#: pozitif/negatif üretebilir — ama sessizce çelişen iki dersi aynı anda
#: belleğe koymaktan daha güvenlidir. Belirsizlikte YAZILIR: ders belleğini
#: agresif biçimde kısırlaştırmaz.
_CATISMA_ISARETLERI = ("değil", "yapma", "kullanma", "etme", "asla", "sakın", "olmaz", "yanlış")

#: Ders metni olarak saklanacak öğretmen cevabının üst sınırı. Ders belleği kısa,
#: yordamsal dersler için tasarlanmıştır (bkz. `memory/lessons.py`); öğretmenin
#: tüm cevabını sınırsız saklamak onu uzun bir deneme metnine çevirir.
_LESSON_TEXT_LIMIT = 2_000


def sync_teacher_lesson(
    memory: LessonMemory, *, question: str, answer: str
) -> tuple[bool, str]:
    """Öğretmen cevabını derse çevirip belleğe yaz.

    `(yazıldı_mı, atlama_gerekçesi)` döner — gerekçe yalnız `yazıldı_mı=False`
    iken doludur ve `.fusion/ogretmen.md` günlüğüne + kullanıcıya bildirime
    aktarılır (bkz. çağıran yer, `engine_tools._ask_teacher_tool`).
    """
    metin = answer.strip()[:_LESSON_TEXT_LIMIT]
    if not metin:
        return False, "öğretmen boş cevap verdi"
    for aday in memory.recall(question, limit=3):
        if _olasi_catisma(metin, aday.text):
            kesit = aday.text[:80] + ("…" if len(aday.text) > 80 else "")
            return False, f"bellekteki bir dersle çelişebilir: {kesit!r}"
    yazildi = memory.add(
        Lesson(text=metin, kind=LessonKind.SUCCESS, task=question, source=LessonSource.TEACHER)
    )
    if not yazildi:
        return False, "aynı ders zaten kayıtlı"
    return True, ""


def _olasi_catisma(yeni: str, mevcut: str) -> bool:
    yeni_isaretli = any(k in yeni.lower() for k in _CATISMA_ISARETLERI)
    mevcut_isaretli = any(k in mevcut.lower() for k in _CATISMA_ISARETLERI)
    return yeni_isaretli != mevcut_isaretli

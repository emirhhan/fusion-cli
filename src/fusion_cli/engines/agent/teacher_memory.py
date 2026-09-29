"""Öğretmen planını sonucuyla birlikte ders belleğinde tut ve yeniden kullan.

İkinci bir bellek açılmaz: planlar mevcut `LessonMemory`'ye `LessonSource.TEACHER`
kaynağı ve `TEACHER_PLAN_SCOPE` kapsamıyla yazılır. Plan, öğretmen cevap verdiği
anda DEĞİL, tur bittiğinde ve yalnız tur gerçekten başarılıysa yazılır; böylece
denenmemiş ya da başarısız bir plan "başarılı ders" diye geri gelmez.
"""

from __future__ import annotations

import re
from dataclasses import replace

from ...core.memory import Lesson, LessonKind, LessonMemory, LessonSource
from .teacher_plan import TeacherPlan

#: Plan derslerini diğer derslerden ayıran kapsam. `recall(scope=...)` kapsamsız
#: genel dersleri de döndürdüğü için arama sonucu ayrıca bu değerle süzülür.
TEACHER_PLAN_SCOPE = "ogretmen-plani"

#: İki görevin aynı iş sayılması için gereken en düşük Jaccard benzerliği.
#:
#: Gerekçe: yanlış pozitif (farklı işe eski planı uygulamak) yanlış negatiften
#: (bir öğretmen çağrısı fazladan harcamak) pahalıdır; bu yüzden eşik "kök
#: kümelerinin en az yarısı ortak" düzeyinde tutuldu. Değer ölçülmüş bir optimum
#: değildir; `tests/test_teacher_memory.py::test_gorev_benzerligi_esigi` üç
#: örnekle (aynı iş farklı ekler → benzer; aynı proje başka iş ve aynı kalıpta
#: başka platform → benzer değil) sabitlenmiştir.
MIN_TASK_SIMILARITY = 0.5

#: Türkçe kök kırpma uzunluğu. Eklemeli dilde ilk beş harfe kırpma ("F5"),
#: Türkçe bilgi erişimi çalışmalarında (Can vd., 2008, JASIST) sözlüklü kök
#: bulucularla karşılaştırılabilir sonuç veren bilinen basit yöntemdir.
_STEM_CHARS = 5

#: Anlam taşımayan bağlaçlar. Kısa ve kapalı bir listedir; iş sözcüğü içermez.
_STOPWORDS = frozenset({"ile", "için", "veya", "gibi", "bir", "the", "and"})

#: Bu uzunluğun altındaki sözcükler ("ve", "de") benzerliğe katılmaz.
_MIN_TOKEN_CHARS = 3

#: Ders belleğindeki görev etiketi sınırı: `memory/lessons.py::MAX_LABEL_CHARS`
#: ile aynıdır; daha uzun etiket gömülmez ve anlamsal aramada kaybolur.
_TASK_LABEL_CHARS = 120

#: Geri çağırmada bakılan aday sayısı: benzerlik kararı burada verildiği için
#: belleğin varsayılan `limit=4`'ünden geniş, istem bütçesini etkilemeyecek kadar dar.
_RECALL_LIMIT = 8

_STEP_LINE = re.compile(r"^(\d+)\. (.+)$", re.MULTILINE)


def _stems(text: str) -> frozenset[str]:
    """Görevi yol/dosya adlarını bozmadan kök kümesine çevir."""
    stems: set[str] = set()
    for token in re.findall(r"[\w./-]+", text.lower()):
        token = token.strip("./-")
        if len(token) < _MIN_TOKEN_CHARS or token in _STOPWORDS:
            continue
        # Yol ve dosya adları olduğu gibi kalır; kırpılırsa farklı dosyalar eşleşir.
        stems.add(token if "/" in token or "." in token else token[:_STEM_CHARS])
    return frozenset(stems)


def task_similarity(first: str, second: str) -> float:
    """İki görev arasındaki kök kümesi Jaccard benzerliği (0..1)."""
    a, b = _stems(first), _stems(second)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def plan_lesson_text(plan: TeacherPlan) -> str:
    """Planı hem modelin okuyabileceği hem geri ayrıştırılabilir derse çevir."""
    lines = ["Doğrulanmış öğretmen planı:"]
    lines += [f"{index}. {step}" for index, step in enumerate(plan.steps, start=1)]
    if plan.files:
        lines.append("Dosyalar: " + ", ".join(plan.files))
    if plan.verification:
        lines.append("Doğrulama: " + "; ".join(plan.verification))
    return "\n".join(lines)


def plan_steps_from_lesson(text: str) -> tuple[str, ...]:
    """`plan_lesson_text` çıktısındaki numaralı adımları sırasıyla geri oku."""
    return tuple(match.group(2).strip() for match in _STEP_LINE.finditer(text))


def _task_label(task: str) -> str:
    return " ".join(task.split())[:_TASK_LABEL_CHARS]


def find_reusable_plan(
    memory: LessonMemory, task: str, *, workspace: str, tags: tuple[str, ...]
) -> tuple[Lesson, float] | None:
    """Başarıyla kaydedilmiş ve göreve yeterince benzer en iyi planı bul.

    Başarı sayısı başarısızlık sayısını geçmeyen plan kullanılmaz: hafızadaki
    plan bir kez tutmadığında bir sonraki benzer görevde öğretmene yeniden sorulur.
    """
    best: tuple[Lesson, float] | None = None
    for lesson in memory.recall(
        task, limit=_RECALL_LIMIT, scope=TEACHER_PLAN_SCOPE, workspace=workspace, tags=tags
    ):
        if lesson.source is not LessonSource.TEACHER or lesson.scope != TEACHER_PLAN_SCOPE:
            continue
        if lesson.success_count <= lesson.failure_count or not plan_steps_from_lesson(lesson.text):
            continue
        similarity = task_similarity(task, lesson.task)
        if similarity >= MIN_TASK_SIMILARITY and (best is None or similarity > best[1]):
            best = (lesson, similarity)
    return best


def record_plan_outcome(
    memory: LessonMemory,
    *,
    task: str,
    plan: TeacherPlan,
    success: bool,
    workspace: str,
    tags: tuple[str, ...],
    evidence: str = "",
) -> bool:
    """Başarılı turun planını yaz; aynı plan zaten varsa güvenini artır.

    Başarısız turun planı yazılmaz: denenip tutmamış bir plan ders değildir.
    """
    if not success or not plan.steps:
        return False
    lesson = Lesson(
        text=plan_lesson_text(plan),
        kind=LessonKind.SUCCESS,
        task=_task_label(task),
        source=LessonSource.TEACHER,
        scope=TEACHER_PLAN_SCOPE,
        # Tetikleyici alanı doğrulama kanıtını taşır; metne girseydi aynı plan
        # her turda farklı metin olur ve tekilleştirme çalışmazdı.
        trigger=evidence,
        workspace=workspace,
        tags=tags,
    )
    if memory.add(replace(lesson, success_count=1)):
        return True
    return memory.reinforce((lesson.text,), success=True) > 0

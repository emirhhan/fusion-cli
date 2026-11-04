"""Öğretmen öncesi görev kararı ve yapılandırılmış plan sözleşmesi."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..effects.detect import required_effect_for
from ..effects.model import EffectKind


@dataclass(frozen=True, slots=True)
class TeacherTaskDecision:
    """Öğretmene önceden danışmanın gerekli olup olmadığı."""

    size: str
    reasons: tuple[str, ...]


#: Görevde geçen dosya adları (uzantılı).
_FILE_REF = re.compile(r"[\w./-]+\.\w{1,5}\b")
#: Salt belge/metin dosyaları: bu dosyalardaki küçük düzenleme öğretmen planı gerektirmez.
_DOC_FILE = re.compile(
    r"(?:^|/)(?:readme|changelog|license|contributing)\b|\.(?:md|markdown|txt|rst)$", re.IGNORECASE
)
#: Görevin kendisi "küçük/tek satır" dediği düzenlemeler.
_SMALL_MARKER = re.compile(
    r"\b(?:bir|tek)\s+satır|yazım\s+hata|\btypo\b|\bküçük\s+(?:bir\s+)?(?:düzelt|değişiklik)",
    re.IGNORECASE,
)
#: Belge/küçük düzenleme sayılabilecek görevin en çok uzunluğu.
_SMALL_TASK_CHARS = 240


def _is_small_edit(task: str) -> bool:
    """Tek belge dosyası ya da açıkça "tek satır" denen küçük düzenleme mi?

    Ölçüldü (30 Ekim, A4-34): mutasyon etkisi TEK BAŞINA "orta-büyük" gerekçesiydi;
    "README'ye bir satır ekle" bile yavaş, kotalı öğretmen planı tetikliyordu.
    Yalnız belge dosyalarını hedefleyen ya da kendini küçük ilan eden kısa görevler
    öğretmensiz yürür; kaynak kod düzeltmesi (`src/app.py` hatası) eskisi gibi öğretmen
    planı alır.
    """
    if len(task) > _SMALL_TASK_CHARS or len(re.findall(r"(?m)^\s*\d+[.)]\s+", task)) > 1:
        return False
    files = {ref for ref in _FILE_REF.findall(task) if "." in ref.strip(".")}
    names_readme = bool(re.search(r"\b(?:readme|changelog)\b", task, re.IGNORECASE))
    if files:
        if all(_DOC_FILE.search(ref) for ref in files):
            return True
    elif names_readme:
        return True
    return len(files) <= 1 and bool(_SMALL_MARKER.search(task))


def classify_teacher_task(task: str) -> TeacherTaskDecision:
    """Mevcut etki kararı ile görevin yapısal kapsamını birlikte kullan."""
    mutation = EffectKind.WORKSPACE_MUTATION.value
    has_mutation = any(required_effect_for(part) == mutation for part in (task, *task.split(";")))
    reasons: list[str] = []
    if has_mutation and not _is_small_edit(task):
        reasons.append(f"istenen etki: {mutation}")
    # Dış API bağımlılığı ad listesinden tahmin edilmez: istek açıkça API
    # entegrasyonu söylüyorsa öğretmenin yapılabilirlik planı gereklidir.
    if re.search(r"\bAPI\b", task, re.IGNORECASE) and not task.strip().endswith("?"):
        reasons.append("dış API bağımlılığı")
    # Birden fazla numaralı madde, sözcük tahmini olmadan açık bir iş dizisidir.
    if len(re.findall(r"(?m)^\s*\d+[.)]\s+", task)) > 1:
        reasons.append("birden fazla açık adım")
    # Noktalama kapsam kanıtı değildir: "tarihi yaz; web araştırması yapma" gibi
    # kısa sorular da noktalı virgül taşır. Gerçek değişiklik etkisi ve açık
    # numaralı adımlar yukarıda bağımsız olarak değerlendirilir.
    return TeacherTaskDecision(
        size="orta-buyuk" if reasons else "basit",
        reasons=tuple(reasons),
    )


@dataclass(frozen=True, slots=True)
class UnworkablePart:
    """Dış kısıt yüzünden yapılamayan iş ve uygulanabilir yol."""

    topic: str
    reason: str
    alternative: str


@dataclass(frozen=True, slots=True)
class TeacherPlan:
    """Öğretmenin uygulanabilir ve doğrulanabilir görev planı."""

    steps: tuple[str, ...]
    files: tuple[str, ...]
    risks: tuple[str, ...]
    unworkables: tuple[UnworkablePart, ...]
    verification: tuple[str, ...]
    raw: str


class TeacherPlanError(ValueError):
    """Öğretmen yanıtı plan sözleşmesine uymuyor."""


#: Türkçe harfleri ASCII'ye katlar: prompt `adimlar` ister, gerçek LLM `adımlar` yazar.
_ASCII_FOLD = str.maketrans("ıİşŞçÇğĞöÖüÜ", "iissccggoouu")


def _fold_key(key: str) -> str:
    return key.strip().translate(_ASCII_FOLD).casefold()


def _fold_keys(value: dict[str, object]) -> dict[str, object]:
    return {_fold_key(str(key)): item for key, item in value.items()}


def _step_text(item: object) -> object:
    """`{"adim": "..."}` biçimindeki adım nesnesini metne çevir; diğerlerine dokunma."""
    if isinstance(item, dict):
        folded = _fold_keys(item)
        for key in ("adim", "aciklama", "metin", "step"):
            if isinstance(folded.get(key), str):
                return folded[key]
    return item


def _string_items(value: object, field: str, *, required: bool = False) -> tuple[str, ...]:
    # Opsiyonel alan öğretmen tarafından atlanabilir (boş kalan alan doğal olarak yazılmaz).
    if value is None and not required:
        return ()
    if not isinstance(value, list):
        raise TeacherPlanError(f"'{field}' metin dizisi olmalı.")
    raw = [_step_text(item) for item in value] if field == "adimlar" else list(value)
    texts = [item for item in raw if isinstance(item, str)]
    if len(texts) != len(raw):
        raise TeacherPlanError(f"'{field}' metin dizisi olmalı.")
    items = tuple(item.strip() for item in texts if item.strip())
    if required and not items:
        raise TeacherPlanError(f"'{field}' en az bir madde içermeli.")
    return items


def parse_teacher_plan(answer: str) -> TeacherPlan:
    """Önek ve kod çiti içinden ilk geçerli JSON planını ayıkla."""
    document = _json_document(answer, "adimlar")
    steps = _string_items(document.get("adimlar"), "adimlar", required=True)
    files = _string_items(document.get("dosyalar"), "dosyalar")
    risks = _string_items(document.get("riskler"), "riskler")
    verification = _string_items(document.get("dogrulama"), "dogrulama")
    raw_unworkables = document.get("yapilamayanlar", [])
    if raw_unworkables is None:
        raw_unworkables = []
    if not isinstance(raw_unworkables, list):
        raise TeacherPlanError("'yapilamayanlar' dizi olmalı.")
    unworkables: list[UnworkablePart] = []
    for item in raw_unworkables:
        item = _fold_keys(item) if isinstance(item, dict) else item
        if not isinstance(item, dict) or any(
            not isinstance(item.get(key), str) or not item[key].strip()
            for key in ("konu", "gerekce", "alternatif")
        ):
            raise TeacherPlanError("Yapılamayan iş için konu, gerekçe ve alternatif gerekli.")
        unworkables.append(
            UnworkablePart(
                topic=item["konu"].strip(),
                reason=item["gerekce"].strip(),
                alternative=item["alternatif"].strip(),
            )
        )
    return TeacherPlan(steps, files, risks, tuple(unworkables), verification, answer)


def _json_document(answer: str, marker: str) -> dict[str, object]:
    """Açıklama ve kod çitleri arasındaki ilk uygun JSON nesnesini bul."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", answer):
        try:
            candidate, _end = decoder.raw_decode(answer[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            folded = _fold_keys(candidate)
            if marker in folded:
                return folded
    raise TeacherPlanError(f"Öğretmen yanıtında '{marker}' alanlı JSON bulunamadı.")


def parse_teacher_review(answer: str) -> tuple[str, ...]:
    """Yalnız açık JSON bulgularını denetim sonucu kabul et."""
    document = _json_document(answer, "bulgular")
    return _string_items(document.get("bulgular"), "bulgular")

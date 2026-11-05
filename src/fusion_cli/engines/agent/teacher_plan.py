"""Öğretmen öncesi görev kararı ve yapılandırılmış plan sözleşmesi."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ...core.text_fold import fold_tr
from ..effects.detect import requested_web_urls, required_effect_for
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

# The exception needs affirmative scope and dependency constraints, not a task
# noun (such as "counter") or a model-size guess. Ambiguity keeps the old route.
_BOUNDED_TASK_CHARS = 1_000
_SINGLE_FILE = re.compile(
    r"\b(?:tek(?:\s+bir)?|bir)\s+(?:[\w+#-]+\s+){0,2}dosya(?:s[ıi])?\b|"
    r"\b(?:single|one)[-\s]+(?:[\w+#-]+[-\s]+){0,2}file\b"
)
_REJECTED_SINGLE_FILE = re.compile(
    r"\s+(?:olmasın|değil|yazma|oluşturma|kullanma|olsun\s+istemiyorum|is\s+not)\b"
)
_NO_EXTERNAL_DEPENDENCIES = re.compile(
    r"\b(?:harici|dış)\s+(?:hiçbir\s+)?(?:bağımlılık|kütüphane|paket)\w*\s+"
    r"(?:kullanma(?:dan)?|olmasın|yok)\b|"
    r"\b(?:sadece|yalnızca|yalnız)\s+standart\s+kütüphane\w*\s+kullan\b|"
    r"\b(?:no|without)\s+(?:any\s+)?(?:external\s+)?dependenc(?:y|ies)\b|"
    r"\b(?:only|just)\s+(?:the\s+)?standard\s+library\b"
)
_EXTERNAL_OR_EXPANDED_SCOPE = re.compile(
    r"\bapi\b|\bcdn\b|\bruntime\b|\bfetch\b|\bscript\b|\bstylesheet\b|"
    r"çalışma\s+zaman|her\s+açılış|veri\w*\s+(?:çek|getir|yükle)|"
    r"entegrasyon|entegre|integrat|veritaban|"
    r"\bdatabase\b|\bbackend\b|\bdeploy\w*|\bpublish(?:ing)?\b|"
    r"\byayına\s+(?:al|çıkar)\b|"
    r"\byay(?:ınla|ımla)(?:yın|yin|yalım|yalim|mak|mayı|mayi)?\b|"
    r"\byay(?:ınla|ımla)n(?:sın|sin|masını|masini)\b|"
    r"kimlik\s+doğrula|\bauthentication\b|\bauthorization\b|\blogin\b|"
    r"\bdosyalar\w*\b|\b(?:iki|üç|dört|two|three|multiple|several|[2-9])\s+"
    r"(?:[\w+#-]+\s+){0,2}(?:dosya|files?)\w*\b"
)
_EXPLICIT_TEACHER = re.compile(r"\bask_teacher\b|\böğretmen\w*|\bteacher\b|\bmentor\b")

# A brief static document has an output boundary without requiring users to
# spell out implementation constraints. Features and extra operations do not.
_BRIEF_REPORT = re.compile(
    r"\b(?:kısa|özlü|short|brief|concise)\s+[^.;!?\n]{0,80}\b(?:rapor\w*|report)\b"
)
_REJECTED_BRIEF_REPORT = re.compile(
    r"\b(?:not|never|do\s+not|don't)\b[^.;!?\n]{0,40}\b(?:short|brief|concise)\b|"
    r"\b(?:short|brief|concise)\s+[^.;!?\n]{0,80}\b(?:is\s+not|isn't|not\s+wanted)\b|"
    r"\b(?:kısa|özlü)\b[^.;!?\n]{0,80}\b(?:olmayan|olmasın|değil|istemiyorum|"
    r"hazırlama|oluşturma|yazma)\b"
)
_REPORT_EXPANDED_SCOPE = re.compile(
    r"\b(?:kapsamlı|ayrıntılı|detaylı|karmaşık|comprehensive|exhaustive|detailed|complex|"
    r"modüler|modular|refresh\w*|polling)\b|"
    r"\b(?:that|which|should|must)\s+fetch\w*\b|"
    r"\bon(?:\s+page)?\s*load\b|\b(?:uses?|using)\s+(?:the\s+)?fetch\b|"
    r"\b(?:whenever|when)\b[^.;!?\n]{0,40}\bpage\s+opens\b|"
    r"\b(?:cover\w*|across)\s+(?:all|every)\b|"
    r"\bevery\s+(?:second|minute|hour|day)\b|\bher\s+(?:saniye|dakika|saat|gün)\b|"
    r"\b(?:tüm|bütün|her)\b[^.;!?\n]{0,80}\b(?:kapsa|incele|analiz|karşılaştır)\w*|"
    r"\b(?:sil|kaldır|taşı|yeniden\s+adlandır|gönder|düzelt|değiştir)(?:in|iniz|sene|sin)?\b|"
    r"\b(?:delete|remove|rename|move|overwrite|send|upload|install|execute|fix|edit|refactor)\b"
)
_REPORT_FEATURE = (
    r"(?:etkileşimli|interactive|dashboard|oyun|game|uygulama|application|simulation|"
    r"simülasyon|grafik\w*|charts?|forms?|düğme\w*|buttons?)"
)
_REPORT_FEATURE_DIRECTIVE = re.compile(
    r"\b(?:etkileşimli|interactive)\s+(?:[\w-]+\s+){0,3}(?:rapor\w*|report)\b|"
    rf"\b(?:add|build|include|implement|create|with|showing|containing)\s+"
    rf"(?:(?!(?:about|of|on|report)\b)[\w-]+\s+){{0,6}}{_REPORT_FEATURE}\b|"
    rf"\b{_REPORT_FEATURE}\b\s+(?:(?!rapor\w*\b)[\w-]+\s+){{0,6}}"
    r"(?:ekle|kur|yap|oluştur|geliştir|olsun|içer)\w*\b|"
    r"(?:^|[.;!?]|\b(?:and|also|then)\b)\s*(?:please\s+)?"
    r"(?:implement|develop|replace|refactor)\b|"
    r"\b(?:ayrıca|ek\s+olarak)\b[^.;!?\n]{0,100}\b(?:geliştir|uygula|kodla|değiştir)\w*\b"
)
_STATIC_REPORT_FILE = re.compile(r"\.(?:html?|md|txt|rst)$")
_NON_HTTP_REPORT_SOURCE = re.compile(
    r"\b(?:file|ftp|sftp|data|javascript|mailto):|\b(?!https?://)[a-z][\w+.-]*://"
)

# Source domains and document paths are not workspace filenames.
_SOURCE_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'`]+", re.IGNORECASE)
_QUOTED_SCOPE = re.compile(
    r"```.*?```|`[^`]*`|\"[^\"\n]*\"|“[^”\n]*”|"
    r"(?<!\w)'[^'\n]+'(?!\w)|^[ \t]*>[^\n]*",
    re.S | re.M,
)
_REJECTED_DEPENDENCY_SCOPE = re.compile(r"\s+(?:demiyorum|demedim|istemi(?:yorum|yoruz)|değil)\b")


def _scope_text(task: str) -> str:
    """Quoted examples cannot supply affirmative scope; quoted paths still count."""

    def quoted(match: re.Match[str]) -> str:
        inner = match.group().strip("`\"“”'")
        if _FILE_REF.fullmatch(inner) or _SOURCE_URL.fullmatch(inner):
            return inner
        return " "

    return _QUOTED_SCOPE.sub(quoted, fold_tr(task))


def _source_urls_are_read_only(scope: str) -> bool:
    # Consultation and completion must agree about which URL is actually read.
    # Scheme-less WWW references remain ambiguous rather than granting the fast route.
    if any(match.group().startswith("www.") for match in _SOURCE_URL.finditer(scope)):
        return False
    return set(requested_web_urls(scope)) <= set(requested_web_urls(scope, source_reads_only=True))


def _is_short_static_report(task: str, scope: str, prose: str) -> bool:
    refs = tuple(_FILE_REF.finditer(scope))
    files = {ref.group() for ref in refs}
    static = {ref for ref in files if _STATIC_REPORT_FILE.search(ref)}
    if len(static) != 1 or _NON_HTTP_REPORT_SOURCE.search(fold_tr(task)):
        return False
    if not any(
        ref.group() in static and _report_output_target(scope[: ref.start()], scope[ref.end() :])
        for ref in refs
    ):
        return False
    for ref in refs:
        if ref.group() in static:
            continue
        # Dotted technology names and versions can be subjects, not extra files.
        before, after = scope[: ref.start()], scope[ref.end() :]
        if (
            re.fullmatch(r"\d+(?:\.\d+)+", ref.group())
            or re.search(r"\b(?:about|of|on)\s+(?:the\s+)?$", before)
            or re.match(
                r"[’'](?:s|n?[ıiuü]n)\b|\s+(?:[\w-]+\s+){0,4}(?:release|version|sürüm)\w*\b",
                after,
            )
        ):
            continue
        return False
    return bool(
        _BRIEF_REPORT.search(prose)
        and not _REJECTED_BRIEF_REPORT.search(prose)
        and not _REPORT_EXPANDED_SCOPE.search(prose)
        and not _REPORT_FEATURE_DIRECTIVE.search(prose)
        and required_effect_for(task) == EffectKind.WORKSPACE_MUTATION.value
    )


def _report_output_target(before: str, after: str) -> bool:
    """A source filename cannot stand in for an unspecified output target."""
    if re.match(
        r"\s+(?:(?:olarak|adıyla|dosya\w*)\s+){0,2}"
        r"(?:oluştur|hazırla|yaz|kaydet|aktar)(?!ma|me)\w*\b",
        after,
    ):
        return True
    destination = re.search(r"\b(?:as|to|into|in)\s+(?:the\s+)?$", before)
    input_boundary = r"read|from|using" + ("" if destination else r"|about|of")
    return bool(
        re.search(
            r"\b(?:create|write|generate|save|oluştur|hazırla|yaz|kaydet)\b"
            rf"(?:(?!\b(?:{input_boundary})\b)[^.;!?\n]){{0,160}}$",
            _FILE_REF.sub(" ", before),
        )
    )


def is_bounded_single_file_task(task: str) -> bool:
    """Short static reports or explicitly self-contained work can run directly.

    This changes consultation cost only. Tool permissions, actual verification,
    and optional teacher access are separate and stay unchanged.
    """
    if len(task) > _BOUNDED_TASK_CHARS:
        return False
    folded = _scope_text(task)
    single_file_scopes = tuple(_SINGLE_FILE.finditer(folded))
    dependency_scopes = tuple(_NO_EXTERNAL_DEPENDENCIES.finditer(folded))
    if any(_REJECTED_DEPENDENCY_SCOPE.match(folded, scope.end()) for scope in dependency_scopes):
        return False
    if not _source_urls_are_read_only(folded):
        return False
    # These common direct rejections contradict the affirmative scope required
    # by the fast route, even if an earlier sentence mentioned a single file.
    if any(_REJECTED_SINGLE_FILE.match(folded, scope.end()) for scope in single_file_scopes):
        return False
    folded = _SOURCE_URL.sub(" ", folded)
    prose = _FILE_REF.sub(" ", folded)
    if _EXPLICIT_TEACHER.search(prose):
        return False
    if len(re.findall(r"(?m)^\s*\d+[.)]\s+", task)) > 1:
        return False
    # "Fetch the source" is a read instruction, not a runtime dependency.
    # Actual runtime/cadence/features remain vetoes inside the report predicate.
    report_scope = (
        re.sub(r"\bfetch\b", " ", prose)
        if requested_web_urls(task, source_reads_only=True)
        else prose
    )
    if _is_short_static_report(task, folded, prose) and not _EXTERNAL_OR_EXPANDED_SCOPE.search(
        report_scope
    ):
        return True
    if _EXTERNAL_OR_EXPANDED_SCOPE.search(prose):
        return False
    return bool(
        single_file_scopes and dependency_scopes and len(set(_FILE_REF.findall(folded))) <= 1
    )


def is_short_static_report_task(task: str) -> bool:
    """Pure document scope, independent of teacher settings or executable app scope."""
    if not is_bounded_single_file_task(task):
        return False
    scope = _SOURCE_URL.sub(" ", _scope_text(task))
    return _is_short_static_report(task, scope, _FILE_REF.sub(" ", scope))


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
    files = {ref for ref in _FILE_REF.findall(_SOURCE_URL.sub(" ", task)) if "." in ref.strip(".")}
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
    if has_mutation and not (_is_small_edit(task) or is_bounded_single_file_task(task)):
        reasons.append(f"istenen etki: {mutation}")
    # Dış API bağımlılığı ad listesinden tahmin edilmez: istek açıkça API
    # entegrasyonu söylüyorsa öğretmenin yapılabilirlik planı gereklidir.
    if re.search(
        r"\bAPI\b", _SOURCE_URL.sub(" ", task), re.IGNORECASE
    ) and not task.strip().endswith("?"):
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

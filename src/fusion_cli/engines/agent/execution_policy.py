"""Sağlayıcıya göre agent yürütme bütçesi.

API sağlayıcılarının mevcut davranışı korunur. Tarayıcı/oturum tabanlı Web AI
sağlayıcılarında ise tek bir küçük görevin onlarca web isteğine dönüşmesini önlemek
için görev büyüklüğüne göre dinamik ama cömert üst sınırlar uygulanır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ...config.models import Config
from ...config.tool_policy import mutation_policy_for_model
from ...core.types import ModelSpec
from ..effects.detect import required_effect_for
from .classify import TaskKind

_WEB_PROVIDER_IDS = frozenset(
    {"chatgpt_web", "claude_web", "gemini_web", "copilot_web", "perplexity_web"}
)
_COMPLEX_KINDS = frozenset(
    {TaskKind.BUGFIX, TaskKind.REFACTOR, TaskKind.TEST, TaskKind.WEBSITE, TaskKind.FEATURE}
)
#: Değişiklik ürettiği kesin olan etki sözleşmeleri.
#
# Görev türü anahtar kelime SAYIMIYLA bulunur ve "incele ve eksikleri tamamla"
# gibi bir istekte keşif kelimeleri (incele) değişiklik kelimelerini bastırıp
# EXPLORE kazanabiliyor. O zaman görev 5 araç turu alıyor — bir projeyi tanımaya
# bile yetmez — ve yazmaya iten kapıların hiçbiri kurulmuyor.
#
# Etki tespiti bu boşluğu kapatır: metin gerçek bir değişiklik istiyorsa görev
# türü ne olursa olsun karmaşık bütçeye alınır.
_MUTATING_EFFECTS = frozenset(
    {"workspace_mutation", "shell_action", "git_push", "git_commit"}
)
_EXTENDED_MARKERS = (
    "kapsamlı",
    "kapsamli",
    "baştan sona",
    "bastan sona",
    "tüm proje",
    "tum proje",
    "derin araştır",
    "derin arastir",
    "eksiksiz",
    "tamamını",
    "tamamini",
)


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """Bir agent turunun sağlayıcıya özel davranış sınırları.

    ``None`` sınırın uygulanmadığı ve eski davranışın korunduğu anlamına gelir.
    """

    is_web: bool
    max_model_calls: int | None = None
    max_tool_rounds: int | None = None
    max_same_tool_without_change: int = 2
    total_timeout_s: float | None = None
    idle_timeout_s: float | None = None
    heuristic_auto_continue: bool = True
    conditional_self_review: bool = False
    learn_read_only_turns: bool = True
    offer_tools: bool = True
    # Gerçek dünya etkisi isteyen görevlerde modelin yalnızca “yapıyorum” demesini
    # başarı sayma. `required_effect` runtime tarafından başarılı araç kanıtıyla
    # doğrulanır; kanıt yoksa model bir kez araç çağrısına zorlanır.
    requires_tool_evidence: bool = False
    required_effect: str | None = None
    #: Görev türü kod değiştirmeyi gerektiren cinsten mi (BUGFIX, TEST, FEATURE…).
    #
    # `required_effect` metinden çıkarılır ve dar kalıplara bakar; "testleri geçir"
    # gibi bir görevde boş kalıyor. O zaman kanıt kapısı hiç kurulmuyor ve model
    # yalnızca okuyup düzyazıyla durunca tur bitmiş sayılıyordu (ölçüldü: üç
    # koşunun ikisi böyle düştü). Bu alan o boşluğu görev TÜRÜNDEN kapatır.
    complex_task: bool = False
    max_evidence_reprompts: int = 1
    # Bu modelin dosya/shell değiştirmesine izin var mı? Doğrulanmamış taklit-araç
    # modelleri (bkz. config.tool_policy) okur ve planlar ama değiştiremez.
    allow_mutation: bool = True
    #: İzin yoksa kullanıcıya ve modele gösterilecek gerekçe.
    mutation_block_reason: str = ""


def policy_for(config: Config, spec: ModelSpec, kind: TaskKind, task: str) -> ExecutionPolicy:
    """Seçilen model ve görev türü için yürütme politikasını döndür.

    Kısa mesaj otomatik olarak “sohbet” değildir. “Repoyu pushla”, “paketi kur” veya
    “dosyayı sil” gibi birkaç kelimelik görevler gerçek bir etki ister ve araçsız
    tamamlanamaz. Bu ayrım sağlayıcıdan bağımsızdır; Web AI tarafında ayrıca araç
    şemalarının yanlışlıkla kapatılmasını önler.
    """

    lowered = task.lower()
    explicit_no_tools = _explicit_no_tools(lowered)
    # Kullanıcı “araç kullanma” dese bile gerçek bir dış etki talebi ortadan
    # kalkmaz. Araçlar kapalı tutulur ama iş yapılmış gibi raporlanamaz.
    required_effect = required_effect_for(task, kind)
    requires_evidence = required_effect is not None
    # Yetenek kararı `strict` kısa devresinden BAĞIMSIZ verilir: panelden zorunlu
    # model seçmek güvenlik kapısını atlamak anlamına gelemez.
    mutation = mutation_policy_for_model(config, spec.model)

    if not is_web_model(config, spec.model):
        # API/local sağlayıcılarda hard-cap yok; fakat açık operasyonlarda kanıtsız
        # başarıya bütün sağlayıcılarda izin verilmez.
        return ExecutionPolicy(
            is_web=False,
            allow_mutation=mutation.ok,
            mutation_block_reason=mutation.reason,
            offer_tools=not explicit_no_tools,
            requires_tool_evidence=requires_evidence,
            required_effect=required_effect,
            max_evidence_reprompts=0 if explicit_no_tools else 1,
            complex_task=kind in _COMPLEX_KINDS or required_effect in _MUTATING_EFFECTS,
        )

    extended = any(marker in lowered for marker in _EXTENDED_MARKERS)
    # Tür ya da ETKİ: ikisinden biri değişiklik istiyorsa iş karmaşıktır.
    complex_task = kind in _COMPLEX_KINDS or required_effect in _MUTATING_EFFECTS
    simple_chat = _is_genuine_simple_chat(task, kind, required_effect)

    if extended:
        # Kullanıcı açıkça büyük iş istediğinde yeteneği erken kesme; yine de sonsuz
        # web çağrısına karşı emniyet supabı bırak.
        max_calls, max_rounds, timeout, idle_timeout = 36, 28, 2400.0, 300.0
    elif complex_task:
        # Ölçüldü: sözleşme artık yanıt başına TEK araç çağrısı ve var olan dosyada
        # toptan yazma yerine hedefli düzenleme istiyor. İkisi de tur sayısını mekanik
        # olarak artırır — dört dosyalık bir görev ~6 okuma + ~6 düzenleme + doğrulama
        # ile 14+ tur harcıyor. Eski 12 turluk sınır dört koşunun ikisini tam da iş
        # ilerlerken kesti ("araç turu sınırına ulaşıldı"). Sınır akışa uydurulur.
        max_calls, max_rounds, timeout, idle_timeout = 28, 22, 1800.0, 240.0
    else:
        max_calls, max_rounds, timeout, idle_timeout = 8, 5, 240.0, 120.0

    return ExecutionPolicy(
        is_web=True,
        allow_mutation=mutation.ok,
        mutation_block_reason=mutation.reason,
        max_model_calls=max_calls,
        max_tool_rounds=max_rounds,
        max_same_tool_without_change=2,
        total_timeout_s=timeout,
        idle_timeout_s=idle_timeout,
        # Web yanıtında kısa ama geçerli final metnini "yarım" sanıp fazladan
        # çağrı açma. Gerçek truncation ve bekleyen todo hâlâ devam ettirilir.
        heuristic_auto_continue=False,
        complex_task=complex_task,
        # Basit sohbet/keşifte denetçi çağrısı yapma; kod ve değişiklik işlerinde koru.
        conditional_self_review=True,
        # Salt-okuma web turlarından ayrı bir model çağrısıyla ders çıkarma.
        learn_read_only_turns=False,
        # Basit sohbet veya kullanıcının açıkça araç istemediği bir turda onlarca
        # araç şemasını browser prompt'una eklemek hem gecikme hem geçici web hatası
        # üretir. API sağlayıcıları yukarıdaki erken dönüşle aynen korunur.
        offer_tools=not explicit_no_tools and (requires_evidence or not simple_chat),
        requires_tool_evidence=requires_evidence,
        required_effect=required_effect,
        max_evidence_reprompts=0 if explicit_no_tools else 1,
    )


_EXPLICIT_NO_TOOL_MARKERS = (
    "araç kullanma",
    "arac kullanma",
    "tool kullanma",
    "araç çağırma",
    "arac cagirma",
)
_SCOPED_NO_TOOL_MARKERS = (
    "başka",
    "baska",
    "diğer",
    "diger",
    "dışında",
    "disinda",
    "haricinde",
    "sonra",
    "ardından",
    "ardindan",
)
_NO_TOOL_CLAUSE_SPLIT = re.compile(
    r"(?:[.!?;\n]+|\b(?:ama|fakat|ancak|lakin)\b)",
    re.IGNORECASE,
)


def _explicit_no_tools(lowered: str) -> bool:
    clauses = [clause.strip() for clause in _NO_TOOL_CLAUSE_SPLIT.split(lowered) if clause.strip()]
    for clause in clauses:
        if not any(marker in clause for marker in _EXPLICIT_NO_TOOL_MARKERS):
            continue
        if any(scope in clause for scope in _SCOPED_NO_TOOL_MARKERS):
            continue
        return True
    return False


def _is_genuine_simple_chat(task: str, kind: TaskKind, required_effect: str | None) -> bool:
    """Araç şeması taşımaya değmeyen gerçek kısa sohbeti tanı.

    Eski `GENERAL + <=240 karakter` kuralı operasyonları da sohbet sanıyordu. Burada
    yalnızca açık selam/teşekkür/kimlik sorusu ve “sadece X yaz” türü doğrudan cevap
    görevleri araçsız kabul edilir.
    """

    if required_effect is not None:
        return False
    lowered = " ".join(task.lower().split()).strip(" .!?…")
    if len(lowered) > 260:
        return False
    if re.fullmatch(
        r"(?:merhaba|selam|selamlar|günaydın|gunaydin|iyi akşamlar|iyi aksamlar|"
        r"teşekkür(?:ler| ederim)?|tesekkur(?:ler| ederim)?|sağ ol|sag ol|nasılsın|nasilsin)",
        lowered,
    ):
        return True
    if re.fullmatch(r"(?:hangi|ne) model(?:sin| kullanıyorsun| kullaniyorsun)?", lowered):
        return True
    return bool(
        re.search(
            r"^(?:sadece|yalnızca|yalnizca)\b.{0,220}\b"
            r"(?:yaz|söyle|soyle|cevapla|döndür|dondur)\b",
            lowered,
            re.DOTALL,
        )
    )


def is_web_model(config: Config, model: str) -> bool:
    """Model native Web AI kimliği veya config'te web oturumu mu?"""

    provider = model.split("/", 1)[0].strip().lower()
    if provider in _WEB_PROVIDER_IDS or provider.endswith("_web"):
        return True
    return any(session.model == model for session in config.web_sessions)


def is_complex_kind(kind: TaskKind) -> bool:
    return kind in _COMPLEX_KINDS

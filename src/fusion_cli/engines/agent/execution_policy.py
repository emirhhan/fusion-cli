"""Sağlayıcıya göre agent yürütme bütçesi.

API sağlayıcılarının mevcut davranışı korunur. Tarayıcı/oturum tabanlı Web AI
sağlayıcılarında tek bir üst sınır kademesi uygulanır; kaçak turu sabit çağrı
sayısı değil ilerleme kapısı ve boşta-kalma süresi durdurur.

Politika görev TÜRÜNE bakmaz. Ölçüldü: kelime sınıflandırıcısıyla seçilen bütçe
kademesi "devam et" gibi kısa bir mesajı beş araç turuna indirip büyük işi
yarıda kesiyordu. Bu turun metninden yalnız `required_effect` (açık dış etki)
çıkarılır; o da yönlendirmez, kanıt kapısını besler.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from ...config.models import Config
from ...config.tool_policy import mutation_policy_for_model
from ...core.types import ModelSpec
from ..effects.detect import required_effect_for

_WEB_PROVIDER_IDS = frozenset(
    {"chatgpt_web", "claude_web", "gemini_web", "copilot_web", "perplexity_web"}
)
#: Değişiklik ürettiği kesin olan etki sözleşmeleri.
#
# Metin gerçek bir değişiklik istiyorsa (dosya yaz, komut çalıştır, commit, push)
# tur "karmaşık" sayılır: kanıt kapısı ve değişiklik gerektiren denetimler buna
# bakar.
#
# `"bulk_count"` (toplu sayma/filtreleme, bkz. `effects/detect.py`) BİLEREK bu
# kümeye eklenmez: sayma bir dosyayı değiştirmiyor, yalnızca doğru araç kanıtı
# istiyor. Kod okunarak doğrulandı: `policy_for` aşağıda `requires_tool_evidence`i
# `required_effect is not None` üzerinden kurar — bu, `_MUTATING_EFFECTS` kümesine
# girmeyen her etki adı için de zaten True olur. Bu yüzden yeni etkinin kanıt
# kapısını açması için bu dosyada BAŞKA bir değişikliğe gerek yoktur.
_MUTATING_EFFECTS = frozenset({"workspace_mutation", "shell_action", "git_push", "git_commit"})

#: Web AI turunun tek bütçe kademesi: model çağrısı, araç turu, toplam süre (sn),
#: boşta kalma süresi (sn).
#
# Ölçüldü (Godot koşusu, kullanıcı makinesi): gerçek bir oyun projesi
# `project.godot` + birkaç sahne + birkaç script + asset indirme demek; bu,
# onlarca okuma ve yazma eder. Daha dar sınırlar işi TAM İLERLERKEN kesiyor ve
# kullanıcıya yarım bir iskelet bırakıyordu. Bu değerler o koşuda ölçülen
# "karmaşık iş" kademesidir.
#
# Kaçak koruması sayıdan değil iki yerden gelir: ilerlemesiz tur sayacı
# (`max_idle_rounds`) ve boşta-kalma zaman aşımı. "Merhaba" bütçe tüketmez;
# model tek çağrıda cevaplar.
WEB_MAX_MODEL_CALLS = 90
WEB_MAX_TOOL_ROUNDS = 75
WEB_TOTAL_TIMEOUT_S = 5_400.0
WEB_IDLE_TIMEOUT_S = 300.0


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
    #: Bu turun metni açık bir değişiklik etkisi istiyor mu (`_MUTATING_EFFECTS`).
    complex_task: bool = False
    max_evidence_reprompts: int = 1
    # Bu modelin dosya/shell değiştirmesine izin var mı? Doğrulanmamış taklit-araç
    # modelleri (bkz. config.tool_policy) okur ve planlar ama değiştiremez.
    allow_mutation: bool = True
    #: İzin yoksa kullanıcıya ve modele gösterilecek gerekçe.
    mutation_block_reason: str = ""
    #: Engel MODEL YETENEĞİNDEN mi geliyor (kip kararından değil)?
    #
    # Ayrım şart: sohbet ve gözlem turları da `allow_mutation=False` kurar ama
    # onların gerekçesi bu turun KARARIDIR, modelin yeteneği değil. Yedek zinciri
    # başka bir modele düştüğünde yalnız YETENEK kaynaklı engel gözden geçirilir;
    # kip kararı asla geri alınmaz.
    mutation_blocked_by_capability: bool = False
    #: Şema ve gerçek dispatcher için aynı kesin araç sınırı.
    allowed_tool_names: frozenset[str] | None = None
    #: Bu adım kaçıncı kez deneniyor; yedek zinciri o kadar yukarı kaydırır.
    escalation: int = 0
    #: Kurtarma gözlemi sınıflandırma kaynaklı değişiklik zorlaması almamalı.
    observe_only: bool = False


def policy_for(config: Config, spec: ModelSpec, task: str) -> ExecutionPolicy:
    """Seçilen model ve BU TURUN metni için yürütme politikasını döndür.

    Kısa mesaj otomatik olarak “sohbet” değildir. “Repoyu pushla”, “paketi kur” veya
    “dosyayı sil” gibi birkaç kelimelik görevler gerçek bir etki ister ve araçsız
    tamamlanamaz. Bu ayrım sağlayıcıdan bağımsızdır; Web AI tarafında ayrıca araç
    şemalarının yanlışlıkla kapatılmasını önler.
    """

    lowered = task.lower()
    explicit_no_tools = _explicit_no_tools(lowered)
    # Kullanıcı “araç kullanma” dese bile gerçek bir dış etki talebi ortadan
    # kalkmaz. Araçlar kapalı tutulur ama iş yapılmış gibi raporlanamaz.
    required_effect = required_effect_for(task)
    requires_evidence = required_effect is not None
    complex_task = required_effect in _MUTATING_EFFECTS
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
            mutation_blocked_by_capability=not mutation.ok,
            offer_tools=not explicit_no_tools,
            requires_tool_evidence=requires_evidence,
            required_effect=required_effect,
            max_evidence_reprompts=0 if explicit_no_tools else 1,
            complex_task=complex_task,
        )

    simple_chat = _is_genuine_simple_chat(task, required_effect)
    return ExecutionPolicy(
        is_web=True,
        allow_mutation=mutation.ok,
        mutation_block_reason=mutation.reason,
        mutation_blocked_by_capability=not mutation.ok,
        max_model_calls=WEB_MAX_MODEL_CALLS,
        max_tool_rounds=WEB_MAX_TOOL_ROUNDS,
        max_same_tool_without_change=2,
        total_timeout_s=WEB_TOTAL_TIMEOUT_S,
        idle_timeout_s=WEB_IDLE_TIMEOUT_S,
        # Web yanıtında kısa ama geçerli final metnini "yarım" sanıp fazladan
        # çağrı açma. Gerçek truncation ve bekleyen todo hâlâ devam ettirilir.
        heuristic_auto_continue=False,
        complex_task=complex_task,
        # Basit sohbet/keşifte denetçi çağrısı yapma; kod ve değişiklik işlerinde koru.
        conditional_self_review=True,
        # Salt-okuma web turlarından ayrı bir model çağrısıyla ders çıkarma.
        learn_read_only_turns=False,
        # Taşıma optimizasyonu, yönlendirme değil: selamlaşmada ya da kullanıcının
        # açıkça araç istemediği turda onlarca araç şemasını tarayıcı istemine
        # eklemek hem gecikme hem geçici web hatası üretir.
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


def _is_genuine_simple_chat(task: str, required_effect: str | None) -> bool:
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


def uses_web_context(config: Config, spec: ModelSpec) -> bool:
    """Use the narrow history limit only if the selected chain can reach web AI."""
    models = (spec.model,) if spec.strict else spec.models
    return any(is_web_model(config, model) for model in models)


def refresh_mutation_policy(
    execution: ExecutionPolicy, served_by: str, config: Config
) -> ExecutionPolicy:
    """Turu GERÇEKTE karşılayan modele göre yetenek kapısını tazele.

    Ölçüldü (22 Eylül, kullanıcının kendi kurulumunda): birincil `chatgpt_web`
    oturumu insan doğrulamasına takılınca zincir `nvidia_nim/...` modeline düştü,
    ama tur sonuna kadar SALT-OKUNUR kaldı. Engelin gerekçesi ("chatgpt_web
    taklit aracı ölçülmedi") artık işi yapan modele ait değildi; kullanıcı ise
    hiçbir dosyanın neden yazılamadığını göremiyordu.

    Kapı yalnız AÇILIR, hiç kapanmaz. Turun ortasında aracı elinden alınan model
    yarım iş bırakır; daraltma kararı turun başında verilir. Kip kaynaklı engel
    (sohbet, gözlem) buraya hiç girmez — `mutation_blocked_by_capability` False'tur.
    """
    if execution.allow_mutation or not execution.mutation_blocked_by_capability:
        return execution
    if not served_by:
        return execution
    if not mutation_policy_for_model(config, served_by).ok:
        return execution
    return replace(
        execution,
        allow_mutation=True,
        mutation_block_reason="",
        mutation_blocked_by_capability=False,
    )

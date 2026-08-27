"""Agent döngüsü: tek model + araçlar + öz-denetim.

Bir tur şöyle akar:

    model çağrısı ──▶ araç istedi mi?
                       ├── evet → onay → çalıştır → sonucu geçmişe ekle → tekrar
                       └── hayır → nihai cevap

Üzerine üç iyileştirme katmanı biner:

- **Refleksiyon** — bir araç hata döndürdüğünde modele "farklı yaklaş" notu enjekte
  edilir. Ek model çağrısı YOK; bedava bir davranış düzeltmesidir.
- **Otomatik devam** — model işi yarım bırakmış görünüyorsa bir kez "devam et" denir.
- **Öz-eleştiri** — tur bitince denetçi model sonucu kontrol eder; somut bir sorun
  bulursa TEK düzeltici tur çalışır. Sonsuz düzeltme döngüsü yoktur.

Motor konsolu tanımaz: tüm ilerleme olay olarak yayınlanır. Araçlar arasında ayrım
yapmaz: alt-ajan devri de dosya okumak da kayıt defterinden geçer.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ...config.eligibility import effort_for_spec
from ...config.model_select import select_agent_spec
from ...config.models import Config
from ...core.budget import BudgetStop, TurnBudget
from ...core.clock import SystemClock
from ...core.concurrency import BackgroundTasks
from ...core.constants import CAPABILITY_WALL_PREFIX, FILE_MISSING_PREFIX
from ...core.errors import FusionError
from ...core.events import (
    Channel,
    ContextCompressed,
    EventPublisher,
    MutationUnavailable,
    SelfReviewFinished,
    SelfReviewStarted,
    ToolCallRepaired,
    ToolExecuted,
    ToolOutcome,
    TurnAnswered,
    TurnBudgetExhausted,
    VerificationFailed,
)
from ...core.health import HealthRegistry
from ...core.memory import CodeIndex, LessonMemory
from ...core.tools import ToolContext, ToolResult
from ...core.types import (
    CompletionRequest,
    Message,
    ModelResult,
    StreamDone,
    TextChunk,
    ToolCall,
)
from ...core.verification import VerificationResult, Verifier
from ...memory.lessons import as_prompt_block
from ...providers.factory import build_provider
from ...providers.web_registry import web_registry_for
from ...tools import ToolRegistry, build_registry
from ...tools.capabilities import CapabilityRegistry
from ...tools.emulation import render_tool_example, validate_arguments
from ...tools.files import resolve_path
from ...tools.preview import file_diff
from ..effects.runner import maybe_run_effect_workflow
from . import compaction, history, learning_steps, reflexion, review, skill_recall
from .approval import ApprovalPolicy, Decision, SecurityApproval, build_request
from .classify import TaskClassification, TaskKind, classify_task_details, recall_scope, scope_of
from .engine_tools import UserAsker, build_agent_registry
from .execution_policy import ExecutionPolicy, is_complex_kind, policy_for
from .playbook_stage import maybe_run_playbook, run_workflow_stages
from .project_instructions import read_project_instructions
from .workspace_hint import find_workspace_for

_PROMPTS = Path(__file__).parent / "prompts"
SYSTEM_PROMPT = (_PROMPTS / "system.md").read_text(encoding="utf-8")
PLAN_MODE_PROMPT = (_PROMPTS / "plan_mode.md").read_text(encoding="utf-8")

#: Yarım kalan turda en fazla kaç kez "devam et" enjekte edilir.
MAX_AUTO_CONTINUE = 1
#: Doğrulama kapısının bir turda en fazla kaç kez çalışacağı.
#:
#: 1 yetmiyordu: düzeltici tur KENDİ hatasını üretebiliyor. Gerçek koşuda kapı beş
#: sorunu bildirdi, model düzeltirken index.html'i yeniden yazdı ve <script> etiketini
#: düşürdü — sayfa tamamen boş kaldı, kapı bir daha bakmadığı için öyle teslim edildi.
#: 2 bu regresyonu yakalar; daha fazlası sonsuz düzeltme döngüsü riskidir.
MAX_VERIFY_ROUNDS = 2

#: Boş cevapta kaç kez daha denenir. Sınırsız denemek kotayı ve zamanı tüketir;
#: hiç denememek turu iş yapmadan bitirir (ölçüldü).
MAX_EMPTY_RETRIES = 2
#: Bozuk araç çağrısı için TÜM tur boyunca tanınan onarım hakkı.
#
# Eskiden 1'di ve 12 turluk işler için ölçülmüştü. Turlar 22 tura çıkınca bu hak
# orantısız kaldı: yirmi adımlık bir işin herhangi bir yerindeki TEK yazım hatası
# tüm turu öldürüyor ve o ana kadarki işi çöpe atıyordu (ölçüldü: dört koşunun
# biri böyle düştü).
#
# Sayı tur uzunluğuyla birlikte büyütülür, sınırsız değildir: aynı bozuk çağrıyı
# tekrarlayan model zaten `seen >= 1` kuralıyla ayrıca durdurulur ve ilerleme
# üretmeyen turları "ilerleme yok" kapısı bitirir.
MAX_TOOL_CONTRACT_REPAIRS = 4

#: Değişiklik isteyen bir görevde arka arkaya kaç keşif turuna izin verilir.
#
# Ölçüldü: model dizin listeledi, dosya okudu, başka dizin listeledi… ve bütçe
# keşifle doldu; tek satır değişmedi. Dört tur, bir projeyi tanımaya yeter
# (list_dir + iki okuma + bir arama); beşincide artık yazılacak yer bellidir.
MAX_READ_ONLY_ROUNDS = 4
#: Keşif kapısının bir turda en fazla kaç kez konuşacağı. Israr etmek yerine
#: kanıt kapısına ve tur bütçesine bırakılır; sonsuz dürtme çağrı yakar.
MAX_EXPLORE_PUSHES = 2


#: Kullanıcı reddettiğinde modele dönen açıklama. Hata DEĞİLDİR; refleksiyon tetiklemez.
#: Onay alınamadı. İKİ durumu birden anlatır ve bu bilinçlidir: kullanıcı
#: reddetmiş olabilir ya da oturum etkileşimsizdir ve kimseye sorulamamıştır.
#: Eski metin ("kullanıcı bu işlemi onaylamadı") ikinci durumda yanlıştı —
#: ölçüldü: boru hattında çalışan bir turda kimse reddetmemişti, model yine de
#: reddedildiğini sandı ve ne yapacağını bilemeden turu tüketti.
#:
#: Son cümle (UYDURMA UYARISI) sonradan eklendi. Ölçüldü: reddedilen adım gerçek
#: veri getirecekti (ör. `git clone` sonrası dosya okuma); model reddi metinde
#: kabul etti ama ÇIKTI DOSYASINA yine de ezberden "gerçek" görünen değerler
#: yazdı — kullanıcı çıktıyı kaynağa dayalı sandı. "Adımı neden atladığını yaz"
#: talimatı SOHBETİ kapsıyordu, TESLİM EDİLEN dosyayı değil; bu satır o boşluğu
#: doğrudan, reddin olduğu anda (en yüksek dikkat anında) kapatır.
DENIED_MESSAGE = (
    "Bu işlem onaylanmadı — kullanıcı reddetmiş ya da oturum etkileşimsiz olduğu "
    "için onay alınamamış olabilir. Onay GEREKTİRMEYEN bir yol dene (dosya "
    "araçları onay istemez); mümkün değilse bu adımı neden atladığını açıkça yaz. "
    "Bu adımın getireceği veriyi (dosya içeriği, sayı, açıklama…) ASLA ezberden ya "
    "da tahminle üretip teslim ettiğin dosyaya/cevaba yazma — reddedilen adımı "
    "atladığını söylemek yeterli değildir, UYDURULMUŞ değeri de yazmamalısın."
)
#: Plan modunda değiştirici araç hiç çalıştırılmaz ve kullanıcıya sorulmaz.
BLOCKED_MESSAGE = "PLAN MODU: değişiklik yapılamaz. Sorma, yalnızca planı sun."
#: Görev gerçek bir etki istiyor ama model bunu yapamıyor. Kullanıcıya NE YAPACAĞINI
#: söyler: sebep + çıkış yolu. Hata mesajı eyleme dönüştürülebilir olmalıdır (RULES).
MUTATION_UNAVAILABLE_ANSWER = (
    "Bu görev dosya/sistem değişikliği gerektiriyor ama seçili model bunu yapamıyor: "
    "{reason}.\n\n"
    "Yapılacak: `fusion serve` ile paneli aç → Sağlayıcılar → ilgili web oturumu → "
    '"Araç yeteneğini ölç". Ölçüm geçerse izin açılır. Alternatif olarak `/model` ile '
    "araç yetenekli bir API modeline geç.\n\n"
    "Hiçbir değişiklik yapılmadı."
)
#: Model yetenek kapısına takıldı: okuyabilir, planlayabilir ama değiştiremez.
MUTATION_BLOCKED_MESSAGE = (
    "Bu model dosya/sistem değiştiremez ({reason}). Değişiklik önerini metin olarak "
    "yaz; uygulamayı kullanıcı ya da araç yetenekli bir model üstlenecek."
)

_DECISION_MESSAGES = {
    Decision.DENIED: DENIED_MESSAGE,
    Decision.BLOCKED: BLOCKED_MESSAGE,
}
_DECISION_OUTCOMES = {
    Decision.DENIED: ToolOutcome.DENIED,
    Decision.BLOCKED: ToolOutcome.BLOCKED,
}


def _new_budget(config: Config) -> TurnBudget:
    """Bir kullanıcı turu için bütçe kur.

    Eşiklerin bir kısmı yapılandırmadan, bir kısmı yukarıdaki sabitlerden gelir ve bu
    bilinçlidir: kullanıcının ayarlaması anlamlı olanlar (adım sayısı, boşta tur)
    `defaults.yaml`'dadır; "kaç kez devam et denir" gibi davranış detayları koddadır
    ve gerekçeleri sabitin yanında yazılıdır.
    """
    return TurnBudget(
        clock=SystemClock(),
        max_model_calls=config.runtime.agent_max_steps,
        max_verify_rounds=MAX_VERIFY_ROUNDS,
        max_empty_retries=MAX_EMPTY_RETRIES,
        max_contract_repairs=MAX_TOOL_CONTRACT_REPAIRS,
        max_auto_continues=MAX_AUTO_CONTINUE,
        max_idle_rounds=config.runtime.agent_max_idle_rounds,
    )


@dataclass(slots=True)
class AgentOutcome:
    """Bir agent turunun sonucu."""

    final_text: str
    messages: list[Message]
    tool_calls_made: int = 0
    #: Adım sınırına dayanıldı mı?
    hit_step_limit: bool = False
    #: Tur temiz bitti mi? Model akışı hata verirse False. Ders güvenini besler.
    ok: bool = True
    #: Başarıyla çalışan değiştirici araç sayısı. Koşullu denetim/öğrenme kapısı kullanır.
    mutating_tool_calls_made: int = 0
    #: Başarısız araç sayısı. Basit salt-okuma turu ile sorunlu turu ayırır.
    failed_tool_calls: int = 0
    #: Bu turda yapılan gerçek model çağrısı sayısı (teşhis ve bütçe için).
    model_calls_made: int = 0

    #: Nihai cevap akış sırasında ekrana ulaştı mı? Ulaştıysa `TurnAnswered`
    #: yayınlanmaz; aynı metin iki kez basılmaz.
    answer_streamed: bool = False
    #: Görevdeki dosyaların hiçbiri bulunamadı — muhtemelen yanlış çalışma dizini.
    wrong_workspace: bool = False
    #: Tur bir BÜTÇE sınırına çarparak bitti mi? Sebep ayrıca yayınlanmıştır;
    #: `final_text` modelin cevabıdır, hata metni değildir.
    budget_stopped: bool = False

    @property
    def made_no_changes(self) -> bool:
        """Tur araç çalıştırdı ama hiçbir şey değiştirmedi mi?

        Araç HİÇ çağrılmayan tur dışarıdadır: düz sohbet cevabında "değişiklik
        yapılmadı" demek gürültüdür, kimse değişiklik beklemiyordu.
        """
        return self.tool_calls_made > 0 and self.mutating_tool_calls_made == 0


@dataclass(slots=True)
class AgentDeps:
    """Motorun dış bağımlılıkları. Testte tamamı sahteyle verilebilir."""

    config: Config
    publisher: EventPublisher
    policy: ApprovalPolicy
    tool_context: ToolContext
    #: Yerleşik araçlar. Motora bağlı araçlar çalışma anında bunun kopyasına eklenir.
    base_registry: ToolRegistry = field(default_factory=build_registry)
    #: Kullanıcıya soru sorabilen taraf. Yoksa `ask_user` aracı hiç sunulmaz.
    asker: UserAsker | None = None
    #: Anlamsal kod araması. Yoksa `search_codebase` aracı hiç sunulmaz.
    code_index: CodeIndex | None = None
    #: Öğrenilen dersler. Yoksa hatırlama ve ders çıkarımı atlanır.
    lessons: LessonMemory | None = None
    #: Skill/agent kütüphanesi. Yoksa arama ve devretme araçları hiç sunulmaz.
    capabilities: CapabilityRegistry | None = None
    #: Kullanıcının `.claude/settings.local.json` içinde onaysız izin verdiği komutlar.
    allowed_commands: frozenset[str] = frozenset()
    #: Verilirse ders çıkarımı turu BEKLETMEDEN arka planda çalışır (REPL için).
    #: Verilmezse tur içinde beklenir (tek seferlik CLI için doğru davranış).
    background: BackgroundTasks | None = None
    channel: Channel = Channel.MAIN
    #: Kullanıcının seçtiği görev tipi (`/type`). `task_model_map` üzerinden bu turda
    #: kullanılacak modeli belirler; haritada karşılığı yoksa `agent:` rolü kullanılır.
    task_type: str = "general"
    #: Verilirse kod değiştiren tur sonrası doğrulama kapısı çalışır ve sonucu ders
    #: güvenini besler. Verilmezse (varsayılan) mevcut davranış birebir korunur.
    verifier: Verifier | None = None
    #: Oturum boyunca paylaşılan sağlayıcı sağlığı (circuit breaker + güvenilirlik).
    #: Verilirse sağlıksız model turlar arası atlanır. Verilmezse breaker kurulmaz.
    health: HealthRegistry | None = None
    #: TURUN TAMAMI için tek sayaç otoritesi. `run_agent` bunu tur başında bir kez
    #: kurar; öz-denetim ve doğrulama kapısının açtığı iç içe çağrılara AYNI nesne
    #: devredilir. `None` bırakılırsa ilk `run_agent` çağrısı kurar.
    #:
    #: Testler kendi bütçesini vererek sınırları daraltabilir.
    budget: TurnBudget | None = None
    #: Turun yürütme politikası. Bütçe gibi TUR BAŞINDA belirlenir ve iç içe
    #: çağrılara devredilir.
    #:
    #: Ölçüldü: öz-denetim/doğrulama turu politikayı DÜZELTME METNİNDEN yeniden
    #: türetiyordu. Asıl görev BUGFIX (12 araç turu) olsa bile düzeltme metni basit
    #: sohbet sanılıp 5 tura düşüyor ve iş yarıda kesiliyordu.
    execution: ExecutionPolicy | None = None

    def require_budget(self) -> TurnBudget:
        """Bütçeyi döndür; kurulmamışsa programlama hatasıdır.

        `run_agent` her çalıştığında bütçenin kurulu olduğunu garanti eder; bu metot
        yalnızca döngü içindeki kodun `None` kontrolü yapmasını gereksiz kılar.
        """
        if self.budget is None:
            raise FusionError("Tur bütçesi kurulmadan agent döngüsü çalıştırılamaz.")
        return self.budget


async def run_agent(
    task: str,
    deps: AgentDeps,
    *,
    history: list[Message] | None = None,
    plan_mode: bool = False,
    extra_system: str = "",
    depth: int = 0,
    self_review: bool | None = None,
    allowed_tools: set[str] | None = None,
    step_limit: int | None = None,
    verify: bool = True,
    internal: bool = False,
) -> AgentOutcome:
    """Bir görevi araçlarla çalıştır. Döndürülen geçmiş bir sonraki tura beslenir.

    `allowed_tools` verilirse modele YALNIZCA o araçlar sunulur (uzman agent'lar
    kendi araç setini bildirebilir). Görev yönetimi ve soru sorma her zaman açıktır.
    """
    # Bütçe turun EN BAŞINDA bir kez kurulur ve buradan sonra her iç içe çağrı aynı
    # nesneyi görür. Öz-denetim ve doğrulama kapısı `run_agent`'ı yeniden çağırdığı
    # için, bütçe orada kurulsaydı her düzeltici tur sıfırdan başlardı — düzeltilen
    # hata tam olarak buydu.
    if deps.budget is None:
        deps.budget = _new_budget(deps.config)

    if not plan_mode and depth == 0:
        played = await maybe_run_playbook(task, deps)
        if played is not None:
            return played

    registry = build_agent_registry(deps, depth=depth, run_agent=run_agent)
    # Sınıflandırma ve bütçe, TURUN metnine değil GÖREVİN tamamına bakar.
    #
    # Ölçüldü: kullanıcı turu durdurup "devam et" yazdı. O iki kelime GENERAL'e
    # düştü, bütçe beş araç turuna indi ve iş "araç turu sınırına ulaşıldı (5)"
    # ile yarıda kesildi — oysa sürdürülen görev aynı büyük görevdi. Aynı hata
    # onay istemine yazılan tek harfle de yaşandı.
    classification = classify_task_details(_scoped_task(task, history))
    kind = classification.primary

    # Gerçek dünya etkisi için deterministik handler varsa LLM ReAct döngüsünü
    # tamamen atla. Modelin "pushluyorum" demesi operasyon sonucu değildir; Git
    # workflow'u post-condition (local HEAD == remote HEAD) kanıtını kendisi üretir.
    effect_result = await maybe_run_effect_workflow(
        task, deps, registry, plan_mode=plan_mode, depth=depth
    )
    if effect_result is not None:
        effect_messages = list(history or [])
        effect_messages.append(Message("user", task))
        effect_messages.append(Message("assistant", effect_result.final_text))
        return AgentOutcome(
            final_text=effect_result.final_text,
            messages=effect_messages,
            tool_calls_made=effect_result.tool_calls_made,
            ok=effect_result.ok,
            mutating_tool_calls_made=effect_result.mutating_tool_calls_made,
            failed_tool_calls=effect_result.failed_tool_calls,
            model_calls_made=0,
        )

    if not plan_mode and depth == 0 and deps.config.runtime.workflow_mode:
        return await run_workflow_stages(task, deps, run_agent)

    auto_context = skill_recall.should_auto_context(classification)
    recalled = learning_steps.recall_lessons(
        task,
        deps,
        scope=recall_scope(kind),
        enabled=auto_context,
    )
    remembered = as_prompt_block(recalled)
    expertise = _recall_skill(classification, deps, depth=depth)
    proje_talimati = read_project_instructions(deps.tool_context.root)
    messages = _initial_messages(
        task,
        history,
        plan_mode=plan_mode,
        extra_system="\n\n".join(
            part for part in (proje_talimati, remembered, expertise, extra_system) if part
        ),
        # İç düzeltici turlar sistem metnini geçmişten miras alır; yeniden
        # hesaplanan ders/uzmanlık bloğu öneki kaydırıp sohbeti sıfırlıyordu.
        inherit_system=internal,
    )

    if deps.execution is None:
        selected_spec = select_agent_spec(deps.config, deps.task_type)
        deps.execution = policy_for(deps.config, selected_spec, kind, _scoped_task(task, history))
    execution = deps.execution
    # Web AI'nın toplam süre sınırı bütçeye TUR BAŞINDA bir kez yazılır; iç içe
    # çağrılarda yeniden kurulsaydı süre sınırı her düzeltmede tazelenirdi.
    budget = deps.require_budget()
    if budget.total_timeout_s is None and execution.total_timeout_s is not None:
        budget.total_timeout_s = execution.total_timeout_s
    if budget.idle_timeout_s is None and execution.idle_timeout_s is not None:
        budget.idle_timeout_s = execution.idle_timeout_s

    # Yetenek kapısı sessiz kalmamalı: değiştirici araçlar sunulmuyorsa kullanıcı
    # bunu ve nasıl kaldıracağını GÖRMELİ. Görev zaten gerçek bir etki istiyorsa
    # model çağrısı harcamadan dururuz — hiçbir tur bu kısıtı aşamaz.
    if not execution.allow_mutation and not plan_mode:
        # Görev türü de bağlayıcıdır. `required_effect` metinden çıkarılır ve dar
        # kalabilir: "envanter.py'deki hataları düzelt ve eksik modülü yaz" hiçbir
        # desene uymuyordu, bu yüzden tur salt-okunur kipte beş çağrı harcayıp
        # hiçbir şey yapamadan bitti. BUGFIX/FEATURE gibi bir tür zaten doğası
        # gereği değişiklik ister; ayrıca metinden kanıt aramaya gerek yok.
        blocking = execution.required_effect is not None or is_complex_kind(kind)
        deps.publisher.publish(
            MutationUnavailable(reason=execution.mutation_block_reason, blocking=blocking)
        )
        if blocking:
            return AgentOutcome(
                final_text=MUTATION_UNAVAILABLE_ANSWER.format(
                    reason=execution.mutation_block_reason
                ),
                messages=[*(history or []), Message("user", task)],
                ok=False,
            )

    outcome = await _drive(
        messages,
        deps,
        registry,
        plan_mode=plan_mode,
        allowed_tools=allowed_tools,
        step_limit=step_limit,
        execution=execution,
        internal=internal,
    )

    should_review = deps.config.runtime.self_review if self_review is None else self_review
    # Başarısız provider/transport veya kanıtsız eylem sonucu cevap kalitesi değildir.
    # Denetçiye göndermek hatayı maskeleyip ek çağrılar üretir.
    if should_review and not outcome.ok:
        should_review = False
    # Yanlış dizinde düzeltilecek bir şey YOKTUR. Ölçüldü: öz-denetim düzeltici
    # turu tam bu durumda görevi terk edip kendine yeni iş uydurdu (o projenin
    # README'sini okuyup "test paketini çalıştır" diye plan yazdı). Doğru cevap
    # "bu dizinde o dosyalar yok" demektir; onu ikinci bir tur iyileştiremez.
    if outcome.wrong_workspace:
        should_review = False
    if should_review and execution.conditional_self_review:
        should_review = _web_self_review_needed(task, kind, outcome, deps)
    if should_review and not plan_mode and depth == 0 and outcome.final_text.strip():
        outcome = await _self_review(task, outcome, deps)

    verification = None
    # Doğrulama turu hakkı da tur genelidir: iç içe bir düzeltme kendi kapı bütçesini
    # açamaz (`verify=False` ile zaten kapatılıyor, bütçe bunu ikinci kez garanti eder).
    while (verify and budget.stop is None and budget.take_verify_round()):
        verification = await _verify(outcome, deps, plan_mode=plan_mode, depth=depth)
        # Bulgu YOKLUĞU başarı değildir: `ok=False` tek başına düzeltmeyi hak eder.
        # Koşul eskiden `not verification.findings` de arıyordu; yalnızca özet
        # dolduran bir kapı (komut doğrulayıcısı) başarısız olduğunda agent
        # düzeltmeye hiç başlamıyordu.
        if verification is None or verification.ok:
            break
        outcome = await _fix_findings(task, verification, outcome, deps)

    _mark_verification_notes(outcome, verification)
    _mark_unverified(outcome, verification)

    # Cevap ÖĞRENMEDEN ÖNCE duyurulur. Ölçüldü: iş bir dakikada bitti, cevap
    # hazırdı, ama ders çıkarımı bitene kadar ekrana hiçbir şey basılmadı ve
    # kullanıcı 20 dakika boş ekran gördü. Öğrenme muhasebedir; kullanıcıyı
    # bekletemez.
    _announce_answer(outcome, deps, depth=depth, internal=internal)

    await learning_steps.learn(
        task,
        outcome,
        deps,
        plan_mode=plan_mode,
        scope=scope_of(kind),
        allow_read_only=execution.learn_read_only_turns,
    )
    await learning_steps.reinforce_recalled(
        recalled, outcome, deps, plan_mode=plan_mode, verification=verification
    )
    outcome.messages = await _maybe_compress(outcome.messages, deps)
    # Tarayıcı oturumunun sahibi EN DIŞTAKİ turdur. İç içe çağrılar (öz-denetim,
    # doğrulama düzeltmesi, alt-ajan) aynı bağlamı paylaşır; onların kapatması
    # sürmekte olan turun sayfasını elinden alırdı. Kapatılmayan oturum arkada
    # bir chromium süreci bırakır — RULES.md "oluşturulan her task'ın sahibi vardır".
    if depth == 0 and deps.tool_context.browser.is_open:
        await deps.tool_context.browser.close()
    return outcome


#: Doğrulama düzeltilemediğinde cevabın başına eklenen uyarı.
#
# Ölçüldü: model `app/page.tsx`'e yinelenen fonksiyon tanımları ekledi, doğrulama
# kapısı bunu YAKALADI, düzeltici tur açıldı, düzeltme de tutmadı ve kapı hakkı
# bitti. Tur yine de BAŞARI özetiyle kapandı ("bileşenleri ekleyip eksik
# tanımları tamamladım") ve kullanıcının projesi 8 derleme hatasıyla bozuk kaldı.
#
# Bildiğimiz bir bozukluğu başarı diye teslim etmek, hiç yazmamaktan kötüdür.
UNVERIFIED_WARNING = (
    "⚠ DOĞRULAMA GEÇMEDİ — yapılan değişiklikler projeyi kırıyor olabilir.\n"
    "{summary}\n{findings}\n"
    "Değişiklikleri gözden geçir; gerekirse `/undo` ile geri al.\n\n"
)


def _mark_unverified(outcome: AgentOutcome, verification: VerificationResult | None) -> None:
    """Doğrulama düzeltilemediyse turu BAŞARI olarak kapatma.

    Kapı hakkı bittiğinde sonuç sessizce yutuluyordu: elimizde "bu değişiklik
    projeyi kırıyor" bilgisi varken kullanıcıya başarı özeti gidiyordu.
    """
    if verification is None or verification.ok:
        return
    bulgular = "\n".join(f"- {finding}" for finding in verification.findings[:5])
    outcome.final_text = (
        UNVERIFIED_WARNING.format(summary=verification.summary, findings=bulgular)
        + outcome.final_text
    )
    outcome.ok = False



VERIFICATION_NOTES = (
    "⚠ Doğrulama notları — işi engellemiyor:\n"
    "{notes}\n\n"
)


def _mark_verification_notes(
    outcome: AgentOutcome,
    verification: VerificationResult | None,
) -> None:
    """Non-blocking doğrulama notlarını final cevaba ekle.

    Bunlar correction agent açmaz, `outcome.ok` değerini değiştirmez ve öğrenme
    sisteminde başarısız tur sayılmaz.
    """
    if verification is None or not verification.has_notes:
        return

    lines = [
        *(f"- [uyarı] {finding}" for finding in verification.warnings[:5]),
        *(f"- [öneri] {finding}" for finding in verification.advisories[:5]),
    ]

    outcome.final_text = (
        VERIFICATION_NOTES.format(notes="\n".join(lines))
        + outcome.final_text
    )


def _announce_answer(
    outcome: AgentOutcome, deps: AgentDeps, *, depth: int, internal: bool
) -> None:
    """Kabul edilmiş nihai cevabı TEK noktadan yayınla.

    Yayın noktası bilinçli olarak `run_agent`'ın SONUDUR, `_drive`'ın değil:
    `_drive` her çağrıldığında bir "nihai cevap" üretir ve öz-denetim ile doğrulama
    kapısı onu ikinci, üçüncü kez çalıştırır. `_outcome` içinde yayınlamak, çift
    basma hatasını çözerken aynı hatayı düzeltici turlarda çoğaltırdı.

    Üç kapı vardır ve üçü de gereklidir:

    - `depth == 0` — alt-ajanın cevabı kullanıcının turu değildir; o zaten araç
      sonucu olarak özetlenip basılır.
    - `not internal` — öz-denetim ve doğrulama düzeltmesi `run_agent`'ı YENİDEN
      çağırır ve bunlar `depth=0`'dır. Bayrak olmadan düzeltici tur da cevabını
      yayınlıyor, dış tur aynı metni ikinci kez basıyordu (gerçek koşuda cevap
      ekrana yapışık iki kez düştü).
    - `outcome.ok` ya da BÜTÇE durdurması — başarısızlık metinleri
      `ErrorOccurred`'ın tekelindedir. Bütçeyle kesilen tur istisnadır: sebep
      ayrıca yayınlanmıştır ve `final_text` modelin cevabıdır, hata metni değil.
      İkisini birden hata gibi basmak "✗ hata İş başarıyla tamamlanmıştır" gibi
      kendiyle çelişen satırlar üretiyordu (ölçüldü).
    - `not answer_streamed` — gerçekten akıtan sağlayıcılarda cevap ekrana zaten
      ulaştı. İki yol asla aynı anda çalışmaz.
    """
    if internal or depth != 0 or outcome.answer_streamed:
        return
    if not (outcome.ok or outcome.budget_stopped):
        return
    if not outcome.final_text.strip():
        return
    deps.publisher.publish(TurnAnswered(channel=deps.channel, text=outcome.final_text))


# --------------------------------------------------------------------------- #
# Döngü
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class _State:
    """TEK bir `_drive` çağrısının muhasebesi.

    Tur geneli sayaçlar burada DEĞİL `deps.budget` içindedir: iç içe düzeltici turlar
    aynı bütçeyi paylaşmalıdır. Buradakiler yalnızca bu çağrının raporlanan sonucunu
    üretir ve çağıran tarafından toplanır.
    """

    tool_calls_made: int = 0
    mutating_tool_calls_made: int = 0
    failed_tool_calls: int = 0
    model_calls_made: int = 0
    tool_rounds: int = 0
    tool_calls_last_turn: int = 0
    evidence_reprompts: int = 0
    #: "Hiç araç çağırmadan bitirme" kapısının kaç kez konuştuğu. Bir kezle sınırlı.
    never_acted_prompts: int = 0
    #: Bu tur bir İÇ düzeltici tur mu (öz-denetim, doğrulama kapısı)? İç turlar
    #: araçsız bitebilir ve bu meşrudur: asıl işi dış tur zaten yapmıştır, iç tur
    #: yalnızca düzeltir ya da açıklar.
    internal: bool = False
    tool_contract_abort: str = ""
    #: Bir araç "bu iş benimle YAPILAMAZ" dedi mi? (şifre duvarı, oturum kapısı…)
    #
    # Eylem-kanıtı kapısı buna bakar. Kapı, kanıt yokluğunu her zaman modelin
    # tembelliği sayıyordu ve dürüst "erişemedim" cevabını "İşlem tamamlanmadı"
    # metniyle EZİYORDU. Ölçülen sonuç: harness modeli, yapamadığı işi yapmış gibi
    # göstermeye — yani uydurmaya — itiyordu.
    capability_wall: bool = False
    #: Bu çağrıda nihai cevap metni GERÇEKTEN aktı mı? `TurnAnswered` buna bakar.
    answer_streamed: bool = False
    #: Arka arkaya kaç araç turu HİÇBİR değişiklik üretmedi. Keşif kapısı buna bakar.
    read_only_rounds: int = 0
    #: Keşif kapısı bu turda kaç kez konuştu.
    explore_pushes: int = 0
    #: Arka arkaya başarısız olan DEĞİŞTİRİCİ çağrı sayısı. Düzenleme döngüsü kapısı.
    failed_mutations_in_row: int = 0
    #: Döngü kapısı bu turda kaç kez konuştu.
    edit_loop_pushes: int = 0
    #: Modele en son kaç değişiklik kaydı bildirildi.
    logged_changes: int = 0
    #: "Dosya yok" ile düşen okumaların İSTENEN yolları (öneri araması için).
    missing_paths: list[str] = field(default_factory=list)
    #: Başarıyla okunan dosya sayısı. Yanlış-dizin hipotezi buna bakar.
    successful_file_reads: int = 0
    #: Yanlış dizin uyarısı verildi mi?
    warned_wrong_workspace: bool = False


async def _drive(
    messages: list[Message],
    deps: AgentDeps,
    registry: ToolRegistry,
    *,
    plan_mode: bool,
    allowed_tools: set[str] | None = None,
    step_limit: int | None = None,
    execution: ExecutionPolicy,
    internal: bool = False,
) -> AgentOutcome:
    state = _State(internal=internal)
    budget = deps.require_budget()
    final_text = ""
    # Tur geneli model çağrısı sınırı BÜTÇEDEDİR: iç içe düzeltici turlar aynı
    # bütçeden yer. Buradaki `local_limit` yalnızca BU çağrıyı daha da daraltır
    # (alt-ajanın `step_limit`'i ve Web AI'nın tur başı sınırı).
    local_limit = step_limit
    if execution.max_model_calls is not None:
        local_limit = min(local_limit or execution.max_model_calls, execution.max_model_calls)
    local_calls = 0

    while True:
        if budget.model_calls_exhausted or (local_limit is not None and local_calls >= local_limit):
            return _halt(final_text, messages, state, budget, BudgetStop.MODEL_CALLS, deps)
        local_calls += 1
        time_stop = budget.time_stop_reason()
        if time_stop is not None:
            return _halt(final_text, messages, state, budget, time_stop, deps)
        remaining = budget.next_timeout_s()

        try:
            if remaining is None:
                result = await _call_model(
                    messages,
                    deps,
                    registry,
                    allowed_tools,
                    state=state,
                    execution=execution,
                    offer_tools=execution.offer_tools,
                )
            else:
                async with asyncio.timeout(max(1.0, remaining)):
                    result = await _call_model(
                        messages,
                        deps,
                        registry,
                        allowed_tools,
                        state=state,
                        execution=execution,
                        offer_tools=execution.offer_tools,
                        timeout_s=min(deps.config.runtime.request_timeout_s, remaining),
                    )
        except TimeoutError:
            reason = budget.time_stop_reason() or BudgetStop.DEADLINE
            return _halt(final_text, messages, state, budget, reason, deps)

        state.model_calls_made += 1
        budget.record_model_call()
        if _is_tool_contract_error(result.error):
            if budget.take_contract_repair():
                if result.text.strip():
                    messages.append(Message("assistant", result.text))
                messages.append(
                    reflexion.tool_contract_repair_note(result.error or "geçersiz çağrı")
                )
                # Onarım SESSİZ kalmamalı: her onarım fazladan bir model çağrısı
                # harcar ve tekrarlarsa turu bitirir. Kullanıcı turun neden
                # uzadığını göremezse Fusion'ı yavaş sanır — ekranda hiçbir iz
                # yokken arka planda üç çağrı yanmış olabilir.
                deps.publisher.publish(ToolCallRepaired())
                continue
            budget.halt(BudgetStop.CONTRACT_UNREPAIRABLE)
            _publish_budget_stop(deps, budget, state)
            return _outcome(
                _tool_contract_abort_message(result.error or "geçersiz çağrı"),
                messages,
                state,
                ok=False,
            )
        if not result.ok:
            return _outcome(result.error or "", messages, state, ok=False)

        if not result.is_usable:
            if budget.take_empty_retry():
                messages.append(reflexion.empty_response_note())
                continue
            budget.halt(BudgetStop.EMPTY_RESPONSES)
            _publish_budget_stop(deps, budget, state)
            return _outcome(final_text, messages, state)

        messages.append(Message("assistant", result.text, tool_calls=result.tool_calls))

        if not result.tool_calls:
            final_text = result.text
            # `capability_wall`: bir araç işin kendisiyle yapılamayacağını bildirdiyse
            # kanıt istemek anlamsızdır. Modeli zorlamak onu uydurmaya iter ve dürüst
            # cevabı "İşlem tamamlanmadı" metniyle ezer — kullanıcı ne olduğunu
            # öğrenemez. Kanıt yokluğunun sebebi burada BİLİNİYOR.
            if (
                not plan_mode
                and execution.requires_tool_evidence
                and not state.capability_wall
                # Yanlış dizinde kanıt aramak anlamsızdır: değiştirilecek dosya
                # zaten yok. Zorlamak modeli iş uydurmaya iten üçüncü kapıydı.
                and not state.warned_wrong_workspace
                and not _tool_evidence_satisfied(execution, budget)
            ):
                if state.evidence_reprompts < execution.max_evidence_reprompts:
                    state.evidence_reprompts += 1
                    messages.append(
                        reflexion.tool_evidence_required_note(execution.required_effect)
                    )
                    continue
                return _outcome(
                    reflexion.unverified_action_message(execution.required_effect),
                    messages,
                    state,
                    ok=False,
                )
            continue_note = _auto_continue_note(
                final_text,
                deps,
                state,
                plan_mode=plan_mode,
                execution=execution,
                truncated=result.truncated,
            )
            if continue_note is not None:
                messages.append(continue_note)
                continue
            return _outcome(final_text, messages, state)

        if execution.max_tool_rounds is not None and state.tool_rounds >= execution.max_tool_rounds:
            return _halt(final_text, messages, state, budget, BudgetStop.TOOL_ROUNDS, deps)

        before = _progress_marker(deps, state)
        errored = await _run_tools(
            result.tool_calls, messages, deps, registry, state, execution=execution
        )
        budget.record_round(progressed=_progress_marker(deps, state) != before)
        # Keşif sayacı: değiştirici bir araç çalıştığı anda sıfırlanır.
        state.read_only_rounds = 0 if state.mutating_tool_calls_made > 0 else (
            state.read_only_rounds + 1
        )
        if state.tool_contract_abort:
            budget.halt(BudgetStop.REPEATED_CALL)
            _publish_budget_stop(deps, budget, state)
            return _outcome(state.tool_contract_abort, messages, state, ok=False)
        if budget.idle:
            return _halt(final_text, messages, state, budget, BudgetStop.NO_PROGRESS, deps)
        if _stuck_editing(state, plan_mode=plan_mode):
            state.edit_loop_pushes += 1
            messages.append(reflexion.repeated_edit_note(state.failed_mutations_in_row))
            # Sayaç SIFIRLANMAZ. Sıfırlamak, notun gösterdiği çıkışı tam da model
            # onu izlemeye çalıştığı anda kapatıyordu: not "write_file ile yeniden
            # yaz" diyor, model deniyor, ama toptan-yazma engelinin kalkması aynı
            # sayaca bakıyor ve sayaç yeni sıfırlanmış oluyordu (ölçüldü — tur ölü
            # kilide düştü). Kapının kaç kez konuştuğu ayrı sayaçta tutulur.
        elif errored and deps.config.runtime.reflexion and not plan_mode:
            messages.append(reflexion.note(persistent=False))
        if _looks_like_wrong_workspace(state):
            state.warned_wrong_workspace = True
            oneri = find_workspace_for(
                tuple(state.missing_paths), deps.tool_context.root
            )
            messages.append(
                reflexion.wrong_workspace_note(
                    str(deps.tool_context.root), str(oneri) if oneri else ""
                )
            )
        _record_changes(messages, deps, state)
        if _needs_push_to_act(state, plan_mode=plan_mode, execution=execution):
            state.explore_pushes += 1
            state.read_only_rounds = 0
            messages.append(reflexion.enough_exploring_note(MAX_READ_ONLY_ROUNDS))


def _progress_marker(deps: AgentDeps, state: _State) -> tuple[int, int]:
    """Turun ilerleyip ilerlemediğini ölçen iki sayı.

    Başarılı araç sayısı VE dokunulan dosya sayısı birlikte bakılır: bir tur yalnızca
    okuma yapmış olabilir (dosya sayısı artmaz ama iş yapılmıştır) ya da yalnızca
    yazma (ikisi de artar). İkisi de sabit kaldıysa o turda hiçbir şey olmamıştır.
    """
    return state.tool_calls_made, len(deps.tool_context.touched)


def _halt(
    final_text: str,
    messages: list[Message],
    state: _State,
    budget: TurnBudget,
    reason: BudgetStop,
    deps: AgentDeps,
) -> AgentOutcome:
    """Bütçe sebebiyle turu bitir, sebebini YAYINLA ve sonucu döndür.

    `ok=False`: bütçeyle kesilen bir tur tamamlanmış sayılmaz. Ders çıkarımı ve
    öz-denetim bu bayrağa bakar; kesilen turu başarı gibi öğrenmek zararlıdır.
    """
    budget.halt(reason)
    _publish_budget_stop(deps, budget, state)
    text = final_text.strip()
    outcome = _outcome(text, messages, state, hit_step_limit=True, ok=False)
    # Sebep AZ ÖNCE yayınlandı. `final_text` modelin cevabıdır, hata metni
    # değildir; ikisini birden hata gibi basmak "✗ hata İş başarıyla
    # tamamlanmıştır" gibi kendiyle çelişen satırlar üretiyordu (ölçüldü).
    outcome.budget_stopped = True
    return outcome


def _publish_budget_stop(deps: AgentDeps, budget: TurnBudget, state: _State) -> None:
    if budget.stop is None:
        return
    deps.publisher.publish(
        TurnBudgetExhausted(
            reason=budget.stop.value,
            model_calls=budget.model_calls,
            tool_rounds=state.tool_rounds,
            idle_rounds=budget.idle_rounds,
            elapsed_s=budget.elapsed_s,
        )
    )


def _outcome(
    final_text: str,
    messages: list[Message],
    state: _State,
    *,
    hit_step_limit: bool = False,
    ok: bool = True,
) -> AgentOutcome:
    return AgentOutcome(
        final_text=final_text,
        messages=messages,
        tool_calls_made=state.tool_calls_made,
        hit_step_limit=hit_step_limit,
        ok=ok,
        mutating_tool_calls_made=state.mutating_tool_calls_made,
        failed_tool_calls=state.failed_tool_calls,
        model_calls_made=state.model_calls_made,
        answer_streamed=state.answer_streamed,
        wrong_workspace=state.warned_wrong_workspace,
    )


def _tool_evidence_satisfied(execution: ExecutionPolicy, budget: TurnBudget) -> bool:
    """Gerçek eylem isteği başarılı bir araç sonucu ile kanıtlandı mı?

    Kanıt BÜTÇEDEN okunur, turun yerel durumundan değil: doğrulama düzeltmesi ve
    öz-denetim `run_agent`'ı yeniden çağırır ve taze bir durumla başlar. Kanıt orada
    tutulsaydı iç içe tur, ana turun zaten yaptığı işi baştan kanıtlamak zorunda
    kalırdı — ölçüldü, model işi yapmışken düzeltici tur "işlem tamamlanmadı" dedi.
    """

    effect = execution.required_effect
    if effect is None:
        return True
    evidence = budget.successful_tool_evidence
    if effect == "git_push":
        return any(
            name == "run_shell" and _shell_contains_git_action(args, "push")
            for name, args, _ in evidence
        )
    if effect == "git_commit":
        return any(
            name == "run_shell" and _shell_contains_git_action(args, "commit")
            for name, args, _ in evidence
        )
    if effect == "shell_action":
        return any(name == "run_shell" for name, _, _ in evidence)
    if effect == "workspace_mutation":
        return any(mutating for _, _, mutating in evidence)
    if effect == "web_lookup":
        return any(
            name in {"web_search", "web_fetch", "read_url_content"} for name, _, _ in evidence
        )
    if effect == "workspace_read":
        return any(
            name
            in {
                "read_file",
                "view_file",
                "list_dir",
                "search_code",
                "grep_search",
                "search_codebase",
                "glob",
                "git",
            }
            for name, _, _ in evidence
        )
    return bool(evidence)


def _shell_contains_git_action(args: dict[str, object], action: str) -> bool:
    command = args.get("command")
    if not isinstance(command, str):
        return False
    # Yalnızca gerçek bir komut segmentindeki git çağrısını kabul et.
    # `echo git push` gibi yalnızca metin basan komutlar kanıt sayılmaz;
    # `cd repo && git -C . push`, `sudo git push` ve `env X=1 git push` sayılır.
    pattern = (
        rf"(?:^|(?:&&|\|\||;|\n)\s*)"
        rf"(?:(?:sudo|command)\s+)?"
        rf"(?:env(?:\s+[A-Za-z_][A-Za-z0-9_]*=[^\s;&|]+)+\s+)?"
        rf"git\b(?:(?![;&|\n]).){{0,180}}\b{re.escape(action)}\b"
    )
    return bool(re.search(pattern, command, re.IGNORECASE))


async def _call_model(
    messages: list[Message],
    deps: AgentDeps,
    registry: ToolRegistry,
    allowed_tools: set[str] | None = None,
    *,
    state: _State,
    execution: ExecutionPolicy,
    offer_tools: bool = True,
    timeout_s: float | None = None,
) -> ModelResult:
    """Modeli akıtarak çağır; metin parçaları olay olarak yayınlanır."""
    runtime = deps.config.runtime
    spec = select_agent_spec(deps.config, deps.task_type)
    request = CompletionRequest(
        messages=tuple(messages),
        temperature=runtime.temperature,
        max_tokens=runtime.max_tokens,
        timeout_s=timeout_s or runtime.request_timeout_s,
        max_retries=runtime.max_retries,
        tools=(
            tuple(registry.schemas(_permitted(allowed_tools, registry, execution)))
            if offer_tools
            else ()
        ),
        reasoning_effort=effort_for_spec(spec, runtime.reasoning_effort),
    )
    provider = build_provider(
        spec,
        publisher=deps.publisher,
        retry_delays_s=runtime.retry_delays_s,
        channel=deps.channel,
        health=deps.health,
        web_sessions=web_registry_for(deps.config),
    )

    result: ModelResult | None = None
    async for item in provider.stream(request):
        if isinstance(item, TextChunk):
            # Beyan değil GÖZLEM: metin gerçekten aktıysa turun cevabı ekrana
            # ulaşmış demektir ve `TurnAnswered` ikinci kez basmamalıdır. Sarmalayıcı
            # zinciri ne olursa olsun (yedek, tekrar deneme) bu ölçüm doğrudur —
            # sağlayıcının "akıtır mıyım" beyanına güvenmek yanıltıcı olurdu.
            if not item.provisional:
                state.answer_streamed = True
        elif isinstance(item, StreamDone):
            result = item.result
    return result or ModelResult(
        name=spec.name,
        model=spec.model,
        text="",
        latency_ms=0,
        ok=False,
        error="Model akışı sonuç üretmeden bitti.",
    )


#: Araç kısıtlaması olsa bile daima sunulan araçlar. Bunlar olmadan agent planlayamaz
#: ya da belirsizliği gideremez.
ALWAYS_ALLOWED = frozenset({"todo_write", "ask_user", "find_skill", "read_skill"})


def _permitted(
    allowed_tools: set[str] | None,
    registry: ToolRegistry,
    execution: ExecutionPolicy,
) -> set[str] | None:
    """Modele sunulacak araç adlarını belirle.

    Mutation izni yoksa değiştirici araçların ŞEMASI hiç gönderilmez: modele
    yapamayacağı bir yeteneği göstermek, denemesine ve turu boşa harcamasına yol açar.
    """
    names = (
        set(registry.names())
        if allowed_tools is None
        else ((allowed_tools | ALWAYS_ALLOWED) & set(registry.names()))
    )
    if not execution.allow_mutation:
        names = {
            name
            for name in names
            if not (registry.get(name) is not None and registry.get(name).mutating)  # type: ignore[union-attr]
        }
    return names


def _auto_continue_note(
    final_text: str,
    deps: AgentDeps,
    state: _State,
    *,
    plan_mode: bool,
    execution: ExecutionPolicy,
    truncated: bool,
) -> Message | None:
    """Tur devam ettirilecekse modele enjekte edilecek notu döndür, yoksa `None`.

    Not TÜRÜ ayrılır: "işi yarım bıraktın" ile "iş yapmadan bana soru sordun" farklı
    davranışlardır ve modele farklı şey söylenmelidir.
    """
    if plan_mode:
        return None
    # Yanlış dizinde "devam et" demek, modeli iş UYDURMAYA iter. Doğru cevap
    # "bu dizinde o dosyalar yok" demektir ve o cevap zaten verilmiştir; onu
    # zorlamak turu kullanıcının istemediği bir işe çevirir (ölçüldü).
    if state.warned_wrong_workspace:
        return None
    # Gerçek çıktı bütçesi dolduysa sağlayıcıdan bağımsız olarak bir kez devam et.
    # Bu, sağlayıcıdan gelen sert bir olgudur ve her teşhisin önündedir.
    if truncated:
        return _spend(deps, reflexion.auto_continue_note())
    # ÖZGÜL TEŞHİS GENELDEN ÖNCE GELİR. "İş yapmadan soru sordu" turu çoğu zaman
    # kısa da olur ve `looks_unfinished` onu önce yakalayıp "işi yarım bıraktın"
    # notunu gönderiyordu. İki not da modeli çalıştırır ama yanlış olanı yanlış
    # şeyi düzeltmesini söyler: model yarım kalan işi arar, oysa sorun kullanıcıya
    # geri sormasıdır.
    if _asked_instead_of_acting(final_text, state, deps.require_budget()):
        return _spend(deps, reflexion.asked_instead_of_acting_note())
    # "Hiç araç çağırmadı" en özgül teşhistir ve genel sezgisellerden ÖNCE gelir:
    # model işi yarım bırakmış değil, hiç başlamamıştır.
    if _never_acted(state, execution):
        state.never_acted_prompts += 1
        return _spend(deps, reflexion.never_acted_note())
    if not execution.heuristic_auto_continue:
        # Web modellerinde kısa ama geçerli ".env / README" gibi cevaplar eski
        # sezgisel tarafından yarım sanılıyordu. Bekleyen todo yoksa ek çağrı açma.
        wanted = deps.tool_context.todos.has_pending
    else:
        wanted = reflexion.looks_unfinished(
            final_text,
            tool_calls_last_turn=state.tool_calls_last_turn,
            has_pending_todos=deps.tool_context.todos.has_pending,
        )
    if not wanted:
        wanted = _stopped_without_acting(state, deps.require_budget(), execution=execution)
    return _spend(deps, reflexion.auto_continue_note()) if wanted else None


def _spend(deps: AgentDeps, note: Message) -> Message | None:
    """Devam hakkını harca ve notu döndür; hak kalmadıysa `None`.

    Hak yalnızca GERÇEKTEN devam edilecekse harcanır; sırayı tersine çevirmek
    devam etmeyen turlarda da bütçe yakardı.
    """
    bekleyen = deps.tool_context.todos.pending_count
    return note if deps.require_budget().take_auto_continue(pending_todos=bekleyen) else None


def _asked_instead_of_acting(final_text: str, state: _State, budget: TurnBudget) -> bool:
    """Model iş yapmadan turu kullanıcıya soru sorarak mı bitirdi?

    Gözlemlendi (Gemini web): model sekiz araç çağırıp dizin yapısını okudu, hiçbir
    şey değiştirmeden "ne yapmak istediğinizi belirtin" dedi ve tur bitti sayıldı.
    Kullanıcı görevi zaten vermişti.

    `_stopped_without_acting` bunu yakalayamıyor çünkü yalnızca BUGFIX/FEATURE gibi
    türlerde çalışır; "analiz et" sınıfına düşen istek kapının dışında kalır. Bu kapı
    o şartı GENİŞLETMEZ — genişletmek "şu dosyayı açıkla" gibi meşru salt-okuma
    turlarına da bedava bir devam çağrısı yaptırırdı. Bunun yerine dar ve doğrudan
    belirtiye bakar: iş yok + kapanışta soru işareti.

    `ask_user` çağıran tur DIŞARIDADIR: model doğru aracı kullanmışsa soru meşrudur
    ve cevabı zaten geçmişe girmiştir.
    """
    if state.tool_calls_made == 0 or state.mutating_tool_calls_made > 0:
        return False
    if not reflexion.ends_with_question(final_text):
        return False
    return not any(
        name in _ASKING_TOOLS or name in _DELEGATION_TOOLS
        for name, _, _ in budget.successful_tool_evidence
    )


#: Kullanıcıya soruyu DOĞRU yoldan soran araç. Çağrıldıysa tur zorlanmaz.
_ASKING_TOOLS = frozenset({"ask_user"})


#: Aynı turda kaç başarısız değiştirici çağrıdan sonra çıkış yolu gösterilir.
#
# İki deneme normaldir (ilk `old` tutmaz, model düzeltir). Üçüncüde model artık
# yaklaşımını değiştirmiyor, aynı şeyi daha dar pencereyle tekrarlıyor.
MAX_FAILED_MUTATIONS_IN_ROW = 3
#: Toptan yazma çıkışının açıldığı başarısız düzenleme sayısı.
#
# Döngü notundan DAHA ERKEN açılır: boşta-tur kapısı üç ilerlemesiz turda turu
# öldürüyor ve çıkış üçüncüde açılırsa hiç kullanılamıyor (ölçüldü — model
# write_file'a kaçtı, engellendi, tur öldü). İki başarısız hedefli düzenleme,
# modelin 'old' metnini tutturamadığını göstermeye yeter.
MAX_EDITS_BEFORE_REWRITE = 2
#: Döngü kapısının bir turda en fazla kaç kez konuşacağı.
MAX_EDIT_LOOP_PUSHES = 2


def _stuck_editing(state: _State, *, plan_mode: bool) -> bool:
    """Model aynı düzenlemeyi tekrar tekrar deneyip düşüyor mu?"""
    if plan_mode or state.edit_loop_pushes >= MAX_EDIT_LOOP_PUSHES:
        return False
    return state.failed_mutations_in_row >= MAX_FAILED_MUTATIONS_IN_ROW


#: Okuma araçları. Yanlış-dizin hipotezi yalnızca bunlara bakar.
_FILE_READ_TOOLS = frozenset({"read_file", "view_file"})
#: Kaç "dosya yok" hatasından sonra yanlış dizin hipotezi kurulur.
#
# İki hata rastlantı olabilir (model yanlış ad tahmin etti). Üçüncüde ve HİÇBİR
# dosya okunamamışken, en olası açıklama çalışma dizininin yanlış olmasıdır.
MAX_MISSING_READS = 3


def _looks_like_wrong_workspace(state: _State) -> bool:
    """Görevdeki dosyaların hiçbiri bu dizinde yok gibi mi görünüyor?

    Ölçüldü: kullanıcı fusion'ı yanlış klasörde açtı. Model dört dosyayı da
    bulamadı, sonra öz-denetim düzeltici turunda GÖREVİ TERK ETTİ ve kendine yeni
    iş uydurdu — o projenin README'sini okuyup "test paketini çalıştır" diye todo
    listesi yazdı. Kullanıcının sorduğu şeyle hiç ilgisi yoktu.

    Doğru davranış durmaktır: bu bir "yapılamayan iş"tir, uydurulacak bir iş değil.
    """
    if state.warned_wrong_workspace or state.successful_file_reads > 0:
        return False
    return len(state.missing_paths) >= MAX_MISSING_READS


def _record_changes(messages: list[Message], deps: AgentDeps, state: _State) -> None:
    """Değişen dosyaları modele OLGU olarak hatırlat.

    Model kendi işini takip edemiyor: bir koşuda üç dosya oluşturup kapanışta
    "herhangi bir değişiklik yapılmamıştır" dedi, başka bir koşuda dokunmadığı
    dosyayı "güncelledim" dedi. Kayıt yalnızca liste BÜYÜDÜĞÜNDE eklenir; her
    turda tekrarlamak promptu şişirir.
    """
    yollar = deps.tool_context.changes.paths
    if len(yollar) == state.logged_changes:
        return
    state.logged_changes = len(yollar)
    from ...tools.files import display_path

    messages.append(
        reflexion.change_log_note(tuple(display_path(deps.tool_context, y) for y in yollar))
    )


def _needs_push_to_act(
    state: _State, *, plan_mode: bool, execution: ExecutionPolicy
) -> bool:
    """Model okumaktan çıkıp yazmaya itilmeli mi?

    Yalnızca görev GERÇEKTEN değişiklik istiyorsa konuşur (`requires_tool_evidence`
    ya da karmaşık görev türü); "şu dosyayı açıkla" gibi bir işte okumak zaten
    doğru davranıştır ve dürtmek turu bozardı.

    Ölçüt yapısaldır: arka arkaya kaç araç turu hiçbir mutasyon üretmedi. Metne
    bakılmaz, niyet tahmin edilmez.
    """
    if plan_mode or not execution.allow_mutation:
        return False
    if not (execution.requires_tool_evidence or execution.complex_task):
        return False
    if state.mutating_tool_calls_made > 0:
        return False
    if state.explore_pushes >= MAX_EXPLORE_PUSHES:
        return False
    return state.read_only_rounds >= MAX_READ_ONLY_ROUNDS


def _stopped_without_acting(
    state: _State, budget: TurnBudget, *, execution: ExecutionPolicy
) -> bool:
    """Model kod değiştirmesi gereken bir işte yalnızca OKUYUP durdu mu?

    Ölçüldü (Gemini web, aynı görev üç kez): iki koşuda model dosyaları okudu, sonra
    araç çağrısı ÜRETMEDEN düzyazı yazdı — birinde kodu markdown bloğu olarak döktü,
    ötekinde "ilgili dosyaları okuma aracını çağırıyorum" deyip hiç çağırmadı.
    Fusion ikisini de nihai cevap sayıp turu bitirdi; hiçbir dosya değişmedi.

    Kanıt kapısı bunu yakalayamıyordu çünkü `required_effect` dar metin kalıplarına
    bakar ve "testleri geçir" ifadesinde boş kalır. Burada karar GÖREV TÜRÜNDEN
    verilir: iş kod değiştirmeyi gerektiren cinstense ve tur boyunca hiçbir şey
    değişmediyse, düzyazı bir teslim değildir.

    Duyuru metnini dilsel olarak tanımaya çalışmaz — o yol dile ve kalıba bağımlıdır.
    Bakılan tek şey yapısaldır: iş başlamış (araç çağrılmış) ama hiçbir mutasyon
    olmamıştır. Hak `max_auto_continues` ile sınırlıdır; model ısrar ederse tur biter.

    Devretme bu kuralın DIŞINDADIR: işi alt-ajana veren bir turun kendisi dosya
    değiştirmez ve değiştirmesi de beklenmez. Alt-ajanın kendi bütçesi ve kapıları
    zaten oradadır; ana turu ikinci kez zorlamak yalnızca çağrı harcar.
    """
    if not execution.complex_task or state.tool_calls_made == 0:
        return False
    if state.mutating_tool_calls_made > 0:
        return False
    return not any(name in _DELEGATION_TOOLS for name, _, _ in budget.successful_tool_evidence)


#: İşi devreden araçlar — bunları çağıran tur "hiçbir şey yapmadı" sayılmaz.
_DELEGATION_TOOLS = frozenset({"spawn_agent", "invoke_subagent"})


def _never_acted(state: _State, execution: ExecutionPolicy) -> bool:
    """Karmaşık bir görevde model HİÇ araç çağırmadan turu kapatıyor mu?

    Ölçüldü (canlı koşu): model üç tur boyunca "somut bir görev almadım, dizin
    içeriğini listeliyorum" tarzı düz yazı üretti, tek satır değişmedi ve tur
    `ok=True` ile kapandı. Hiçbir kapı konuşmadı çünkü var olan iki kapı da
    (`_stopped_without_acting`, `_asked_instead_of_acting`) sıfır çağrıyı
    dışarıda bırakıyor — ikisi de "araç çağırdı ama değiştirmedi" için yazılmış.
    En kötü durum ise "hiç çağırmadı"dır ve tam olarak o kapsam dışıydı.

    Kanıt kapısı bu boşluğu doldurmuyor: yalnızca görevden somut bir etki
    çıkarılabildiğinde (`required_effect`) açılıyor, yani her görevde değil.

    BİR KEZ konuşur. Model ikinci kez de araçsız gelirse zorlamak çağrı harcamaktır;
    o noktada cevabı olduğu gibi teslim etmek dürüst olandır.
    """
    if not execution.complex_task or state.internal:
        return False
    if state.tool_calls_made > 0:
        return False
    # Kullanıcı "araç kullanma" dediyse ya da araçlar hiç sunulmadıysa araçsız tur
    # BEKLENEN davranıştır. `max_evidence_reprompts` bu durumda zaten sıfırlanıyor;
    # aynı sinyal burada da geçerlidir, ikinci bir bayrak icat edilmez.
    if not execution.offer_tools or execution.max_evidence_reprompts <= 0:
        return False
    return state.never_acted_prompts < 1


def _targeted_edit_required(
    name: str,
    args: dict[str, object],
    deps: AgentDeps,
    execution: ExecutionPolicy,
    state: _State,
) -> list[str]:
    """Taklit araç kullanan modelde var olan dosya toptan yeniden yazılamaz.

    Ölçüldü (Gemini web, aynı görev altı koşu): yıkıcı başarısızlıkların HEPSİNDE
    `write_file` vardı — bozuk sözdizimi, 13 ruff hatası, toplanamayan test dosyası.
    Yalnızca `edit_file` kullanan koşular eksik kalabildi ama kodu hiç bozmadı.

    Sebep yapısal: yüz satırlık bir dosyayı baştan üretmek modele yüz satırlık hata
    yüzeyi açar, hedefli düzenleme birkaç satırlık. Ücretsiz bir web modeli o yüzeyi
    tutarlı biçimde temiz geçemiyor.

    Karar MOTOR katmanında verilir çünkü sağlayıcı politikasıdır; `files.py`
    sağlayıcıdan habersiz kalır. Yeni dosya yazmak serbesttir — kısıt yalnızca var
    olan bir dosyanın ÜZERİNE yazmaya karşıdır.

    Kısıt agent'ın BU TURDA kendi oluşturduğu dosyayı kapsamaz. Ölçülen ölü kilit:
    `scaffold_web` iskeleyi diske yazıyor ve "şimdi bunları DOLDUR" diyor; ama iskele
    dosyasını doldurmak tanımı gereği toptan yazmadır ve kural onu engelliyordu.
    Model `write_file` deneyip bloklanıyor, `edit_file` deneyip 'old' metnini
    tutturamıyor, içeriği öğrenmek için yeniden okumaya kalkınca tekrar kapısına
    takılıyor ve tur "ilerleme yok" ile ölüyordu. Kuralın gerekçesi (kullanıcının
    kodunu koru) dakikalar önce agent'ın kendi yazdığı yer tutucu dosyada geçersizdir.
    """
    if not execution.is_web or name not in _FULL_WRITE_TOOLS:
        return []
    raw = args.get("path")
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        hedef = resolve_path(deps.tool_context, raw)
    except FusionError:
        return []
    if not hedef.exists():
        return []
    if deps.tool_context.changes.was_created_this_turn(hedef):
        return []
    if _rewrite_is_last_resort(hedef, deps, state):
        return []
    return [
        f"'{raw}' zaten var. Var olan dosyayı toptan yeniden yazma — önce read_file "
        "ile ilgili satırları gör, sonra replace_range ile YALNIZCA yeni parçayı gönder. "
        "Kısa exact-text değişimi dışında edit_file'a düşme."
    ]


def _rewrite_is_last_resort(hedef: Path, deps: AgentDeps, state: _State) -> bool:
    """Toptan yazma artık TEK çıkış mı?

    Kural olmadan ölçülen ölü kilit: `edit_file` üç kez "'old' bulunamadı" verdi,
    model `write_file`'a kaçtı ve KOŞULSUZ engellendi, tekrar `edit_file` denedi,
    yine tutmadı ve tur "ilerleme yok" ile öldü. Model doğru dosyayı, doğru
    niyetle hedeflemişti; çıkışı olmayan bir kapıya çarptı.

    İki koşul BİRLİKTE aranır:

    - Hedefli düzenleme bu turda arka arkaya birkaç kez düşmüş olmalı. Bir-iki
      başarısızlık normaldir ve model kendi kendine toparlar.
    - Model dosyanın TAMAMINI okumuş olmalı. Kuralın gerekçesi "yüz satırlık
      dosyayı baştan üretmek yüz satırlık hata yüzeyi açar" idi; içeriğin tamamı
      görülmüşse yazma artık kör değildir ve o gerekçe düşer.
    """
    if state.failed_mutations_in_row < MAX_EDITS_BEFORE_REWRITE:
        return False
    return hedef in deps.tool_context.fully_read


#: Dosyanın tamamını değiştiren araçlar.
_FULL_WRITE_TOOLS = frozenset({"write_file"})

#: Onay açısından değiştirici sayılan ama TEKRAR EDİLMESİ meşru olan araçlar.
#
# Tekrar imzasında değiştirici araçların çağı sıfırlanır ("aynı yazma iki kez
# istenmez"). `run_shell` bu kuralın altında yanlış kalıyordu: doğrulama komutu
# tam olarak tekrarlanmak İÇİN vardır. Ölçüldü — model kodu düzeltti, `npm test`
# çalıştırmak istedi ve TOOL_CALL_DUPLICATE ile engellendi; düzeltmenin işe
# yarayıp yaramadığını doğrulayamadı.
#
# Çağa bağlanmak doğru davranışı verir: değişiklik olmadan aynı komutu tekrar
# etmek yine tekrardır, değişiklikten SONRA tekrar etmek yeni bilgidir.
_RERUNNABLE_TOOLS = frozenset({"run_shell"})


# --------------------------------------------------------------------------- #
# Araç yürütme
# --------------------------------------------------------------------------- #


async def _run_tools(
    calls: tuple[ToolCall, ...],
    messages: list[Message],
    deps: AgentDeps,
    registry: ToolRegistry,
    state: _State,
    *,
    execution: ExecutionPolicy,
) -> bool:
    """Çalıştırmadan ÖNCE doğrula; bozuk ve tekrar eden çağrı zincirini kes.

    Sıra önemlidir: sözleşme ihlali (bozuk JSON, bilinmeyen araç, eksik alan) araç
    hiç çalışmadan yakalanır ve modele düzeltme şansı verilir. İkinci kez aynı hata
    gelirse tur sonlandırılır — düzeltemeyen bir model sonsuza kadar denemez.
    """
    state.tool_calls_last_turn = len(calls)
    state.tool_rounds += 1
    errored = False

    budget = deps.require_budget()
    for call in calls:
        args, parse_error = _parse_arguments_checked(call.arguments)
        tool = registry.get(call.name)
        # İmza TUR BOYUNCA paylaşılır: düzeltici turun ana turdaki çağrıyı birebir
        # tekrar etmesi, her tura ayrı ayrı bakıldığında görünmeyen bir döngüdür.
        signature = budget.signature(
            call.name,
            _encode_arguments(args),
            mutating=tool is not None and tool.mutating and call.name not in _RERUNNABLE_TOOLS,
        )
        seen = budget.count_call(signature)

        contract_errors: list[str] = []
        if parse_error:
            contract_errors.append(parse_error)
        if tool is None:
            contract_errors.append(
                "bilinmeyen araç; kullanılabilir araçlar: " + ", ".join(registry.names())
            )
        else:
            function_schema = tool.schema().get("function")
            if isinstance(function_schema, dict):
                contract_errors.extend(validate_arguments(function_schema, args))

        if not contract_errors:
            contract_errors.extend(
                _targeted_edit_required(call.name, args, deps, execution, state)
            )

        if contract_errors:
            # Aynı bozuk çağrı ikinci kez geldiyse onarım hakkı harcanmaz: model
            # düzeltmiyor, tekrarlıyor.
            no_more_repairs = seen >= 1 or not budget.take_contract_repair()
            output = _tool_contract_failure(
                call.name,
                contract_errors,
                tool.schema().get("function") if tool is not None else None,
            )
            outcome = ToolOutcome.BLOCKED if no_more_repairs else ToolOutcome.FAILED
            deps.publisher.publish(
                ToolExecuted(
                    name=call.name,
                    args=args,
                    outcome=outcome,
                    output=output,
                    diff=None,
                )
            )
            messages.append(Message("tool", output, tool_call_id=call.id, name=call.name, ok=False))
            state.failed_tool_calls += 1
            errored = True
            # Tur BURADA ÖLDÜRÜLMEZ — tekrar kapısıyla (aşağıda) aynı gerekçe.
            #
            # Eskiden onarım hakkı bitince tur anında sonlandırılıyordu; tekrar kapısı
            # ise "turu kesmek o ana kadarki TÜM ilerlemeyi çöpe atar" diyerek
            # kesmiyordu. İki kapının aynı durumda farklı davranması bir çelişkiydi.
            #
            # Ölçüldü: iki bozuk JSON gönderip ÜÇÜNCÜ turda doğru hamleyi yapan bir
            # model, doğru hamlesine hiç ulaşamadan öldürülüyordu. Karar tek bir
            # otoriteye, "ilerleme yok" kapısına bırakılır: model toparlanamazsa tur
            # yine biter — ama üç şans sonra, tek hamlede değil.
            continue

        # Değiştirici araçta tek tekrar bile döngüdür: aynı yazma iki kez istenmez.
        # Okuma araçlarında çalışma alanı değişmediği sürece birkaç tekrara izin verilir.
        duplicate_limit = (
            1 if tool is not None and tool.mutating else execution.max_same_tool_without_change
        )
        # Kapı artık TÜM sağlayıcılarda açık. Eskiden yalnızca web modelleri
        # denetleniyordu; API modelleri aynı çağrıyı sınırsız tekrar edebiliyordu.
        if seen >= duplicate_limit:
            output = (
                "TOOL_CALL_DUPLICATE: Bu çağrıyı aynı argümanlarla ZATEN yaptın ve "
                "çalışma alanında o zamandan beri ilgili bir değişiklik olmadı. Fusion "
                "çağrıyı çalıştırmadı — sonucu zaten elinde. Aynı şeyi yeniden isteme; "
                "şunlardan BİRİNİ yap: yeni dosyada write_file, mevcut dosyada "
                "replace_range ile değişikliği uygula, "
                "farklı bir dosyayı read_file ile oku, eksik bilgi varsa ask_user ile "
                "sor, ya da işi bitirip sonucu söyle."
            )
            deps.publisher.publish(
                ToolExecuted(
                    name=call.name,
                    args=args,
                    outcome=ToolOutcome.BLOCKED,
                    output=output,
                    diff=None,
                )
            )
            messages.append(Message("tool", output, tool_call_id=call.id, name=call.name, ok=False))
            state.failed_tool_calls += 1
            errored = True
            # Tur BURADA ÖLDÜRÜLMEZ. Tekrarlanan bir çağrı zararsız bir verimsizliktir;
            # turu kesmek o ana kadarki TÜM ilerlemeyi çöpe atar. Ölçüldü: model dört
            # dosyayı okuyup birini düzelttikten sonra aynı dosyayı üç kez okudu ve
            # yapılan iş boşa gitti.
            #
            # Karar "ilerleme yok" kapısına bırakılır: engellenen çağrı ilerleme
            # üretmediği için boşta tur sayacı artar ve model kendini toparlayamazsa
            # tur yine biter — ama üç şans sonra, tek hamlede değil.
            continue

        pending_diff = file_diff(call.name, args, deps.tool_context)
        result, outcome = await _execute(call, args, deps, registry, execution=execution)
        if result.output.startswith(CAPABILITY_WALL_PREFIX):
            state.capability_wall = True
        if outcome is ToolOutcome.OK:
            state.tool_calls_made += 1
            if call.name in _FILE_READ_TOOLS:
                state.successful_file_reads += 1
            mutating = bool(tool is not None and tool.mutating)
            budget.successful_tool_evidence.append((call.name, args, mutating))
            if mutating:
                state.mutating_tool_calls_made += 1
                state.failed_mutations_in_row = 0
                # Çağı yalnızca DOSYA değişikliği ilerletir. `run_shell` başarılı
                # olduğunda da ilerletmek, aynı komutun tekrar imzasını her
                # seferinde tazeliyor ve tekrar kapısını `run_shell` için işlevsiz
                # bırakıyordu (bkz. `_RERUNNABLE_TOOLS`).
                if call.name not in _RERUNNABLE_TOOLS:
                    budget.record_mutation()
        elif outcome is ToolOutcome.FAILED:
            state.failed_tool_calls += 1
            errored = True
            # Sayaç YALNIZCA değiştirici çağrılarda büyür: okuma hatası (yanlış
            # dosya adı) düzenleme döngüsü değildir ve o kapıyı tetiklememeli.
            if call.name in _FILE_READ_TOOLS and result.output.startswith(FILE_MISSING_PREFIX):
                istenen = args.get("path")
                if isinstance(istenen, str):
                    state.missing_paths.append(istenen)
            if tool is not None and tool.mutating:
                state.failed_mutations_in_row += 1
                # Düşen bir düzenlemeden sonra YENİDEN OKUMA serbest kalmalı:
                # toparlanmanın tek yolu odur ve tekrar kapısı onu engelliyordu.
                budget.record_failed_mutation()

        diff = pending_diff if outcome is ToolOutcome.OK else None
        deps.publisher.publish(
            ToolExecuted(
                name=call.name,
                args=args,
                outcome=outcome,
                output=result.output,
                diff=diff,
            )
        )
        messages.append(
            Message(
                "tool",
                result.output,
                tool_call_id=call.id,
                name=call.name,
                ok=result.ok,
            )
        )
    return errored


def _encode_arguments(args: dict[str, object]) -> str:
    """Argümanları tekrar tespiti için KARARLI bir metne çevir.

    Anahtar sırası sabitlenir: aynı çağrının farklı sırayla gelmesi onu yeni bir
    çağrı yapmaz. Serileştirilemeyen bir değer varsa `repr` yeterlidir — burada
    amaç eşitlik karşılaştırması, yeniden üretilebilir bir kayıt değil.
    """
    try:
        return json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(args)


async def _execute(
    call: ToolCall,
    args: dict[str, object],
    deps: AgentDeps,
    registry: ToolRegistry,
    *,
    execution: ExecutionPolicy,
) -> tuple[ToolResult, ToolOutcome]:
    """Onaydan geçir ve çalıştır. Bilinmeyen araç da kayıt defterinin sorunu."""
    tool = registry.get(call.name)
    if tool is not None and tool.mutating and not execution.allow_mutation:
        # Yetenek kapısı onaydan ÖNCE gelir: kullanıcıya sormanın anlamı yok, bu
        # model bu işi güvenilir yapamıyor. Şema hiç sunulmadığı için buraya normalde
        # gelinmez; ikinci savunma hattıdır.
        return (
            ToolResult(MUTATION_BLOCKED_MESSAGE.format(reason=execution.mutation_block_reason)),
            ToolOutcome.BLOCKED,
        )
    if tool is not None and tool.mutating:
        decision = await deps.policy.decide(build_request(tool, args, deps.allowed_commands))
        if decision is not Decision.ALLOW:
            # Reddetme ve engelleme HATA DEĞİLDİR: refleksiyon tetiklenmemeli,
            # model yalnızca farklı bir yol denemeli.
            return ToolResult(_DECISION_MESSAGES[decision]), _DECISION_OUTCOMES[decision]

    result = await registry.execute(call.name, args, deps.tool_context)
    return result, ToolOutcome.OK if result.ok else ToolOutcome.FAILED


def _parse_arguments_checked(raw: str) -> tuple[dict[str, object], str | None]:
    """Ham argümanları ayrıştır; bozuk JSON kanıtını SİLMEDEN.

    Hatayı yutup boş sözlük döndürmek, modele "argümanların boştu" demek olurdu;
    oysa sorun JSON'un kendisidir ve model bunu bilmeden düzeltemez.
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        return {}, f"arguments geçerli JSON olmalı ({error})"
    if not isinstance(parsed, dict):
        return {}, "arguments bir JSON nesnesi olmalı"
    return parsed, None


def _is_tool_contract_error(detail: str | None) -> bool:
    return bool(detail and detail.startswith("TOOL_CALL_"))


def _tool_contract_failure(
    name: str,
    errors: list[str],
    function_schema: object,
) -> str:
    lines = ["TOOL_CALL_INVALID", f"tool: {name}", "errors:"]
    lines.extend(f"- {error}" for error in errors)
    if isinstance(function_schema, dict):
        lines.append("valid_example:")
        lines.append(render_tool_example(function_schema))
    return "\n".join(lines)


def _tool_contract_abort_message(detail: str) -> str:
    return (
        "TOOL_CALL_ABORTED: Araç sözleşmesi düzeltilemedi veya aynı çağrı tekrarlandı. "
        "Fusion güvenlik için bu turu sonlandırdı; işlem tamamlanmış kabul edilmemelidir.\n"
        + detail
    )


# --------------------------------------------------------------------------- #
# Öz-denetim ve sıkıştırma
# --------------------------------------------------------------------------- #


def _web_self_review_needed(
    task: str, kind: TaskKind, outcome: AgentOutcome, deps: AgentDeps
) -> bool:
    """Run Web-AI review only when it can improve a valid model answer.

    Provider/authentication/timeout failures are transport failures, not answer-quality
    problems. Sending them to the same model for review hides the real error and creates
    two extra browser calls. Tool failures remain reviewable after the model produces a
    usable final answer.
    """
    if not outcome.ok:
        return False
    if outcome.hit_step_limit or outcome.failed_tool_calls > 0:
        return True
    if outcome.mutating_tool_calls_made > 0:
        return True

    lowered = task.lower()
    explicit_no_tools = any(
        marker in lowered
        for marker in (
            "araç kullanma",
            "arac kullanma",
            "tool kullanma",
            "araç çağırma",
            "arac cagirma",
        )
    )
    direct_response = bool(
        re.search(
            r"^\s*(?:sadece|yalnızca|yalnizca)\b.{0,220}\b"
            r"(?:yaz|söyle|soyle|cevapla|döndür|dondur)\b",
            lowered,
            re.DOTALL,
        )
    )
    if outcome.tool_calls_made == 0 and (explicit_no_tools or direct_response):
        return False

    if outcome.tool_calls_made == 0 and len(task.strip()) <= 160:
        risky_markers = (
            "kod",
            "python",
            "javascript",
            "typescript",
            "dosya",
            "proje",
            "test",
            "hata",
            "bug",
            "düzelt",
            "duzelt",
            "sil",
            "değiştir",
            "degistir",
            "uygula",
            "patch",
        )
        if not any(marker in lowered for marker in risky_markers):
            return False

    if is_complex_kind(kind):
        return True
    # Güvenlik kipinde kullanıcı her değişikliği tek tek onaylamıştır; araç çalışan
    # bir turu denetimsiz bırakmak o kipin amacına aykırı olurdu.
    return isinstance(deps.policy, SecurityApproval) and outcome.tool_calls_made > 0


#: Düzeltici tura verilen talimat. Kullanıcının ASIL GÖREVİ tekrar edilir.
#
# Ölçüldü: talimat yalnızca "bir öz-denetim şu sorunu işaret etti" diyordu ve
# düzeltici tur görevi kaybediyordu. Model dizini baştan listeledi, dosyaları
# yeniden okudu ve "iş henüz verilmedi, ne yapmamı istiyorsunuz" diyerek turu
# bitirdi — birinci turda yapılmış işi de götürerek. Düzeltici tur bir ARA
# adımdır; hedefi kendi başına taşımalıdır.
_CORRECTION_TASK = (
    "Kullanıcının görevi şuydu:\n{task}\n\n"
    "Bu göreve devam ediyorsun; sıfırdan başlamıyorsun ve kullanıcıya görevi geri "
    "sormuyorsun.{done}\n"
    "Bir öz-denetim aşağıdaki sorunu işaret etti. Gerekiyorsa düzelt; haklı değilse "
    "kısaca neden sorun olmadığını açıkla.\n\n{feedback}"
)

#: Düzeltici tura verilen "zaten yaptıkların" özeti.
#
# Ölçüldü: düzeltici tur dizini baştan listeledi, package.json'ı yeniden okudu,
# app ve components dizinlerini gezdi ve ancak beşinci turda düzenlemeye geldi.
# Geçmiş prompta gönderiliyor ama model onu KENDİ hafızası değil bir döküm gibi
# okuyor. Ne yaptığını açıkça söylemek o beş turu geri kazandırır.
_ALREADY_DONE = "\n\nBu turda ZATEN yaptıkların (tekrarlama):\n{items}"
#: Özette gösterilecek en fazla adım. Amaç hatırlatmak, izi baştan sona dökmek değil.
MAX_DONE_ITEMS = 12


def _already_done_block(budget: TurnBudget) -> str:
    """Turda başarıyla çalışan araçları kısa bir liste olarak yaz."""
    gorulen: list[str] = []
    for name, args, _ in budget.successful_tool_evidence:
        hedef = next(
            (
                str(args[alan])
                for alan in ("path", "command", "pattern", "query")
                if isinstance(args.get(alan), str)
            ),
            "",
        )
        satir = f"- {name}({hedef})" if hedef else f"- {name}"
        if satir not in gorulen:
            gorulen.append(satir)
    if not gorulen:
        return ""
    return _ALREADY_DONE.format(items="\n".join(gorulen[:MAX_DONE_ITEMS]))


def _correction_task(task: str, feedback: str, budget: TurnBudget) -> str:
    return _CORRECTION_TASK.format(
        task=task, feedback=feedback, done=_already_done_block(budget)
    )


async def _self_review(task: str, outcome: AgentOutcome, deps: AgentDeps) -> AgentOutcome:
    deps.publisher.publish(SelfReviewStarted())
    feedback = await review.review_turn(
        task, outcome.final_text, outcome.messages, config=deps.config, publisher=deps.publisher
    )
    deps.publisher.publish(SelfReviewFinished(issue_found=bool(feedback)))
    if not feedback:
        return outcome

    correction = await run_agent(
        _correction_task(task, feedback, deps.require_budget()),
        deps,
        history=outcome.messages,
        self_review=False,
        internal=True,
        # Kapı bu turda çalışmaz: dış döngü zaten doğrulayacak. Aksi halde iç içe
        # doğrulama olur ve MAX_VERIFY_ROUNDS sessizce ikiye katlanır.
        verify=False,
    )
    correction.tool_calls_made += outcome.tool_calls_made
    correction.mutating_tool_calls_made += outcome.mutating_tool_calls_made
    correction.failed_tool_calls += outcome.failed_tool_calls
    correction.model_calls_made += outcome.model_calls_made
    return correction


def _recall_skill(
    classification: TaskClassification,
    deps: AgentDeps,
    *,
    depth: int,
) -> str:
    """Confidence-gated uzmanlık context'ini yalnız ana tura ekle.

    Alt-ajan kendi dar göreviyle çalışır. Ana turda da yanlış/kararsız expertise
    enjeksiyonu yerine hiç enjeksiyon tercih edilir.
    """
    if depth > 0:
        return ""

    skills = (
        deps.capabilities.skills()
        if deps.capabilities is not None
        else ()
    )

    return skill_recall.auto_expertise_block(
        classification,
        skills,
    )

async def _verify(
    outcome: AgentOutcome, deps: AgentDeps, *, plan_mode: bool, depth: int
) -> VerificationResult | None:
    """Doğrulama kapısını çalıştır.

    Sonuç iki yere birden gider: modele düzeltme talimatı ve ders güvenine sinyal.
    İki kez çalıştırmak hem israf hem de iki farklı cevap alma riskidir.

    İş yapılmadıysa (araç çağrısı yok) kapı anlamsızdır; plan modunda ise hiçbir şey
    değişmediği için hiç çalışmaz.
    """
    if deps.verifier is None or plan_mode or depth > 0:
        return None
    if outcome.tool_calls_made == 0:
        return None
    return await deps.verifier.verify()


async def _fix_findings(
    task: str, verification: VerificationResult, outcome: AgentOutcome, deps: AgentDeps
) -> AgentOutcome:
    """Somut bulguları modele düzeltme talimatı olarak ver ve TEK düzeltici tur aç.

    Model çağrısı EKLEMEZ (talimat deterministik üretilir) ama düzeltici turun kendisi
    bir tur maliyetindedir. Öz-denetimdeki disiplinin aynısı: ikinci bir kapı turu yok,
    sonsuz düzeltme döngüsü yok.
    """
    deps.publisher.publish(
        VerificationFailed(summary=verification.summary, findings=verification.findings)
    )
    # Bulgu yoksa özet tek başına talimat olur: elde bundan fazlası yok, ama
    # "doğrulama düştü" bilgisi bile modele hiçbir şey söylememekten iyidir.
    ayrintilar = verification.findings or ((verification.summary,) if verification.summary else ())
    bulgular = "\n".join(f"- {finding}" for finding in ayrintilar)
    correction = await run_agent(
        # Görev tekrar edilir: düzeltici tur bir ARA adımdır, hedefi kendi başına
        # taşımalıdır (bkz. `_CORRECTION_TASK`).
        f"Kullanıcının görevi şuydu:\n{task}\n\n"
        "Bu göreve devam ediyorsun. Doğrulama kapısı üretilen çıktıda şu somut "
        "sorunları buldu. Hepsini düzelt; düzeltemeyeceğin varsa nedenini tek "
        f"cümleyle yaz.\n\n{bulgular}",
        deps,
        history=outcome.messages,
        self_review=False,
        internal=True,
        # Kapı düzeltici turda TEKRAR çalışmaz: sonsuz düzeltme döngüsü yok.
        verify=False,
    )
    correction.tool_calls_made += outcome.tool_calls_made
    correction.mutating_tool_calls_made += outcome.mutating_tool_calls_made
    correction.failed_tool_calls += outcome.failed_tool_calls
    correction.model_calls_made += outcome.model_calls_made
    return correction


async def _maybe_compress(messages: list[Message], deps: AgentDeps) -> list[Message]:
    before = len(messages)
    threshold = (
        history.WEB_COMPRESS_THRESHOLD_CHARS
        if (deps.execution and deps.execution.is_web)
        or (deps.config.web_sessions and any(s.enabled for s in deps.config.web_sessions))
        else history.COMPRESS_THRESHOLD_CHARS
    )
    compressed = await compaction.compress(
        messages, config=deps.config, publisher=deps.publisher, threshold_chars=threshold
    )
    if len(compressed) < before:
        deps.publisher.publish(ContextCompressed(before=before, after=len(compressed)))
    return compressed


def _scoped_task(task: str, history: list[Message] | None) -> str:
    """Sınıflandırma ve bütçe için görevin TAMAMINI temsil eden metin.

    Geçmişteki İLK kullanıcı mesajı asıl hedefi taşır; bu turun metni ("devam et")
    yalnızca onun devamıdır. İkisi birleştirilir — prompta değil, YALNIZCA tür ve
    bütçe kararına girer.
    """
    ilk = next((mesaj.content for mesaj in history or () if mesaj.role == "user"), "")
    return f"{ilk}\n{task}".strip() if ilk else task


def _initial_messages(
    task: str,
    history: list[Message] | None,
    *,
    plan_mode: bool,
    extra_system: str,
    inherit_system: bool = False,
) -> list[Message]:
    """Turun mesaj listesini kur: TEK sistem mesajı + geçmiş + yeni görev.

    Sistem mesajı BAŞA EKLENMEZ, geçmişinkinin YERİNE geçer. Ölçüldü: geçmiş
    her zaman bir önceki turun `outcome.messages` listesidir ve o liste zaten bir
    sistem mesajıyla başlar; başa bir tane daha eklemek listeyi
    `[system, system, user, …]` yapıyordu.

    Bunun görünmeyen bedeli tarayıcı sohbetiydi. `_deliver_turn` sohbeti ancak
    gönderilmiş önek DEĞİŞMEMİŞSE sürdürür; fazladan sistem mesajı öneki
    kaydırdığı için önek hiçbir zaman tutmuyordu. Sonuç: hem öz-denetim düzeltici
    turu hem de TUI'deki HER takip mesajı yeni bir tarayıcı sohbeti açıyor ve
    geçmişin tamamını tek düz metin olarak yeniden gönderiyordu — `ConversationState`
    docstring'inin "model aynı araç çağrılarını yeniden üretir" diye ölçtüğü durumun
    ta kendisi. Canlı izde tam olarak bu görüldü: düzeltici tur dizini baştan
    listeledi, 1388 satırlık dosyayı yeniden okudu ve görevi kaybetti.

    Sistem metni GERÇEKTEN değiştiyse (plan kipi açıldı) önek zaten kasıtlı olarak
    tutmaz ve sohbetin sıfırlanması doğrudur: model artık başka talimatlarla
    çalışıyordur.

    `inherit_system` İÇ turlar içindir (öz-denetim düzeltmesi, doğrulama kapısı
    düzeltmesi) ve sistem metnini geçmişten olduğu gibi alır. Ölçüldü: çiftlenme
    giderildikten sonra bile sohbet düşmeye devam etti, çünkü `run_agent` dersleri
    ve uzmanlık talimatını HER çağrıda o turun metnine göre hatırlıyor; düzeltici
    turun metni asıl görevden farklı olduğu için hatırlanan blok da farklı çıkıyor
    ve önek yine kayıyordu. Düzeltici tur aynı konuşmanın devamıdır — model zaten
    o talimatlarla çalışıyor, talimatı ortasından değiştirmek için bir sebep yok.
    """
    gecmis = list(history or [])
    devralinabilir = inherit_system and bool(gecmis) and gecmis[0].role == "system"
    if devralinabilir:
        system = gecmis[0].content
    else:
        system = SYSTEM_PROMPT
        if plan_mode:
            system += f"\n\n{PLAN_MODE_PROMPT}"
        if extra_system:
            system += f"\n\n{extra_system}"
    # Yalnızca BAŞTAKİ sistem mesajı düşürülür. Tur içinde araya giren sistem
    # notları (değişiklik kaydı, kapı uyarısı) konuşmanın parçasıdır ve kalır;
    # onları atmak öneki yine kaydırırdı.
    if gecmis and gecmis[0].role == "system":
        gecmis = gecmis[1:]
    return [Message("system", system), *gecmis, Message("user", task)]

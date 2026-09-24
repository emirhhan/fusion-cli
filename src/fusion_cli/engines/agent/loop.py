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
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

from ...config.eligibility import effort_for_spec
from ...config.model_select import escalated_spec, select_agent_spec
from ...config.models import Config
from ...core.budget import BudgetStop, TurnBudget
from ...core.checkpoint import CheckpointStore
from ...core.clock import SystemClock
from ...core.concurrency import BackgroundTasks
from ...core.constants import (
    CAPABILITY_WALL_PREFIX,
    FILE_MISSING_PREFIX,
    UNREACHABLE_RESOURCE_PREFIX,
)
from ...core.errors import ConfigError, FusionError
from ...core.events import (
    Channel,
    ContextCompressed,
    EventPublisher,
    ExecutionRouteSelected,
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
from ...core.evidence import ToolUse
from ...core.health import HealthRegistry
from ...core.memory import CodeIndex, Lesson, LessonMemory
from ...core.progress import RoundSignals, progressed
from ...core.steering import SteeringQueue
from ...core.tools import Tool, ToolContext, ToolFamily, ToolResult, tool_family
from ...core.types import (
    CompletionRequest,
    Message,
    ModelResult,
    ModelSpec,
    StreamDone,
    TextChunk,
    ToolCall,
    is_permanent_error,
)
from ...core.verification import VerificationResult, Verifier
from ...core.web_response import classify_response
from ...providers.capabilities import TaskRequirements, infer_task_requirements
from ...providers.factory import build_provider
from ...providers.web_registry import web_registry_for
from ...tools import ToolRegistry, build_registry
from ...tools.capabilities import CapabilityRegistry
from ...tools.emulation import coerce_arguments, render_tool_example, validate_arguments
from ...tools.files import resolve_path
from ...tools.preview import file_diff
from ..effects.runner import maybe_run_effect_workflow
from . import compaction, denial, history, learning_steps, reflexion, review
from .approval import ApprovalPolicy, Decision, build_request
from .chat_mode import WORKSPACE_READ_REASON, chat_execution, chat_tool_names, observe_execution
from .engine_tools import UserAsker, build_agent_registry
from .execution_policy import (
    ExecutionPolicy,
    policy_for,
    refresh_mutation_policy,
    uses_web_context,
)
from .execution_route import ExecutionRoute, choose_execution_route
from .plan_runner import run_execution_plan
from .playbook_stage import maybe_run_playbook
from .project_instructions import read_all_instructions
from .repo_context import repo_map_block
from .turn_report import build_turn_report
from .workspace_hint import find_workspace_for

_PROMPTS = Path(__file__).parent / "prompts"
SYSTEM_PROMPT = (_PROMPTS / "system.md").read_text(encoding="utf-8")
#: Sohbet kipinin kimliği. Aynı motor ve aynı tek model kullanılır; fark, Fusion'ın
#: kendiliğinden çalışma dizinini taramamasıdır. Kod kipi `SYSTEM_PROMPT` ile kalır.
CHAT_SYSTEM_PROMPT = (_PROMPTS / "system_chat.md").read_text(encoding="utf-8")
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

_DECISION_OUTCOMES = {
    Decision.DENIED: ToolOutcome.DENIED,
    Decision.BLOCKED: ToolOutcome.BLOCKED,
}


def _decision_message(decision: Decision, *, plan_mode: bool) -> str:
    """Reddedilen/engellenen çağrı için modele dönecek metni seç.

    `Decision.BLOCKED` İKİ ayrı sebepten gelebilir ve ikisinin metni FARKLI
    olmalıdır: plan modunda hiç sorulmaz (`BLOCKED_MESSAGE`); auto/security
    modunda ise oturum etkileşimsiz olduğu için sorulAMAMIŞTIR
    (`denial.APPROVAL_UNAVAILABLE_MESSAGE`) — tur ikisinde de sürer ama sebep
    kullanıcıya değil ortama aittir. `Decision.DENIED` ise artık YALNIZCA gerçek
    bir insan reddini taşır; o turu durdurduğu için kısa bir iz mesajı yeter
    (bkz. `loop._drive`, `denial.DENIAL_STOP_ANSWER`).
    """
    if decision is Decision.DENIED:
        return denial.DENIED_TOOL_RESULT
    if plan_mode:
        return BLOCKED_MESSAGE
    return denial.APPROVAL_UNAVAILABLE_MESSAGE


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
    #: Bu turda kaç kez bağlam özetlendi (condensation).
    #
    # Sayı teşhis sinyalidir: sık özetleme, bağlamın taşmakta olduğunu söyler ve
    # devam eden turun neyin özetlendiğini bilmesi gerekir.
    condensations: int = 0
    #: Planlama çağrıları toplam model sayısına dahildir; final kapıları model değildir.
    planning_calls_made: int = 0
    final_verification_calls: int = 0
    #: Aynı çağrı bu turda ZATEN yapıldığı için engellenen çağrı sayısı.
    #:
    #: "Hiçbir şey yapmadım" ile "iş zaten yapılmıştı" farklı sonuçlardır ve
    #: sayaçlar bunları ayırt edemezse plan adımı geçilemez hâle gelir.
    already_done_calls: int = 0
    #: Turda DENENEN araç çağrıları, çalışma sırasıyla. Sayaçlar "kaç tane"
    #: sorusuna cevap verir; yükseltme kararı "hangileri, hangi sırada" bilgisini
    #: ister (bağımlılık zinciri ve araç ailesi bundan okunur).
    tool_uses: tuple[ToolUse, ...] = ()

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
    #: Geçmiş kaynaklarının aranacağı ev dizini. Yoksa `read_session` aracı hiç sunulmaz.
    home: Path | None = None
    #: Kullanıcının `.claude/settings.local.json` içinde onaysız izin verdiği komutlar.
    allowed_commands: frozenset[str] = frozenset()
    #: Verilirse ders çıkarımı turu BEKLETMEDEN arka planda çalışır (REPL için).
    #: Verilmezse tur içinde beklenir (tek seferlik CLI için doğru davranış).
    background: BackgroundTasks | None = None
    channel: Channel = Channel.MAIN
    #: Bu turda kaç kez bağlam özetlendi; plan yürütücüsü checkpoint'e taşır.
    condensations: int = 0
    #: Kullanıcının koşan işe ilettiği yönergeler; her alt turdan önce boşaltılır.
    steering: SteeringQueue | None = None
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
    #: Profesyonel workflow'un kesintiden sonra devam edebilmesi için kalıcı depo.
    checkpoint_store: CheckpointStore | None = None
    #: Aynı kökteki farklı sohbetlerin checkpoint'lerini birbirinden ayırır.
    conversation_id: str = ""
    #: İlk dış turda çıkarılan zorunlu model yetenekleri; iç turlar aynı kararı taşır.
    task_requirements: TaskRequirements | None = None
    #: Bu turda `recall_lessons` ile hatırlanan dersler. Tur sonunda güvenleri
    #: turun sonucuna göre güncellenir (`learning_steps.reinforce_recalled`).
    recalled_lessons: list[Lesson] = field(default_factory=list)

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
    chat_mode: bool = False,
    extra_system: str = "",
    depth: int = 0,
    self_review: bool | None = None,
    allowed_tools: set[str] | None = None,
    step_limit: int | None = None,
    verify: bool = True,
    internal: bool = False,
    require_local_mutation: bool = False,
    system_prompt: str | None = None,
    images: tuple[str, ...] = (),
    workflow: bool = False,
) -> AgentOutcome:
    """Bir görevi araçlarla çalıştır. Döndürülen geçmiş bir sonraki tura beslenir.

    `allowed_tools` verilirse modele YALNIZCA o araçlar sunulur (uzman agent'lar
    kendi araç setini bildirebilir). Boş küme tüm araçları kapatır; dolu kümede
    görev yönetimi ve soru sorma araçları ayrıca sunulur.

    `chat_mode` sohbet turudur: model okur ve cevaplar, çalışma alanını
    DEĞİŞTİRMEZ ve plan motoruna girmez (bkz. `chat_mode.py`).

    Varsayılan yol tek ReAct döngüsüdür; ne zaman araç kullanacağına ve çok
    adımlı işte `todo_write` ile plan tutacağına model karar verir. Plan motoru
    yalnız `workflow=True` (kullanıcı `/plan-yurut` seçti) ya da
    `workflow_mode: always` ile çalışır ve kök konuşmanın tamamını alır.
    """
    # Bütçe turun EN BAŞINDA bir kez kurulur ve buradan sonra her iç içe çağrı aynı
    # nesneyi görür. Öz-denetim ve doğrulama kapısı `run_agent`'ı yeniden çağırdığı
    # için, bütçe orada kurulsaydı her düzeltici tur sıfırdan başlardı — düzeltilen
    # hata tam olarak buydu.
    if deps.budget is None:
        deps.budget = _new_budget(deps.config)

    if not plan_mode and not chat_mode and depth == 0:
        played = await maybe_run_playbook(task, deps)
        if played is not None:
            return played

    registry = build_agent_registry(deps, depth=depth, run_agent=run_agent)
    if deps.task_requirements is None and depth == 0:
        deps.task_requirements = infer_task_requirements(
            task,
            has_images=bool(images),
            mutating=require_local_mutation,
        )

    # Gerçek dünya etkisi için deterministik handler varsa LLM ReAct döngüsünü
    # tamamen atla. Modelin "pushluyorum" demesi operasyon sonucu değildir; Git
    # workflow'u post-condition (local HEAD == remote HEAD) kanıtını kendisi üretir.
    effect_result = (
        None
        if chat_mode
        else await maybe_run_effect_workflow(task, deps, registry, plan_mode=plan_mode, depth=depth)
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

    # Dersler ve beceri metinleri tur başında sisteme BASILMAZ; model onları
    # `recall_lessons` / `find_skill` + `read_skill` ile ister. Ölçüldü: görev
    # türüne göre seçilen uzmanlık ve dersler yanlış türde yanlış bağlamı
    # taşıyordu (WEBSITE sanılan bir turda 21 KB'lık web referansı eklendi).
    proje_ve_dis_bellek = read_all_instructions(deps.tool_context.root, deps.home)
    # Depo haritası: model doğru dosyayı aramak için tur harcamasın. Kod kipinde
    # kök turda eklenir; sohbet kipi çalışma dizinini taramaz.
    harita = repo_map_block(deps.tool_context.root) if depth == 0 and not chat_mode else ""
    teacher_hint = (
        "Karmaşık çok dosyalı görevde kendi incelemenden sonra bir mimari risk veya "
        "doğrulama belirsizliği kalırsa `ask_teacher` ile tek somut soru sor. "
        "Sırları ve özel verileri öğretmene gönderme."
        if depth == 0 and not chat_mode and registry.get("ask_teacher") is not None
        else ""
    )
    messages = _initial_messages(
        task,
        history,
        plan_mode=plan_mode,
        extra_system="\n\n".join(
            part
            for part in (proje_ve_dis_bellek, harita, teacher_hint, extra_system)
            if part
        ),
        # İç düzeltici turlar sistem metnini geçmişten miras alır; yeniden
        # hesaplanan ders/uzmanlık bloğu öneki kaydırıp sohbeti sıfırlıyordu.
        inherit_system=internal,
        system_prompt=system_prompt,
        images=images,
    )

    if deps.execution is None:
        try:
            selected_spec = select_agent_spec(
                deps.config, deps.task_type, requirements=deps.task_requirements
            )
        except ConfigError as error:
            # Henüz hiçbir model çağrılmadı. Normal başarısız sonuç döndürerek
            # oturumun bitiş olayı ve ekleri içeren geçmişi kaydetmesini sağla.
            messages.append(Message("assistant", str(error)))
            return AgentOutcome(final_text=str(error), messages=messages, ok=False)
        # Politikaya BU TURUN metni verilir, geçmişle birleştirilmiş hali değil.
        #
        # `policy_for` `required_effect` çıkarır ve o, turu BAŞARISIZ ilan eden
        # tek kapıdır. Ölçüldü: oturumun ilk mesajı "oyun yap, index.html
        # oluştur" olduğunda, sonraki "merhaba" turu birleştirilmiş metinden
        # `workspace_mutation` etiketi alıyor ve kapı, kullanıcının o turda hiç
        # istemediği bir dosya değişikliğinin kanıtını arayıp turu düşürüyordu.
        # Bir kapı turu reddediyorsa dayandığı iddia O TURDA söylenmiş olmalı.
        deps.execution = policy_for(deps.config, selected_spec, task)
    execution = deps.execution
    if chat_mode:
        # Sohbet turu: değiştirme kapalı, kanıt kapıları kapalı, yalnız okuyan araçlar.
        execution = chat_execution(execution)
        allowed_tools = set(chat_tool_names(registry)) if allowed_tools is None else allowed_tools
    elif (
        not plan_mode
        and execution.allow_mutation
        and execution.required_effect == "workspace_read"
    ):
        # Kod kipinde de gözlem kilidi: turun METNİ yalnızca okuma/inceleme
        # istiyorsa model o turda yazamaz. Plan modu zaten kendi onay
        # politikasıyla (`PlanApproval`) her değişikliği engeller; model gerçek
        # bir yetenek kısıtına (`allow_mutation=False`) çarpmışsa o kısıt
        # önceliklidir, buradaki gözlem gerekçesiyle EZİLMEZ.
        execution = observe_execution(execution, WORKSPACE_READ_REASON)
    if allowed_tools is not None:
        names = frozenset(_permitted(allowed_tools, registry, execution) or ())
        execution = replace(execution, allowed_tool_names=names)
    # Web taşımasında bağlam pahalıdır: uzun okuma hem gecikme hem context rot
    # üretir. SWE-agent'ın ölçümü turda ~100 satırı en iyi pencere olarak veriyor;
    # API yolunda mevcut ölçülmüş davranış (800 satır) korunur.
    if execution.is_web and deps.tool_context.read_window is None:
        deps.tool_context = replace(deps.tool_context, read_window=WEB_READ_WINDOW)
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
        # Yalnız bu turun metni açık bir DEĞİŞİKLİK istiyorsa model çağrılmadan
        # durulur. Okuma ve web araması etkisi değişiklik değildir: model okuyup
        # cevaplayabilir; değiştirici araçlar zaten sunulmaz ve kullanıcı
        # `MutationUnavailable` ile nedenini görür. Ölçüldü (19 Eylül G7): "akışı
        # incele ve anlat" `workspace_read` aldığı için model hiç çağrılmıyordu.
        blocking = not execution.observe_only and execution.complex_task
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

    if not plan_mode and not chat_mode and depth == 0:
        route = choose_execution_route(deps.config.runtime.workflow_mode, requested=workflow)
        deps.publisher.publish(
            ExecutionRouteSelected(route=route.route.value, reasons=route.reasons)
        )
        if route.route is ExecutionRoute.WORKFLOW:
            # Plan motoru KÖK konuşmayı alır: sistem + önceki sohbet + bu turun
            # mesajı. Geçmişsiz plan her adımda kullanıcının önceki söylediklerini
            # kaybediyordu (gizli kelime vakası).
            return await run_execution_plan(
                task, deps, run_agent, conversation=messages, self_review=self_review
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
        require_local_mutation=require_local_mutation,
    )

    verification = None
    # Doğrulama turu hakkı da tur genelidir: iç içe bir düzeltme kendi kapı bütçesini
    # açamaz (`verify=False` ile zaten kapatılıyor, bütçe bunu ikinci kez garanti eder).
    while verify and budget.stop is None and budget.take_verify_round():
        verification = await _verify(outcome, deps, plan_mode=plan_mode, depth=depth)
        # Bulgu YOKLUĞU başarı değildir: `ok=False` tek başına düzeltmeyi hak eder.
        # Koşul eskiden `not verification.findings` de arıyordu; yalnızca özet
        # dolduran bir kapı (komut doğrulayıcısı) başarısız olduğunda agent
        # düzeltmeye hiç başlamıyordu.
        if verification is None or verification.ok:
            break
        # Somut bir verifier bulgusu correction için yeni ve eyleme geçirilebilir
        # bilgidir. Idle saatini tazele; mutlak tur deadline'ı değişmez. Aksi halde
        # uzun bir web turunun sonunda bulunan hata, düzeltici model daha araç
        # çağırmadan eski hareketsizlik süresine takılıyordu.
        budget.record_progress()
        outcome = await _fix_findings(verification, outcome, deps)

    # Deterministik kapılar olasılıksal model hakeminden önce çalışır. Somut bir
    # derleme/statik/tarayıcı bulgusu varken hakeme bütçe harcatmak, düzeltilebilir
    # hatanın bütçe kapanınca verifier'a hiç ulaşmamasına yol açıyordu.
    should_review = deps.config.runtime.self_review if self_review is None else self_review
    # Öz-denetim yalnız GERÇEK bir dosya mutasyonu olduğunda çalışır. Ölçüldü
    # (B2 gecikmesi): "Sadece 'merhaba' yaz" gibi araçsız bir tur, eski koşulda
    # (web taşımasında regex tabanlı `_web_self_review_needed`, API taşımasında
    # koşulsuz) yine de bir hakem çağrısı harcıyordu. Koşul artık YAPISAL: metne
    # bakmaz, yalnızca turda GERÇEKTEN mutasyon olup olmadığına bakar.
    if outcome.mutating_tool_calls_made == 0:
        should_review = False
    # Kullanıcı GERÇEKTEN reddettiyse (`USER_DENIED`) öz-denetim çalışmaz: `_drive`
    # bu turda modeli BİR DAHA ÇAĞIRMAYACAĞINI zaten garanti eder (bkz. döngü
    # başındaki kontrol); öz-denetim bir model çağrısı daha yaparak bunu ihlal
    # ederdi. Diğer bütçe durdurmaları (sözleşme onarılamadı, zaman aşımı…) bunun
    # dışındadır: gerçek bir mutasyon olmuşsa öz-denetim yine de çalışmalı — onu
    # kapatmak `test_mutasyondan_sonraki_arac_sozlesmesi_hatasi_oz_denetimi_atlamaz`
    # ile ölçülen davranışı (geç bir sözleşme hatası yazılmış artefaktı denetimsiz
    # bırakmamalı) bozardı.
    if budget.stop is BudgetStop.USER_DENIED:
        should_review = False
    # Yanlış dizinde düzeltilecek bir şey YOKTUR. Ölçüldü: öz-denetim düzeltici
    # turu tam bu durumda görevi terk edip kendine yeni iş uydurdu (o projenin
    # README'sini okuyup "test paketini çalıştır" diye plan yazdı). Doğru cevap
    # "bu dizinde o dosyalar yok" demektir; onu ikinci bir tur iyileştiremez.
    if outcome.wrong_workspace:
        should_review = False
    if should_review and not plan_mode and depth == 0 and outcome.final_text.strip():
        outcome = await _self_review(task, outcome, deps)

    # Sohbet/gözlem turunda rapor yoktur: çalışma alanı zaten değiştirilemez,
    # dolayısıyla doğrulanacak bir şey de yoktur (bkz. modül docstring "Gözlem
    # turunda yazma tamamen kapalı olmalı").
    #
    # Rapor yalnız KÖK turda uygulanır — `_announce_answer`'daki
    # `internal or depth != 0` erken çıkışıyla AYNI gerekçe. Öz-denetim
    # (`_self_review`) ve doğrulama düzeltmesi (`_fix_findings`) `run_agent`'ı
    # `internal=True` ile YENİDEN çağırır ve o iç çağrı da buraya, kendi
    # sonunda, ayrıca gelir. Koşul olmadan aynı "✓ Doğrulandı" bloğu ÖNCE iç
    # düzeltici turda (kendi `final_text`'inin başına), SONRA kök turda
    # (düzeltmenin döndürdüğü `outcome` üzerinde bir daha) eklenir ve kullanıcı
    # aynı metni art arda iki kez görür (ölçüldü). `plan_runner.py` da adım
    # çağrılarını `internal=True` ile yapıp KENDİ konsolide raporunu
    # (`_turn_report_text`) tüm adımların `tool_uses`'ından ayrıca kurduğu için
    # buradaki iç turların atlanması onu bozmaz, aksine aynı çiftlenmeyi orada
    # da önler.
    if not chat_mode and not internal and depth == 0:
        _apply_turn_report(outcome, deps, gate=verification)

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
        allow_read_only=execution.learn_read_only_turns,
    )
    # Hatırlanan derslerin kaydı turun TAMAMINA aittir; iç içe düzeltici turlar
    # onu erkenden tüketip kendi (ara) sonucuyla pekiştirmemeli.
    if depth == 0 and not internal:
        await learning_steps.reinforce_recalled(
            outcome, deps, plan_mode=plan_mode, verification=verification
        )
    outcome.messages = await _maybe_compress(outcome.messages, deps)
    # Özetleme sayısı turun sonucuna taşınır: plan yürütücüsü onu checkpoint'e
    # yazar ve devam eden tur neyin özetlendiğini bilir.
    outcome.condensations = deps.condensations
    # Tarayıcı oturumunun sahibi EN DIŞTAKİ turdur. İç içe çağrılar (öz-denetim,
    # doğrulama düzeltmesi, alt-ajan) aynı bağlamı paylaşır; onların kapatması
    # sürmekte olan turun sayfasını elinden alırdı. Kapatılmayan oturum arkada
    # bir chromium süreci bırakır — RULES.md "oluşturulan her task'ın sahibi vardır".
    if depth == 0 and deps.tool_context.browser.is_open:
        await deps.tool_context.browser.close()
    return outcome


def _apply_turn_report(
    outcome: AgentOutcome, deps: AgentDeps, *, gate: VerificationResult | None
) -> None:
    """Turun raporunu MODELİN BEYANINDAN değil gerçek kayıttan kur ve ekle.

    Ölçüldü: model "hiçbir dosya değiştirmedim" ya da "tüm testler geçti"
    diyebiliyordu ve bu cümle onun kendi sözüydü — gerçek değişiklik kaydına
    (`deps.tool_context.changes`, A12) ya da gerçekten çalışan bir `run_shell`
    çağrısının çıkış koduna (A1) hiç bakılmıyordu. `build_turn_report` yalnız bu
    ikisine bakar; hiçbir mutasyon yoksa (D4) rapor boş kalır.

    Bilinen bir bozukluğu (`gate.ok is False`) ya da GERÇEKTEN başarısız biten
    bir doğrulama komutunu başarı diye teslim etmek hiç yazmamaktan kötüdür; bu
    yüzden `report.blocks_success` turu `ok=False` yapar. Eksik kanıt (hiçbir
    komut çalışmadı) bunun dışındadır — dürüst bir uyarıdır, hata değildir.
    """
    from ...tools.files import display_path

    changed_paths = tuple(
        display_path(deps.tool_context, path) for path in deps.tool_context.changes.paths
    )
    report = build_turn_report(changed_paths, outcome.tool_uses, gate)
    text = report.render()
    if not text:
        return
    outcome.final_text = report.render_with_model_text(outcome.final_text)
    if report.blocks_success:
        outcome.ok = False


def _announce_answer(outcome: AgentOutcome, deps: AgentDeps, *, depth: int, internal: bool) -> None:
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
    #: Yinelenen olduğu için engellenen çağrı sayısı (bkz. AgentOutcome).
    already_done_calls: int = 0
    #: Denenen her araç çağrısı, SIRAYLA. Engellenen ve düşen çağrılar da girer:
    #: yükseltme kararı "ne denendi" bilgisini "ne başardı" kadar önemser.
    tool_uses: list[ToolUse] = field(default_factory=list)
    tool_rounds: int = 0
    tool_calls_last_turn: int = 0
    evidence_reprompts: int = 0
    #: "Hiç araç çağırmadan bitirme" kapısının kaç kez konuştuğu. Bir kezle sınırlı.
    never_acted_prompts: int = 0
    #: Uzun okuma dizisinden sonra verilen tek ilerleme uyarısı.
    exploration_pushes: int = 0
    #: Bu tur bir İÇ düzeltici tur mu (öz-denetim, doğrulama kapısı)? İç turlar
    #: araçsız bitebilir ve bu meşrudur: asıl işi dış tur zaten yapmıştır, iç tur
    #: yalnızca düzeltir ya da açıklar.
    internal: bool = False
    #: Blocking verification correction araçsız kapanamaz.
    require_local_mutation: bool = False
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
    #: Arka arkaya başarısız olan DEĞİŞTİRİCİ çağrı sayısı. Düzenleme döngüsü kapısı.
    failed_mutations_in_row: int = 0
    #: Döngü kapısı bu turda kaç kez konuştu.
    edit_loop_pushes: int = 0
    #: Modele en son kaç değişiklik kaydı bildirildi.
    logged_changes: int = 0
    #: (araç adı, hata imzası) → kaç kez. Aracın kendi önerisi işe yaramadığında
    #: modele Fusion'ın notunu vermek için tutulur.
    repeated_failures: dict[tuple[str, str], int] = field(default_factory=dict)
    #: "Dosya yok" ile düşen okumaların İSTENEN yolları (öneri araması için).
    missing_paths: list[str] = field(default_factory=list)
    #: Başarıyla okunan dosya sayısı. Yanlış-dizin hipotezi buna bakar.
    successful_file_reads: int = 0
    #: Yanlış dizin uyarısı verildi mi?
    warned_wrong_workspace: bool = False
    #: Kullanıcının GERÇEKTEN reddettiği son aracın adı. `_drive` turu bu isimle
    #: durdurur (bkz. `denial.DENIAL_STOP_ANSWER`); yalnızca `budget.stop is
    #: BudgetStop.USER_DENIED` iken anlamlıdır.
    denied_tool_name: str | None = None


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
    require_local_mutation: bool = False,
) -> AgentOutcome:
    state = _State(
        internal=internal,
        require_local_mutation=require_local_mutation,
    )
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
        if budget.stop is BudgetStop.USER_DENIED:
            # Kullanıcı ÖNCEKİ araç turunda GERÇEKTEN "hayır" dedi (`_run_tools`).
            # Bu bir bütçe olayı DEĞİLDİR: `_halt`/`_halt_local`'ın aksine
            # `TurnBudgetExhausted` YAYINLANMAZ ve tur `ok=True` ile biter — model
            # bir hata yapmadı, kullanıcı bir karar verdi. Model bir DAHA
            # ÇAĞRILMAZ: aksi hâlde reddedilen işi başka bir yoldan yine
            # denenebilir ve kullanıcının kararı yok sayılmış olurdu.
            return _outcome(
                denial.DENIAL_STOP_ANSWER.format(tool=state.denied_tool_name or "araç"),
                messages,
                state,
            )
        # Kullanıcının araya girdiği yönerge, sıradaki model çağrısından ÖNCE girer:
        # tur bittikten sonra iletmek onu bir sonraki göreve, hiç iletmemek ise
        # kullanıcıyı turu öldürmeye zorlardı.
        apply_steering(messages, deps.steering)
        if budget.model_calls_exhausted:
            return _halt(final_text, messages, state, budget, BudgetStop.MODEL_CALLS, deps)
        if local_limit is not None and local_calls >= local_limit:
            return _halt_local(final_text, messages, state, budget, BudgetStop.MODEL_CALLS, deps)
        local_calls += 1
        time_stop = budget.time_stop_reason()
        if time_stop is not None:
            return _halt(final_text, messages, state, budget, time_stop, deps)
        remaining = budget.next_timeout_s()
        call_timeout = min(deps.config.runtime.request_timeout_s, remaining) if remaining else (
            deps.config.runtime.request_timeout_s
        )

        try:
            # Transport idle timeouts do not bound a stream that keeps trickling
            # tokens forever. Bound the complete model call as well.
            async with asyncio.timeout(max(0.01, call_timeout)):
                result = await _call_model(
                    messages,
                    deps,
                    registry,
                    allowed_tools,
                    state=state,
                    execution=execution,
                    offer_tools=execution.offer_tools,
                    timeout_s=call_timeout,
                )
        except TimeoutError:
            reason = budget.time_stop_reason()
            if reason is not None:
                return _halt(final_text, messages, state, budget, reason, deps)
            return _outcome(
                f"Model yanıtı {call_timeout:g} saniyede tamamlanmadı. "
                "Bu çağrı durduruldu; farklı bir model seçip yeniden deneyebilirsin.",
                messages,
                state,
                ok=False,
            )

        state.model_calls_made += 1
        budget.record_model_call()
        # Yedek zinciri BAŞKA bir modele düşmüş olabilir; yetenek kapısı turun
        # başında yapılandırılmış modele göre kapanmıştı. Kapı yalnız açılır.
        execution = refresh_mutation_policy(execution, result.served_by, deps.config)
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
            return _halt_local(final_text, messages, state, budget, BudgetStop.TOOL_ROUNDS, deps)

        before = _progress_marker(deps, state)
        errored = await _run_tools(
            result.tool_calls,
            messages,
            deps,
            registry,
            state,
            execution=execution,
            plan_mode=plan_mode,
        )
        budget.record_round(progressed=progressed(_round_signals(deps, state, before)))
        if state.tool_contract_abort:
            budget.halt(BudgetStop.REPEATED_CALL)
            _publish_budget_stop(deps, budget, state)
            return _outcome(state.tool_contract_abort, messages, state, ok=False)
        exploration_note = _exploration_note(
            state,
            execution,
            plan_mode=plan_mode,
            teacher_available=registry.get("ask_teacher") is not None,
        )
        if exploration_note is not None:
            state.exploration_pushes += 1
            messages.append(Message("user", exploration_note, harness_note=True))

        # Blocking verification correction gerçek bir mutation üretmeden
        # NO_PROGRESS'a düşmemeli. Model önce read_file yapabilir veya yanlış/
        # başarısız bir araç deneyebilir; bu durumda sınırlı bir mutation reprompt'u
        # daha verilir. Hak bittiğinde normal idle kapısı tekrar otoritedir.
        if _never_acted(state, execution):
            state.never_acted_prompts += 1
            note = _spend(deps, reflexion.verification_action_required_note())
            if note is not None:
                messages.append(note)
                continue

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
            oneri = find_workspace_for(tuple(state.missing_paths), deps.tool_context.root)
            messages.append(
                reflexion.wrong_workspace_note(
                    str(deps.tool_context.root), str(oneri) if oneri else ""
                )
            )
        _record_changes(messages, deps, state)


def apply_steering(messages: list[Message], queue: SteeringQueue | None) -> int:
    """Kullanıcının araya girdiği yönergeleri sıradaki çağrıdan ÖNCE mesajlara ekle.

    Yönerge harness notudur: modelin kendi cevabına karışmaz, kullanıcının sözü
    olarak taşınır. Kuyruk tek seferlik boşaltılır — bir kez söyleneni her turda
    tekrar etmek, onu sonsuz bir talimata çevirirdi. Kuyruk yoksa akış değişmez.
    """
    if queue is None or not queue.pending:
        return 0
    notlar = queue.drain()
    messages.extend(notlar)
    return len(notlar)


def _round_signals(
    deps: AgentDeps, state: _State, before: tuple[int, int, int, int]
) -> RoundSignals:
    """Turun sinyallerini önceki ölçümle farkını alarak topla.

    İkili "bir şey değişti mi" kararı, başarısız üç çağrıyla hiç çağrı yapmamayı
    aynı kefeye koyuyordu ve eşiği ayarlamak imkânsızdı. Sinyaller ayrıştırılınca
    budama kararı ölçülebilir ve ayarlanabilir olur.
    """
    simdi = _progress_marker(deps, state)
    return RoundSignals(
        mutations=max(0, simdi[1] - before[1]),
        new_reads=max(0, (simdi[0] - before[0]) - (simdi[1] - before[1])),
        failures=max(0, simdi[2] - before[2]),
        repeats=max(0, simdi[3] - before[3]),
    )


def _progress_marker(deps: AgentDeps, state: _State) -> tuple[int, int, int, int]:
    """Turun ilerleyip ilerlemediğini ölçen iki sayı.

    Başarılı araç sayısı VE dokunulan dosya sayısı birlikte bakılır: bir tur yalnızca
    okuma yapmış olabilir (dosya sayısı artmaz ama iş yapılmıştır) ya da yalnızca
    yazma (ikisi de artar). İkisi de sabit kaldıysa o turda hiçbir şey olmamıştır.
    """
    return (
        state.tool_calls_made,
        len(deps.tool_context.touched),
        state.failed_tool_calls,
        state.already_done_calls,
    )


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


def _halt_local(
    final_text: str,
    messages: list[Message],
    state: _State,
    budget: TurnBudget,
    reason: BudgetStop,
    deps: AgentDeps,
) -> AgentOutcome:
    """Yalnız bu ``_drive`` çağrısının sınırında dur; dış kapıları açık bırak.

    Web yürütme politikasındaki model/araç sınırları çağrı-yereldir. Doğrulama ve
    öz-denetim alt turları aynı ``TurnBudget`` nesnesini paylaşsa da bu yerel sınıra
    çarpılması, çalışma alanının son post-condition doğrulamasını engellememelidir.
    Gerçek tur-geneli sayaç ve süre sınırları `_halt` üzerinden otorite olmaya devam
    eder.
    """
    deps.publisher.publish(
        TurnBudgetExhausted(
            reason=reason.value,
            model_calls=budget.model_calls,
            tool_rounds=state.tool_rounds,
            idle_rounds=budget.idle_rounds,
            elapsed_s=budget.elapsed_s,
        )
    )
    text = final_text.strip()
    outcome = _outcome(text, messages, state, hit_step_limit=True, ok=False)
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


def _note_tool_use(
    state: _State,
    name: str,
    tool: Tool | None,
    *,
    ok: bool,
    arguments: dict[str, object] | None = None,
    output: str = "",
) -> None:
    """Denenen araç çağrısını sırayla kaydet (adım ve tur kanıtı)."""
    state.tool_uses.append(
        ToolUse(
            name=name,
            ok=ok,
            mutating=bool(tool is not None and tool.mutating),
            arguments=arguments or {},
            output=output,
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
        tool_uses=tuple(state.tool_uses),
        already_done_calls=state.already_done_calls,
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
            tool_family(name) is ToolFamily.SHELL and _shell_contains_git_action(args, "push")
            for name, args, _ in evidence
        )
    if effect == "git_commit":
        return any(
            tool_family(name) is ToolFamily.SHELL and _shell_contains_git_action(args, "commit")
            for name, args, _ in evidence
        )
    if effect == "shell_action":
        return any(tool_family(name) is ToolFamily.SHELL for name, _, _ in evidence)
    if effect == "workspace_mutation":
        return any(mutating for _, _, mutating in evidence)
    if effect == "web_lookup":
        return any(
            name in {"web_search", "web_fetch", "read_url_content"} for name, _, _ in evidence
        )
    if effect.startswith("file:"):
        # Dosya teslim eden adımın kanıtı DEĞİŞTİREN bir araçtır.
        #
        # Eskiden `file:` etkisi son satıra düşüyordu ve "herhangi bir başarılı
        # araç" kanıt sayılıyordu. Ölçüldü (13 Eylül, Godot koşusu): adım
        # `file:ASSETS.json` bekliyordu, model tek bir `web_search` yaptı, sonra
        # "assetleri bulup indireceğim" diyen bir metinle turu bitirdi ve kanıt
        # kapısı bunu YETERLİ saydı. Hiçbir dosya yazılmadı, hiçbir yeniden istem
        # yapılmadı; adım doğrulamada düştü ve kurtarma hakkı boşa gitti.
        return any(mutating for _, _, mutating in evidence)
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
    # Takılan adım bir üst modele yükselir: aynı modelle aynı duvara çarpmak yerine
    # zincirde yukarı kayılır. `strict` rolde kullanıcının seçimi korunur.
    spec = escalated_spec(
        select_agent_spec(deps.config, deps.task_type, requirements=deps.task_requirements),
        execution.escalation,
    )
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
ALWAYS_ALLOWED = frozenset(
    {"todo_write", "ask_user", "find_skill", "read_skill", "recall_lessons"}
)

#: Web taşımasında bir okumada gösterilecek en fazla satır (SWE-agent ölçümü).
WEB_READ_WINDOW = 100


def _permitted(
    allowed_tools: set[str] | None,
    registry: ToolRegistry,
    execution: ExecutionPolicy,
) -> set[str] | None:
    """Modele sunulacak ve çalıştırılabilecek araç adlarını belirle.

    Mutation izni yoksa değiştirici araçların ŞEMASI hiç gönderilmez: modele
    yapamayacağı bir yeteneği göstermek, denemesine ve turu boşa harcamasına yol açar.
    Düzenleme sözleşmesi tüm sağlayıcılarda aynıdır (`edit_file` / `multi_edit` /
    `write_file`); sağlayıcıya göre şema daraltılmaz.
    """
    if allowed_tools is not None and not allowed_tools:
        return set()
    names = (
        set(registry.names())
        if allowed_tools is None
        else ((allowed_tools | ALWAYS_ALLOWED) & set(registry.names()))
    )
    if execution.allowed_tool_names is not None:
        names &= execution.allowed_tool_names
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
    # Taşıma bütünlüğü her teşhisin önündedir: kesilmiş yanıt, kapanmamış blok ve
    # boş yanıt farklı hamleler ister. Üçünü "işi yarım bıraktın" notuna bağlamak
    # ya yapılan işi çöpe atıyor ya da modele yanlış şeyi düzelttiriyordu.
    butunluk = classify_response(final_text, truncated=truncated, has_tool_calls=False)
    tasima_notu = reflexion.integrity_note(butunluk)
    if tasima_notu is not None:
        return _spend(deps, tasima_notu)
    # Bloklayan doğrulama düzeltmesi araçsız kapanamaz; bu tek dal korunur (bkz.
    # `_never_acted`). Kapsamı büyüten genel dürtme kapıları (hiç çağrı yapmadan
    # soru sorma, keşifte takılma, "yarım kalmış gibi görünme") kaldırıldı: model
    # ne zaman araç kullanacağına, ne zaman bitireceğine kendi karar verir.
    if _never_acted(state, execution):
        state.never_acted_prompts += 1
        return _spend(deps, reflexion.verification_action_required_note())
    wanted = deps.tool_context.todos.has_pending
    return _spend(deps, reflexion.auto_continue_note()) if wanted else None


def _spend(deps: AgentDeps, note: Message) -> Message | None:
    """Devam hakkını harca ve notu döndür; hak kalmadıysa `None`.

    Hak yalnızca GERÇEKTEN devam edilecekse harcanır; sırayı tersine çevirmek
    devam etmeyen turlarda da bütçe yakardı.
    """
    bekleyen = deps.tool_context.todos.pending_count
    return note if deps.require_budget().take_auto_continue(pending_todos=bekleyen) else None


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

#: Tamamı okunmuş bir dosyanın toptan yeniden yazılmasının serbest olduğu üst sınır.
#
# Kuralın gerekçesi hacimdir: "yüz satırlık bir dosyayı baştan üretmek modele yüz
# satırlık hata yüzeyi açar". Küçük dosyada o yüzey yoktur ve kural yalnızca
# maliyet üretir.
#
# Ölçüldü (6 Eylül, 24 görev × 3 koşu): engellenen 34 toptan yazmanın TAMAMI
# 1-45 satırlık dosyalardaydı; 34'ünün 28'i 12 satır ve altındaydı. Model her
# seferinde `replace_range`'e düşmek zorunda kaldı ve tek satırlık JSON'u satır
# aralığıyla onarmaya çalışırken tur harcadı. Yıkıcı başarısızlıkların ölçüldüğü
# rejim ise ~100 satırdı.
#
# Sınır, gözlenen meşru vakaların (45) üstüne, ölçülen yıkıcı rejimin (~100)
# belirgin altına konur.
MAX_LINES_FOR_FULL_REWRITE = 60
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


def _never_acted(state: _State, execution: ExecutionPolicy) -> bool:
    """Bloklayan doğrulama düzeltmesi HİÇ araç çağırmadan turu kapatıyor mu?

    Yalnızca `require_local_mutation` (blocking verification correction) dalı
    kalır: bu alt tur gerçek bir mutation ÜRETMEK ZORUNDADIR, dış turun eski
    kanıtıyla kapanamaz. Genel "karmaşık görevde hiç araç çağırmadı" dürtüsü
    kaldırıldı (B4/A13): model ne zaman araç kullanacağına kendi karar verir ve
    araçsız bitirdiği bir tur, aksini gerektiren bir kapıya (kanıt kapısı,
    doğrulama düzeltmesi) çarpmıyorsa geçerli bir teslimdir.

    BİR KEZ değil İKİ KEZ konuşur (blocking correction'a özeldir): model ikinci
    kez de araçsız gelirse zorlamak çağrı harcamaktır; o noktada cevabı olduğu
    gibi teslim etmek dürüst olandır.
    """
    if not state.require_local_mutation:
        return False
    # Blocking verification correction dış turun eski evidence'ı ile kapanamaz;
    # BU alt tur gerçek bir mutation üretmelidir.
    if state.mutating_tool_calls_made > 0:
        return False
    if not execution.offer_tools:
        return False
    return state.never_acted_prompts < 2


def _exploration_note(
    state: _State,
    execution: ExecutionPolicy,
    *,
    plan_mode: bool,
    teacher_available: bool,
) -> str | None:
    """İstenen değişiklikte uzun salt-okuma döngüsünü bir kez kır."""
    if (
        plan_mode
        or not execution.complex_task
        or not execution.allow_mutation
        or state.mutating_tool_calls_made
        or state.tool_calls_made < 10
        or state.exploration_pushes
    ):
        return None
    note = (
        "FUSION_NOT: Bu görevde en az 10 başarılı araç çağrısı yaptın ama henüz "
        "hiç dosya değiştirmedin. Daha fazla genel dizin taraması yapma. "
        "İncelediğin dosyalardan ilk somut değişikliği seç ve uygula."
    )
    if teacher_available:
        note += (
            " Mimari karar veya doğrulama konusunda bir belirsizlik kaldıysa "
            "`ask_teacher` ile tek somut soru sor, cevabı değerlendir, ardından uygula."
        )
    return note


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
    satir = _line_count(hedef)
    if satir <= MAX_LINES_FOR_FULL_REWRITE:
        # Küçük dosyada çıkış yolu VARDIR ve söylenmelidir: tamamını okuduktan
        # sonra toptan yazma serbest (bkz. `_rewrite_is_last_resort`).
        #
        # Ölçüldü (13 Eylül, koşu 27): mesaj yalnız kaldırılan `replace_range`
        # aracını öneriyordu. Model `scenes/main.tscn` için `write_file` denedi,
        # engellendi, `edit_file` ile boş 'old' gönderdi, tekrar `write_file`
        # denedi ve tekrar kapısına takıldı; adım bütçesi doldu, sahne hiç
        # yazılamadı. Sahne dosyası satır satır yamanacak bir metin değildir,
        # yeniden üretilir.
        return [
            f"'{raw}' zaten var ({satir} satır) ve İÇERİĞİNİ BU ADIMDA OKUMADIN. "
            "Önce `read_file` ile TAMAMINI oku; tamamını gördükten sonra `write_file` "
            "ile yeniden yazmana izin verilir. Yalnız küçük bir parça değişecekse "
            "`edit_file` ile o parçayı gönder."
        ]
    return [
        f"'{raw}' zaten var ve {satir} satır. Var olan dosyayı toptan yeniden yazma — "
        "önce read_file ile ilgili satırları gör, sonra edit_file ile YALNIZCA değişecek "
        "parçayı gönder."
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
    if hedef not in deps.tool_context.fully_read:
        return False
    if _line_count(hedef) <= MAX_LINES_FOR_FULL_REWRITE:
        return True
    return state.failed_mutations_in_row >= MAX_EDITS_BEFORE_REWRITE


def _line_count(path: Path) -> int:
    """Dosyanın satır sayısı; okunamıyorsa kuralı gevşetmeyecek şekilde sonsuz."""
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return sys.maxsize
    except UnicodeDecodeError:
        # İkili dosya: toptan yazmanın hacim gerekçesi burada ölçülemez, kısıt kalsın.
        return sys.maxsize


#: Dosyanın tamamını değiştiren araçlar.
_FULL_WRITE_TOOLS = frozenset({"write_file"})

def _is_rerunnable(name: str) -> bool:
    """Onay açısından değiştirici sayılan ama TEKRAR EDİLMESİ meşru olan araç mı.

    Tekrar imzasında değiştirici araçların çağı sıfırlanır ("aynı yazma iki kez
    istenmez"). `run_shell` bu kuralın altında yanlış kalıyordu: doğrulama komutu
    tam olarak tekrarlanmak İÇİN vardır. Ölçüldü — model kodu düzeltti, `npm test`
    çalıştırmak istedi ve TOOL_CALL_DUPLICATE ile engellendi; düzeltmenin işe
    yarayıp yaramadığını doğrulayamadı.

    Çağa bağlanmak doğru davranışı verir: değişiklik olmadan aynı komutu tekrar
    etmek yine tekrardır, değişiklikten SONRA tekrar etmek yeni bilgidir.

    Sınıflandırma TEK KAYNAKTAN (`core.tools.tool_family`) okunur, burada ikinci
    bir ad listesi açılmaz. Ölçüldü (masaüstü uygulaması, API modeli): model
    doğrulama komutunu `run_shell` yerine takma adı `bash` ile çağırdı; birebir
    ad karşılaştırması `"bash" != "run_shell"` olduğu için bu istisnayı hiç
    görmedi ve tam da çözmek için var olduğu ölü kilit takma ad altında geri
    geldi (bkz. `engines/agent/turn_report.py::_is_shell_call`, aynı yaklaşım).
    """
    return tool_family(name) is ToolFamily.SHELL


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
    plan_mode: bool = False,
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
        if budget.stop is BudgetStop.USER_DENIED:
            # Bu TUR'daki önceki bir çağrı AZ ÖNCE reddedildi (aşağıda). Aynı model
            # yanıtındaki kalan çağrılar hiç çalıştırılmaz — kullanıcının kararı bir
            # sonraki çağrıda yok sayılmamalı. Sağlayıcı sözleşmesi yine de her
            # `tool_call`'a bir sonuç ister; bu yüzden "atlandı" mesajı gönderilir.
            output = denial.SKIPPED_TOOL_RESULT
            deps.publisher.publish(
                ToolExecuted(
                    name=call.name,
                    args={},
                    outcome=ToolOutcome.DENIED,
                    output=output,
                    diff=None,
                )
            )
            messages.append(
                Message("tool", output, tool_call_id=call.id, name=call.name, ok=False)
            )
            state.failed_tool_calls += 1
            errored = True
            continue

        args, parse_error = _parse_arguments_checked(call.arguments)
        tool = registry.get(call.name)
        function_schema = tool.schema().get("function") if tool is not None else None
        # Fazla kodlanmış yapısal argüman ONARILIR: bir dizi alanının JSON METNİ
        # olarak gelmesi niyet hatası değil kodlama hatasıdır ve turu düşürmemeli.
        #
        # Onarım imzadan ÖNCE yapılır: aynı mantıksal çağrının kodlanmış ve çözülmüş
        # hâlleri iki ayrı imza üretseydi tekrar kapısı bu çağrıyı hiç göremezdi.
        if isinstance(function_schema, dict):
            args = coerce_arguments(function_schema, args)
        # İmza TUR BOYUNCA paylaşılır: düzeltici turun ana turdaki çağrıyı birebir
        # tekrar etmesi, her tura ayrı ayrı bakıldığında görünmeyen bir döngüdür.
        signature = budget.signature(
            call.name,
            _encode_arguments(args),
            mutating=tool is not None and tool.mutating and not _is_rerunnable(call.name),
        )
        seen = budget.count_call(signature)

        contract_errors: list[str] = []
        if parse_error:
            contract_errors.append(parse_error)
        if tool is None:
            contract_errors.append(
                "bilinmeyen araç; kullanılabilir araçlar: " + ", ".join(registry.names())
            )
        elif isinstance(function_schema, dict):
            contract_errors.extend(validate_arguments(function_schema, args))

        if not contract_errors:
            contract_errors.extend(_targeted_edit_required(call.name, args, deps, execution, state))

        if contract_errors:
            # Aynı bozuk çağrı ikinci kez geldiyse onarım hakkı harcanmaz: model
            # düzeltmiyor, tekrarlıyor.
            no_more_repairs = seen >= 1 or not budget.take_contract_repair()
            output = _tool_contract_failure(
                call.name,
                contract_errors,
                tool.schema().get("function") if tool is not None else None,
                registry=registry,
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
            _note_tool_use(state, call.name, tool, ok=False, arguments=args, output=output)
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
            # Engellenen yineleme, işin ZATEN YAPILDIĞININ kanıtıdır: düşen
            # çağrılar bu noktaya gelmeden unutulur (`forget_call`).
            state.already_done_calls += 1
            # OKUMA tekrarına HATA değil, ilk sonucun kendisi döner.
            #
            # Ölçülen ölü kilit (Godot koşusu): model `list_dir .` çağrısını
            # yineledi, kapı onu `blocked` yaptı, engellenen çağrı ilerleme
            # saymadığı için boşta tur sayacı doldu ve görev "agent adım bütçesi
            # doldu" ile öldü. Oysa model yalnızca zaten sahip olduğu bilgiyi
            # yeniden istiyordu; ona hata vermek zinciri kırıyor, bilgiyi vermek
            # sürdürüyor ve YENİ İŞ YAPTIRMIYOR. Değiştirici araçlar bu yoldan
            # yararlanamaz: aynı yazma iki kez yapılmaz, orası hâlâ engellidir.
            onbellek = budget.recall_read(signature)
            if onbellek is not None:
                output = f"{_REPEATED_READ_NOTE}\n\n{onbellek}"
                deps.publisher.publish(
                    ToolExecuted(
                        name=call.name,
                        args=args,
                        outcome=ToolOutcome.OK,
                        output=output,
                        diff=None,
                    )
                )
                messages.append(
                    Message("tool", output, tool_call_id=call.id, name=call.name, ok=True)
                )
                _note_tool_use(state, call.name, tool, ok=True, arguments=args, output=output)
                # Kanıt sayaçları ARTMAZ: yeni bir iş yapılmadı, yalnızca bilinen
                # bir sonuç tekrar sunuldu. İlerleme kapısı bunu ilerleme saymaz
                # ve model kendini toparlayamazsa tur yine biter.
                continue
            output = _duplicate_call_message()
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
            _note_tool_use(state, call.name, tool, ok=False, arguments=args, output=output)
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
        result, outcome = await _execute(
            call, args, deps, registry, execution=execution, plan_mode=plan_mode
        )
        _note_tool_use(
            state,
            call.name,
            tool,
            ok=outcome is ToolOutcome.OK,
            arguments=args,
            output=result.output,
        )
        if outcome in (ToolOutcome.DENIED, ToolOutcome.BLOCKED):
            # Onay verilmeyen ya da yetenek kapısına takılan çağrı HİÇ ÇALIŞMADI.
            # Tekrar kapısına kanıt olarak yazılırsa, koşullar düzelse bile aynı
            # çağrı "bunu zaten yaptın ve o zamandan beri bir şey değişmedi"
            # diyen bir engelle karşılaşır.
            #
            # Ölçüldü (Godot koşusu): doğrulama adımındaki
            # `godot --headless --path . --quit` etkileşimsiz oturumda onay
            # alınamayıp `blocked` döndü; ikinci deneme `TOOL_CALL_DUPLICATE` ile
            # engellendi ve adım hiçbir zaman kanıt üretemedi.
            budget.forget_call(signature)
        if outcome is ToolOutcome.DENIED:
            # Bu bir hata ya da bütçe olayı DEĞİLDİR — insan GERÇEKTEN "hayır"
            # dedi. Tur burada durur (`_drive` bir sonraki döngü başında bunu
            # görüp modeli bir daha çağırmadan döner); aynı yanıttaki KALAN
            # çağrılar döngünün başındaki kontrolle atlanır.
            state.denied_tool_name = call.name
            budget.halt(BudgetStop.USER_DENIED)
        # Duvar ve ulaşılamaz kaynak, kanıt kapısı açısından AYNI durumdur: iş bu
        # araçla yapılamadı. Modeli kanıt üretmeye zorlamak onu uydurmaya iter.
        if result.output.startswith((CAPABILITY_WALL_PREFIX, UNREACHABLE_RESOURCE_PREFIX)):
            state.capability_wall = True
        if outcome is ToolOutcome.OK:
            state.tool_calls_made += 1
            # Okuma sonucu turda saklanır: aynı okuma yinelenirse engel yerine
            # bu sonuç döner (bkz. tekrar kapısı).
            if tool is not None and not tool.mutating:
                budget.remember_read(signature, result.output)
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
                # bırakıyordu (bkz. `_is_rerunnable`).
                if not _is_rerunnable(call.name):
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
                # Düşen çağrı YAPILMAMIŞTIR. Hemen unutulmaz — arada hiçbir şey
                # değişmeden yinelemek gerçek tekrardır — ama başarılı bir
                # değişiklikten sonra unutulur: engeli kalkmış olabilir.
                budget.note_failed_call(signature)

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
        govde = result.output
        if outcome is ToolOutcome.FAILED:
            imza = (call.name, _failure_signature(result.output))
            state.repeated_failures[imza] = state.repeated_failures.get(imza, 0) + 1
            not_ = _repeated_failure_note(
                call.name,
                result.output,
                state.repeated_failures[imza],
                teacher_available=(
                    deps.config.teacher is not None and not deps.config.runtime.teacherless
                ),
            )
            if not_ is not None:
                govde = f"{govde}\n\n{not_}"
        messages.append(
            Message(
                "tool",
                govde,
                tool_call_id=call.id,
                name=call.name,
                ok=result.ok,
                images=result.images,
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
    plan_mode: bool = False,
) -> tuple[ToolResult, ToolOutcome]:
    """Onaydan geçir ve çalıştır. Bilinmeyen araç da kayıt defterinin sorunu."""
    tool = registry.get(call.name)
    if execution.allowed_tool_names is not None and call.name not in execution.allowed_tool_names:
        # Serbest araçlar SÖYLENMELİ: gözlem turunda model yalnız "kapsamda değil"
        # cevabını görünce aynı yazma aracını başka argümanla yeniden deniyordu.
        allowed = ", ".join(sorted(execution.allowed_tool_names)) or "yok"
        return ToolResult.failure(
            f"Araç bu adımın izin verilen kapsamında değil. Bu adımda kullanılabilir: {allowed}"
        ), ToolOutcome.BLOCKED
    if tool is not None and tool.mutating and not execution.allow_mutation:
        # Yetenek kapısı onaydan ÖNCE gelir: kullanıcıya sormanın anlamı yok, bu
        # model bu işi güvenilir yapamıyor. Şema hiç sunulmadığı için buraya normalde
        # gelinmez; ikinci savunma hattıdır.
        return (
            ToolResult.failure(
                MUTATION_BLOCKED_MESSAGE.format(reason=execution.mutation_block_reason)
            ),
            ToolOutcome.BLOCKED,
        )
    if tool is not None and tool.mutating:
        decision = await deps.policy.decide(build_request(tool, args, deps.allowed_commands))
        if decision is not Decision.ALLOW:
            # Engelleme (BLOCKED) HATA DEĞİLDİR: refleksiyon tetiklenmemeli, model
            # yalnızca farklı bir yol denemeli. Reddetme (DENIED) ise artık farklı
            # bir sınıftır: turu durdurur (bkz. `_run_tools`, `_drive`).
            message = _decision_message(decision, plan_mode=plan_mode)
            return ToolResult.failure(message), _DECISION_OUTCOMES[decision]

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


#: Aynı hatanın kaç kez yinelenmesinden SONRA Fusion araya girer.
#:
#: 1 olsaydı ilk denemede araya girip modelin normal toparlanmasını bozardık;
#: daha yükseği turu döngüde tutar. Ölçülen vakada hata üç kez yinelendi.
_YINELENEN_HATA_ESIGI = 2

#: Öğretmene danışma ÖNERİSİNİN eşiği (Faz 4, Görev 1).
#:
#: Yeni bir sayı UYDURULMADI: temel "farklı argümanlarla dene" notu zaten
#: `_YINELENEN_HATA_ESIGI`'de veriliyor. Öğretmen önerisi o notun bile işe
#: yaramadığı, yani AYNI hatanın bir kez daha yinelendiği durumdur — bu yüzden
#: mevcut eşiğin üzerine bir tur eklenir, sıfırdan bir eşik seçilmez
#: (bkz. `docs/superpowers/plans/2026-09-22-ogretmen-protokolu.md` §6.2).
_OGRETMEN_ONERI_ESIGI = _YINELENEN_HATA_ESIGI + 1


def _failure_signature(output: str) -> str:
    """Hata metnini karşılaştırılabilir bir imzaya indir.

    İlk satır alınır: araçlar çözüm önerilerini sonraki satırlara yazar ve o
    öneriler aynı hatada bile değişebilir. Yol/ad gibi ayrıntılar İMZANIN
    PARÇASIDIR — farklı dosyada aynı hata farklı iştir, yinelenme sayılmaz.
    """
    return output.strip().splitlines()[0].strip() if output.strip() else ""


def _repeated_failure_note(
    tool_name: str, output: str, count: int, *, teacher_available: bool = False
) -> str | None:
    """Aynı araç aynı hatayı yineliyorsa modele Fusion'ın notu; yoksa `None`.

    Ölçülen hata: `godot__add_node` üç kez "Scene file does not exist" verdi ve
    her seferinde kendi önerisi olarak "Use create_scene first" dedi. Sahne
    zaten vardı; öneri yanlıştı. Model itaatle o öneriyi uygulayıp döngüye
    girdi — inatçı değildi, aracın SÖYLEDİĞİNİ yapıyordu.

    Tekrar kapısı burada yardım etmez: çağrılar birbirinin aynısı değildir
    (araçlar dönüşümlü çağrılıyor). Bu yüzden ölçüt çağrı imzası değil HATA
    imzasıdır.

    `teacher_available` yalnızca `config.teacher` tanımlıysa `True` gelir
    (bkz. çağıran yer); tanımsızken öneri BASILMAZ — model elinde olmayan bir
    aracı çağırmaya yönlendirilmez.
    """
    if count < _YINELENEN_HATA_ESIGI:
        return None
    not_ = (
        f"FUSION_NOT: `{tool_name}` aynı hatayı {count} kez verdi ve aracın kendi "
        "önerisi işe yaramadı. Aynı yolu tekrar deneme; FARKLI ARGÜMANLARLA çağır. "
        "Sık karşılaşılan sebep yol biçimidir: 'res://' ekini kaldırmayı ya da "
        "eklemeyi, göreli yol yerine tam yol vermeyi dene. Bu da olmazsa başka bir "
        "araçla aynı sonuca ulaşmayı dene."
    )
    if teacher_available and count >= _OGRETMEN_ONERI_ESIGI:
        not_ += (
            " Bu hata FARKLI yaklaşımlara rağmen sürüyorsa `ask_teacher` ile web "
            "öğretmene danışmayı düşün — turu bu döngüde harcamak yerine."
        )
    return not_


#: Tekrarlanan OKUMA çağrısında sonucun önüne konan not.
#
# Sonucu sessizce geri vermek, modelin aracı yeniden çalıştırdığını sanmasına ve
# değişmeyen bir dosyayı "taze" bilgi sayıp aynı döngüye girmesine yol açardı.
# Not, sonucun ÖNBELLEKTEN geldiğini ve çalışma alanının değişmediğini söyler.
_REPEATED_READ_NOTE = (
    "TOOL_CALL_CACHED: Bu okumayı aynı argümanlarla zaten yapmıştın ve çalışma "
    "alanında o zamandan beri ilgili bir değişiklik olmadı. Araç yeniden "
    "çalıştırılmadı; önceki sonuç aşağıda. Aynı okumayı bir daha isteme — "
    "elindeki bilgiyle sonraki adıma geç."
)


def _duplicate_call_message() -> str:
    """Tekrarlanan çağrıda modele verilen rehberlik.

    Ölçülen hata: mesaj yalnız DOSYA araçlarını sayıyordu. MCP ya da başka bir
    dış araçla çalışan model bu listeden hiçbirini uygulayamıyor ve engellenen
    aracı tümden yasaklanmış sanıyordu. Gerçek bir Godot turunda `add_node`
    yolu `res://` ekiyle reddedildi; doğru düzeltme AYNI aracı ek olmadan
    çağırmaktı, ama mesaj argüman değiştirmeyi hiç önermiyordu.

    Bu yüzden ilk öneri araç-bağımsızdır: ARGÜMANI değiştir. Dosya araçları
    yalnızca örnek olarak kalır.
    """
    return (
        "TOOL_CALL_DUPLICATE: Bu çağrıyı aynı argümanlarla ZATEN yaptın ve çalışma "
        "alanında o zamandan beri ilgili bir değişiklik olmadı. Fusion çağrıyı "
        "çalıştırmadı — sonucu zaten elinde. Araç YASAK DEĞİL; yasak olan aynı "
        "çağrıyı aynı argümanlarla tekrarlamak.\n"
        "Şunlardan BİRİNİ yap:\n"
        "1) Aynı aracı FARKLI ARGÜMANLARLA çağır. Önceki hata bir yol/biçim "
        "sorunuysa yolu değiştir (ör. 'res://' ekini kaldır ya da ekle, göreli "
        "yol yerine tam yol ver).\n"
        "2) Aynı işi yapan BAŞKA bir aracı dene.\n"
        "3) Dosya işi ise: yeni dosyada write_file, mevcut dosyada edit_file, "
        "başka bir dosyayı read_file ile oku.\n"
        "4) Eksik bilgi varsa ask_user ile sor.\n"
        "5) İş bittiyse sonucu söyle."
    )


def _is_tool_contract_error(detail: str | None) -> bool:
    return bool(detail and detail.startswith("TOOL_CALL_"))


def _tool_contract_failure(
    name: str,
    errors: list[str],
    function_schema: object,
    *,
    registry: ToolRegistry | None = None,
) -> str:
    """Sözleşme hatasını, ÖRNEĞİ hatanın işaret ettiği araçtan vererek bildir.

    Ölçüldü (13 Eylül, Godot koşusu): `write_file` mevcut dosyada reddedildi ve
    hata "replace_range kullan" dedi — ama örnek yine `write_file` çağrısıydı.
    Model örneği izleyip aynı çağrıyı tekrarladı, adım bütçesi doldu ve oyun
    yarım kaldı. Hata bir aracı önerirken başka bir aracın örneğini göstermek,
    öneriyi geri almaktır.
    """
    lines = ["TOOL_CALL_INVALID", f"tool: {name}", "errors:"]
    lines.extend(f"- {error}" for error in errors)
    onerilen = _suggested_tool_schema(name, errors, registry)
    if onerilen is not None:
        lines.append("valid_example:")
        lines.append(render_tool_example(onerilen))
    elif isinstance(function_schema, dict):
        lines.append("valid_example:")
        lines.append(render_tool_example(function_schema))
    return "\n".join(lines)


def _suggested_tool_schema(
    name: str, errors: list[str], registry: ToolRegistry | None
) -> dict[str, object] | None:
    """Hata metninde ADIYLA önerilen BAŞKA aracın şeması; yoksa None.

    Metinde birden çok araç anılıyorsa EN SONA yazılan seçilir: öneriler sıra
    halinde yazılıyor ("önce read_file ile gör, sonra edit_file ile gönder")
    ve modelin yanlış yaptığı adım zincirin sonundaki YAZMA adımıdır.
    """
    if registry is None:
        return None
    metin = " ".join(errors)
    sirali = sorted(
        ((metin.rfind(aday), aday) for aday in registry.names() if aday != name),
        reverse=True,
    )
    for konum, aday in sirali:
        if konum < 0:
            break
        tool = registry.get(aday)
        if tool is None:
            continue
        schema = tool.schema().get("function")
        if isinstance(schema, dict):
            return schema
    return None


def _tool_contract_abort_message(detail: str) -> str:
    return (
        "TOOL_CALL_ABORTED: Araç sözleşmesi düzeltilemedi veya aynı çağrı tekrarlandı. "
        "Fusion güvenlik için bu turu sonlandırdı; işlem tamamlanmış kabul edilmemelidir.\n"
        + detail
    )


# --------------------------------------------------------------------------- #
# Öz-denetim ve sıkıştırma
# --------------------------------------------------------------------------- #


#: Öz-denetim / doğrulama kapısı düzeltmesi turlarına eklenen notların ortak
#: öneki. Bu bir kullanıcı mesajı DEĞİLDİR; modelin bunu görevin yeniden
#: verildiği sanmaması için Fusion'ın kendi sesiyle işaretlenir.
CORRECTION_NOTE_PREFIX = "[Fusion doğrulama]"


def _correction_task(feedback: str) -> str:
    """Öz-denetim düzeltmesi için KISA not üret.

    Ölçüldü: eski talimat kullanıcının görevini BAŞTAN anlatıyordu
    ("Kullanıcının görevi şuydu: …") ve model bunu SAHTE bir yeni kullanıcı
    mesajı sanıp "iş henüz verilmedi, ne yapmamı istiyorsunuz" diyerek turu
    bitiriyordu — birinci turda yapılmış işi de götürerek. Tek konuşma geçmişi
    ilkesi burada da geçerlidir: görev zaten paylaşılan geçmişte duruyor,
    tekrar anlatmaya gerek yok; yalnız hangi sorunun düzeltileceği söylenir.
    """
    return (
        f"{CORRECTION_NOTE_PREFIX} Bir öz-denetim şu sorunu işaret etti. Gerekiyorsa "
        "düzelt; haklı değilsen kısaca neden sorun olmadığını açıkla.\n\n"
        f"{feedback}"
    )


async def _self_review(task: str, outcome: AgentOutcome, deps: AgentDeps) -> AgentOutcome:
    deps.publisher.publish(SelfReviewStarted())
    feedback = await review.review_turn(
        task, outcome.final_text, outcome.messages, config=deps.config, publisher=deps.publisher
    )
    deps.publisher.publish(
        SelfReviewFinished(issue_found=bool(feedback), completed=feedback is not None)
    )
    if not feedback:
        return outcome

    correction = await run_agent(
        _correction_task(feedback),
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


async def _verify(
    outcome: AgentOutcome, deps: AgentDeps, *, plan_mode: bool, depth: int
) -> VerificationResult | None:
    """Doğrulama kapısını çalıştır.

    Sonuç iki yere birden gider: modele düzeltme talimatı ve ders güvenine sinyal.
    İki kez çalıştırmak hem israf hem de iki farklı cevap alma riskidir.

    İş yapılmadıysa kapı anlamsızdır; plan modunda ise hiçbir şey değişmediği için
    hiç çalışmaz.

    Ölçü DEĞİŞTİRİCİ çağrıdır, çağrı sayısı değil. Ölçüldü (17 Eylül denetimi):
    yalnız kod açıklaması istenen bir tur `read_file` çağırdığı için kapı devreye
    girdi ve cevabın sonuna "doğrulanamadı: ruff check .", "mypy src" uyarıları
    eklendi — kullanıcının kodunda hiçbir şey değişmemişken. Kapının sorusu
    "bozdum mu"dur; hiçbir şeyi değiştirmeyen turda sorulacak bir soru yoktur.
    """
    if deps.verifier is None or plan_mode or depth > 0:
        return None
    if outcome.mutating_tool_calls_made == 0:
        return None
    return await deps.verifier.verify()


async def _fix_findings(
    verification: VerificationResult, outcome: AgentOutcome, deps: AgentDeps
) -> AgentOutcome:
    """Somut bulguları modele düzeltme talimatı olarak ver ve TEK düzeltici tur aç.

    Model çağrısı EKLEMEZ (talimat deterministik üretilir) ama düzeltici turun kendisi
    bir tur maliyetindedir. Öz-denetimdeki disiplinin aynısı: ikinci bir kapı turu yok,
    sonsuz düzeltme döngüsü yok.
    """
    deps.publisher.publish(
        VerificationFailed(summary=verification.summary, findings=verification.findings)
    )
    correction_task = _verification_correction_task(verification)
    correction_deps = _verification_correction_deps(deps)
    correction = await _run_verification_correction_attempt(
        correction_task,
        correction_deps,
        history=outcome.messages,
    )
    if (
        correction_deps is not deps
        and not correction.ok
        and deps.budget is not None
        and deps.budget.stop is None
        and not is_permanent_error(correction.final_text)
    ):
        retry = await _run_verification_correction_attempt(
            correction_task,
            deps,
            history=outcome.messages,
        )
        retry.tool_calls_made += correction.tool_calls_made
        retry.mutating_tool_calls_made += correction.mutating_tool_calls_made
        retry.failed_tool_calls += correction.failed_tool_calls
        retry.model_calls_made += correction.model_calls_made
        correction = retry

    correction.tool_calls_made += outcome.tool_calls_made
    correction.mutating_tool_calls_made += outcome.mutating_tool_calls_made
    correction.failed_tool_calls += outcome.failed_tool_calls
    correction.model_calls_made += outcome.model_calls_made
    return correction


def _verification_correction_task(verification: VerificationResult) -> str:
    # Bulgu yoksa özet tek başına talimat olur: elde bundan fazlası yok, ama
    # "doğrulama düştü" bilgisi bile modele hiçbir şey söylememekten iyidir.
    details = verification.findings or ((verification.summary,) if verification.summary else ())
    findings = "\n".join(f"- {finding}" for finding in details)
    # Görev TEKRAR EDİLMEZ: paylaşılan geçmiş zaten taşıyor. Talimat sahte bir
    # kullanıcı mesajı gibi davranıp modelin "görev yeniden mi verildi" sanmasına
    # yol açmasın diye Fusion'ın kendi sesiyle (`CORRECTION_NOTE_PREFIX`) işaretlenir.
    return (
        f"{CORRECTION_NOTE_PREFIX} Doğrulama kapısı üretilen çıktıda şu somut "
        "sorunları buldu. Bunları gerçek kod değişiklikleriyle düzelt. "
        "Doğrulama/test komutunu şimdi TEKRAR ÇALIŞTIRMA; kapı sen değişiklik "
        "yaptıktan sonra otomatik olarak yeniden çalışacak. Gerekirse ilgili dosyayı "
        "oku, fakat ardından en az bir gerçek değiştirici araç çağır "
        "(edit_file/write_file vb.). Salt açıklama, plan, JSON veya kod bloğu "
        "düzeltme değildir. Düzeltemeyeceğin varsa nedenini tek cümleyle yaz. "
        f"\n\n{findings}"
    )


async def _run_verification_correction_attempt(
    task: str,
    deps: AgentDeps,
    *,
    history: list[Message],
) -> AgentOutcome:
    return await run_agent(
        task,
        deps,
        history=history,
        self_review=False,
        internal=True,
        require_local_mutation=True,
        # Kapı düzeltici turda TEKRAR çalışmaz: sonsuz düzeltme döngüsü yok.
        verify=False,
    )


def _verification_correction_deps(deps: AgentDeps) -> AgentDeps:
    """Semantik olarak başarısız modeli varsa ilk fallback ile değiştir.

    Provider zinciri transport/kota hatasında fallback'e geçer; doğrulama bulgusu
    ise başarılı HTTP cevabının içindeki semantik başarısızlıktır ve zinciri doğal
    olarak ilerletmez. Aynı modele aynı artefaktı yeniden yazdırmak ölçülen koşulda
    aynı kusuru tekrarladı. Burada yalnız correction alt turu farklılaştırılır;
    bütçe, çalışma alanı, onay ve kalan fallback sırası paylaşılmaya devam eder.
    """
    selected = select_agent_spec(deps.config, deps.task_type, requirements=deps.task_requirements)
    if not selected.fallback:
        return deps

    correction_spec = ModelSpec(
        name=f"{selected.name}-verification-corrector",
        model=selected.fallback[0],
        tags=selected.tags,
        fallback=selected.fallback[1:],
    )
    correction_config = replace(
        deps.config,
        agent=correction_spec,
        task_model_map={},
    )
    return replace(deps, config=correction_config)


async def _maybe_compress(messages: list[Message], deps: AgentDeps) -> list[Message]:
    before = len(messages)
    selected = select_agent_spec(
        deps.config, deps.task_type, requirements=deps.task_requirements
    )
    threshold = (
        history.WEB_COMPRESS_THRESHOLD_CHARS
        if uses_web_context(deps.config, selected)
        else history.COMPRESS_THRESHOLD_CHARS
    )
    compressed = await compaction.compress(
        messages, config=deps.config, publisher=deps.publisher, threshold_chars=threshold
    )
    if len(compressed) < before:
        deps.publisher.publish(ContextCompressed(before=before, after=len(compressed)))
        deps.condensations += 1
    return compressed


def _initial_messages(
    task: str,
    history: list[Message] | None,
    *,
    plan_mode: bool,
    extra_system: str,
    inherit_system: bool = False,
    system_prompt: str | None = None,
    images: tuple[str, ...] = (),
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
        system = SYSTEM_PROMPT if system_prompt is None else system_prompt
        if plan_mode:
            system += f"\n\n{PLAN_MODE_PROMPT}"
        if extra_system:
            system += f"\n\n{extra_system}"
    # Yalnızca BAŞTAKİ sistem mesajı düşürülür. Tur içinde araya giren sistem
    # notları (değişiklik kaydı, kapı uyarısı) konuşmanın parçasıdır ve kalır;
    # onları atmak öneki yine kaydırırdı.
    if gecmis and gecmis[0].role == "system":
        gecmis = gecmis[1:]
    return [Message("system", system), *gecmis, Message("user", task, images=images)]

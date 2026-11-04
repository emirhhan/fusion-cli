"""Agent turunun ders/bellek adımları: hatırla, çıkar, sakla.

Bu adımlar döngünün kendisinden ayrıdır. Dersler tur başında kendiliğinden
enjekte EDİLMEZ: model ihtiyaç duyduğunda `recall_lessons` aracıyla ister
(`engine_tools.py`). Ölçüldü: görev türüne göre seçilen dersler yanlış türde
yanlış bağlamı sisteme basıyordu. Turdan SONRA yeni ders çıkarılır; `loop.py`
yalnızca bunları çağırır, ayrıntı burada durur.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from dataclasses import replace

# Döngüsel import'tan kaçınmak için tip yalnızca kontrol anında içe alınır.
from typing import TYPE_CHECKING

from ...core.events import LessonsLearned, LessonsRecalled
from ...core.lesson_runtime import HINT_LIMIT, LessonDelivery
from ...core.mcp_tool_names import mcp_server_of
from ...core.memory import Lesson, LessonKind, agent_lesson_tag
from ...core.types import Message
from ...core.verification import VerificationResult
from . import learning, lesson_attribution

logger = logging.getLogger(__name__)

#: `recall_lessons` aracının bir çağrıda döndürdüğü en fazla ders.
#:
#: Ölçüldü: bellekte 320 ders, Godot görevinde 38'i alakalıyken tur başına yalnız
#: 2'si enjekte ediliyordu — öğrenilen bilginin neredeyse tamamı israf oluyordu.
#: Dersi artık model açıkça istiyor; birkaç ders daha dikkat bütçesini bozmaz.
RECALL_LIMIT = 6


if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome


def _workspace(deps: AgentDeps) -> str:
    """Turun çalıştığı proje kökü — derslerin etiketlendiği ve süzüldüğü kimlik.

    Çözülmüş mutlak yol kullanılır: aynı projeye farklı göreli yollardan girmek
    (`.` ve `../fusion-cli`) iki ayrı workspace gibi görünmemeli.
    """
    return str(deps.tool_context.root.resolve()) if deps.tool_context is not None else ""


def lesson_tags(deps: AgentDeps) -> tuple[str, ...]:
    """Dersin ait olduğu TEKNOLOJİLER: proje türü + bağlı MCP sunucuları.

    `workspace` dersi tek bir klasöre bağlar; bu doğru ama yetersizdi. Ölçüldü:
    20 koşuda 38 Godot dersi öğrenildi, yeni bir Godot klasöründe hiçbiri
    hatırlanmadı. "Godot MCP'de `res://` kullanma" dersi klasöre değil
    teknolojiye aittir ve o teknolojinin kullanıldığı her projede geçerlidir.

    MCP sunucusu ayrı bir etikettir: bir MCP aracının kuralı, projenin türünden
    bağımsız olarak o sunucu bağlıyken geçerlidir.
    """
    from .verify_discovery import project_kinds

    context = deps.tool_context
    sunucular = {mcp_server_of(ad) for ad in context.available_tools} - {""}
    # Kendi belleği olan alt ajanın dersi kişilik etiketi taşır (P-055): çıkarımda yazılır,
    # geri çağırmada süzgeç olur (`core.memory.visible_to`).
    owner = getattr(deps, "lesson_owner", "")
    sahip = {agent_lesson_tag(owner)} if owner else set()
    return tuple(sorted({*project_kinds(context.root), *(f"mcp:{s}" for s in sunucular), *sahip}))


def recall_lessons(query: str, deps: AgentDeps, *, limit: int = RECALL_LIMIT) -> tuple[Lesson, ...]:
    """Sorguya benzer, bu projeye ve teknolojilere uyan az sayıdaki dersi hatırla.

    Hatırlanan dersler turun kaydına (`deps.recalled_lessons`) eklenir; tur
    sonunda güvenleri turun sonucuna göre güncellenir (`reinforce_recalled`).
    """
    if deps.lessons is None or not deps.config.runtime.lessons:
        return ()
    recalled = deps.lessons.recall(
        query,
        limit=limit,
        workspace=_workspace(deps),
        tags=lesson_tags(deps),
        policy=lesson_attribution.recall_policy(deps),
    )
    if recalled:
        deps.recalled_lessons.extend(recalled)
        deps.publisher.publish(
            LessonsRecalled(
                count=len(recalled), lesson_ids=tuple(lesson.id for lesson in recalled if lesson.id)
            )
        )
    return recalled


async def reinforce_recalled(
    outcome: AgentOutcome,
    deps: AgentDeps,
    *,
    plan_mode: bool,
    verification: VerificationResult | None = None,
) -> None:
    """Geri çağırma güven üretmez; yalnız ilişkili ve doğrulanmış kullanım pekişir.

    Aynı kök turun operasyon/kriter bağları lesson_state içinde tutulur.
    Salt başarılı kapanış, okunan web içeriği veya prose kullanım beyanı yeterli değildir.
    """
    if deps.lessons is None or not deps.config.runtime.lessons:
        return
    if plan_mode:
        return
    # Retrieval is exposure, not operational use. The same proof contract applies
    # with attribution telemetry disabled; outcome.ok alone cannot reward memory.
    lesson_attribution.settle(outcome, deps)


def should_learn(outcome: AgentOutcome, *, plan_mode: bool, allow_read_only: bool = True) -> bool:
    """Bu turdan ders çıkarılmalı mı. Saftır ve doğrudan test edilir.

    Üç kapı:

    1. **Gerçek iş yapılmış olmalı.** Araç çağrısı olmayan sohbet turundan ders
       çıkarmak hem boşuna model çağrısıdır hem de belleği değersiz kayıtla doldurur.
    2. **Tur temiz bitmiş olmalı.** Bütçeyle kesilen, sözleşme hatasıyla düşürülen ya
       da "ilerleme yok" kapısına takılan bir turun izi öğretici DEĞİLDİR: içeriğinin
       çoğu harness'ın kendi engelleme metnidir. Ölçülen gerçek zarar — iskele yazıp
       kilitlenen ve üç boşta turdan sonra öldürülen bir turdan iki ders çıkarıldı ve
       belleğe yazıldı; o dersler bir sonraki benzer görevde geri enjekte edildi.
       Bu öz-zehirlenmedir.

       Hatalardan öğrenme KAYBOLMAZ: modelin hata yapıp fark ettiği ve düzelttiği tur
       TEMİZ biter, `ok=True` döner ve öğrenilmeye devam eder. Elenen şey modelin
       hatası değil, harness'ın turu öldürmesidir.
    3. **Web AI'da düşük değerli salt-okuma turu elenir.** Ayrı bir model çağrısıyla
       ders çıkarmak pahalıdır; kod değişikliği ya da araç hatası varsa öğrenme korunur.
       API sağlayıcılarında (`allow_read_only`) eski davranış aynıdır.
    """
    if plan_mode or outcome.tool_calls_made == 0:
        return False
    if not outcome.ok or outcome.hit_step_limit:
        return False
    # Tur artık ilerlemesizlikte kesilmiyor (Claude Code'daki gibi); ama takılıp
    # uyarı alan turun izi harness notlarıyla dolu. Ondan ders çıkarmak eski
    # öz-zehirlenmeyi geri getirirdi (bkz. madde 2).
    if getattr(outcome, "stalled", False):
        return False
    return not (
        not allow_read_only
        and outcome.mutating_tool_calls_made == 0
        and outcome.failed_tool_calls == 0
    )


async def learn(
    task: str,
    outcome: AgentOutcome,
    deps: AgentDeps,
    *,
    plan_mode: bool,
    allow_read_only: bool = True,
    final_closeout: bool = False,
) -> None:
    """Turdan ders çıkar ve belleğe yaz. Kapı kararı `should_learn`'dedir."""
    if deps.lessons is None or not deps.config.runtime.lessons:
        return
    if deps.config.runtime.lesson_attributed_feedback and not final_closeout:
        return
    if not should_learn(outcome, plan_mode=plan_mode, allow_read_only=allow_read_only):
        return

    external = learning.reads_external_content(outcome.tool_uses)
    verification = deps.lesson_state.verification if deps.lesson_state else None
    work = _bounded(
        _extract_and_store(
            task, list(outcome.messages), deps, external=external, verification=verification
        )
    )
    if deps.background is None:
        await work
    else:
        deps.background.spawn(work)


#: Ders çıkarımına tanınan en fazla süre.
#
# Öğrenme bir İYİLEŞTİRMEDİR; turu düşürmesi ya da bekletmesi kabul edilemez.
# Ölçüldü: web modelinde çıkarım 20 dakikadan fazla asılı kaldı ve tek satır
# çıktı basılmadı. Sınır aşılırsa ders yazılmaz, tur normal biter.
LEARN_TIMEOUT_S = 120.0


async def _bounded(work: Awaitable[None]) -> None:
    """Öğrenmeyi süreyle sınırla; aşarsa sessizce vazgeç."""
    try:
        async with asyncio.timeout(LEARN_TIMEOUT_S):
            await work
    except TimeoutError:
        # DEBUG seviyesi bilinçli: bu bir teşhis notudur, kullanıcı eylemi
        # gerektirmez. `warning` olarak stderr'e basılınca nihai cevabın sonuna
        # yapışıyor ve kullanıcı onu cevabın parçası sanıyordu (ölçüldü).
        logger.debug("ders çıkarımı %.0f saniyede bitmedi, atlandı", LEARN_TIMEOUT_S)


async def _extract_and_store(
    task: str,
    messages: list[Message],
    deps: AgentDeps,
    *,
    external: bool = False,
    verification: VerificationResult | None = None,
) -> None:
    """Ders çıkarımının asıl işi. Arka planda çalışabilmesi için ayrı tutulur.

    `external`: tur dış içerik okudu; çıkan dersler düşük güvenle "dış kaynaklı"
    etiketlenir (`runtime.external_lesson_confidence`).
    """
    if deps.lessons is None:
        return
    lessons = await learning.extract_lessons(
        task,
        messages,
        config=deps.config,
        publisher=deps.publisher,
        workspace=_workspace(deps),
        tags=lesson_tags(deps),
    )
    lessons = tuple(
        replace(lesson, source_split=deps.lesson_context.policy.source_split) for lesson in lessons
    )
    from ...core.evidence import EvidenceStatus

    refs = (
        tuple(
            item.criterion_id
            for item in verification.evidence
            if item.status is EvidenceStatus.PASSED and item.applicable
        )
        if verification
        else ()
    )
    is_verified = bool(
        verification and verification.ok and not verification.failure_evidence and refs
    )
    lessons = tuple(
        replace(lesson, verified_at=str(deps.clock.now()), evidence_refs=refs)
        if lesson.kind is LessonKind.SUCCESS
        else lesson
        for lesson in lessons
        if lesson.kind is not LessonKind.SUCCESS or is_verified
    )
    if external:
        lessons = learning.mark_external(
            lessons, getattr(deps.config.runtime, "external_lesson_confidence", 0.5)
        )
    # Yazım kapısı: yalnızca ölçülebilir kanıtı olan, sır içermeyen, mevcut derslerle
    # çakışmayan adaylar belleğe girer. Bellek çöple/zehirle dolmasın.
    existing = deps.lessons.all()
    screened = learning.screen_lessons(
        lessons,
        existing,
        has_evidence=learning.has_measurable_evidence(messages),
        has_failure_evidence=any(m.role == "tool" and m.ok is False for m in messages),
    )
    # Ders görev-türü kapsamı olmadan (genel) saklanır: tür artık hesaplanmıyor.
    # Proje ve teknoloji süzgeci `workspace` ve `tags` ile zaten korunuyor.
    stored = learning.store_lessons(screened, deps.lessons)
    # Yeni dersle çelişen ESKİ dersin güveni düşer (A2-11); yan yana iki zıt kural
    # geri çağrılmasın.
    # Dış kaynaklı (doğrulanmamış) ders güvenilir eski dersi çürütemez (MINJA).
    if (
        stored
        and not external
        and not (
            deps.config.runtime.lesson_attributed_feedback
            or deps.config.runtime.lesson_conflict_quarantine
        )
    ):
        deps.lessons.reinforce(learning.contradicted_texts(screened, existing), success=False)
    if stored:
        deps.publisher.publish(LessonsLearned(count=stored, external=stored if external else 0))


def recall_hints(task: str, deps: AgentDeps) -> str:
    """Açık bayrakla en fazla iki dersi gerçek isteme sun."""
    if not deps.config.runtime.lesson_recall_hints:
        return ""
    from ...memory.lessons import as_prompt_block

    lessons = recall_lessons(task, deps, limit=HINT_LIMIT)[:HINT_LIMIT]
    lesson_attribution.offer(lessons, deps, LessonDelivery.HINT)
    return as_prompt_block(lessons)


async def finish_learning(
    outcome: AgentOutcome, deps: AgentDeps, *, plan_mode: bool, task: str = ""
) -> None:
    """Stop kancası dahil en son sonucu yalnız bir kez işle."""
    from ...memory.skill_proposals import SkillProposalError
    from .routine_observer import refresh_routines
    from .teacher_lessons import settle_advice

    if deps.lesson_state is not None:
        if deps.lesson_state.finished:
            return
        deps.lesson_state.finished = True
    await refresh_routines(deps)
    await asyncio.to_thread(settle_advice, outcome, deps)
    state = deps.lesson_state
    if deps.config.runtime.lesson_attributed_feedback:
        lesson_attribution.settle(outcome, deps)
        if task and not outcome.model_error and not outcome.budget_stopped:
            await learn(task, outcome, deps, plan_mode=plan_mode, final_closeout=True)
    if (
        state is not None
        and outcome.ok
        and not outcome.hit_step_limit
        and not outcome.budget_stopped
        and not outcome.model_error
        and deps.skill_proposals is not None
        and deps.config.runtime.verified_skill_proposals
    ):
        for routine, observation in state.routines:
            try:
                await deps.skill_proposals.observe(routine, observation)
            except (SkillProposalError, OSError):
                logger.warning(
                    "Rutin önerisi kaydedilemedi; ana iş sonucu korunuyor.", exc_info=True
                )

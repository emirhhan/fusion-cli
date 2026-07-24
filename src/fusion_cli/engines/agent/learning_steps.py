"""Agent turunun ders/bellek adımları: hatırla, pekiştir, çıkar, sakla.

Bu adımlar döngünün kendisinden ayrıdır: ana döngü modele araç çağırtırken, buradaki
işler turdan ÖNCE (ilgili dersleri hatırla) ve turdan SONRA (dersin güvenini güncelle,
yeni ders çıkar) çalışır. `loop.py` yalnızca bunları çağırır; ayrıntı burada durur.
"""

from __future__ import annotations

from dataclasses import replace

# Döngüsel import'tan kaçınmak için tip yalnızca kontrol anında içe alınır.
from typing import TYPE_CHECKING

from ...core.events import LessonsLearned, LessonsRecalled
from ...core.memory import Lesson
from ...core.types import Message
from . import learning
from .verification import resolve_turn_success

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome


def recall_lessons(task: str, deps: AgentDeps, *, scope: str | None) -> tuple[Lesson, ...]:
    """Göreve benzer, güveni eşiğin üstünde ve kapsamına uyan dersleri hatırla."""
    if deps.lessons is None or not deps.config.runtime.lessons:
        return ()
    recalled = deps.lessons.recall(task, scope=scope)
    if recalled:
        deps.publisher.publish(LessonsRecalled(count=len(recalled)))
    return recalled


async def reinforce_recalled(
    recalled: tuple[Lesson, ...], outcome: AgentOutcome, deps: AgentDeps, *, plan_mode: bool
) -> None:
    """Enjekte edilen derslerin güvenini turun sonucuna göre güncelle.

    Tur başarısı: model temiz bitti, adım sınırına dayanılmadı ve (doğrulama kapısı
    devredeyse) kapı geçti. Kod değiştiren turdan sonra kapı çalıştırılır; böylece
    "doğrulamadan bitirme" gibi kurallar dekoratif kalmaz, gerçekten uygulanır.
    """
    if deps.lessons is None or not deps.config.runtime.lessons:
        return
    if plan_mode or not recalled:
        return
    verification = None
    if deps.verifier is not None and outcome.tool_calls_made > 0:
        verification = await deps.verifier.verify()
    success = resolve_turn_success(
        outcome_ok=outcome.ok, hit_step_limit=outcome.hit_step_limit, verification=verification
    )
    deps.lessons.reinforce(tuple(lesson.text for lesson in recalled), success=success)


async def learn(
    task: str, outcome: AgentOutcome, deps: AgentDeps, *, plan_mode: bool, scope: str
) -> None:
    """Turdan ders çıkar ve belleğe yaz.

    Yalnızca GERÇEK İŞ yapıldıysa (araç çağrısı varsa) çalışır: sohbet turlarından
    ders çıkarmak hem boşuna model çağrısıdır hem de belleği değersiz kayıtla doldurur.
    """
    if deps.lessons is None or not deps.config.runtime.lessons:
        return
    if plan_mode or outcome.tool_calls_made == 0:
        return

    work = _extract_and_store(task, list(outcome.messages), deps, scope=scope)
    if deps.background is None:
        await work
    else:
        deps.background.spawn(work)


async def _extract_and_store(
    task: str, messages: list[Message], deps: AgentDeps, *, scope: str
) -> None:
    """Ders çıkarımının asıl işi. Arka planda çalışabilmesi için ayrı tutulur."""
    if deps.lessons is None:
        return
    lessons = await learning.extract_lessons(
        task, messages, config=deps.config, publisher=deps.publisher
    )
    # Yazım kapısı: yalnızca ölçülebilir kanıtı olan, sır içermeyen, mevcut derslerle
    # çakışmayan adaylar belleğe girer. Bellek çöple/zehirle dolmasın.
    screened = learning.screen_lessons(
        lessons,
        deps.lessons.all(),
        has_evidence=learning.has_measurable_evidence(messages),
    )
    # Öğrenilen ders, görevin kapsamıyla etiketlenir: benzer kapsamda daha isabetli
    # geri çağrılır, alakasız kapsamda enjekte edilmez.
    scoped = tuple(replace(lesson, scope=scope) for lesson in screened)
    stored = learning.store_lessons(scoped, deps.lessons)
    if stored:
        deps.publisher.publish(LessonsLearned(count=stored))

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
from ...core.verification import VerificationResult
from . import learning
from .verification import resolve_turn_success

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome


def _workspace(deps: AgentDeps) -> str:
    """Turun çalıştığı proje kökü — derslerin etiketlendiği ve süzüldüğü kimlik.

    Çözülmüş mutlak yol kullanılır: aynı projeye farklı göreli yollardan girmek
    (`.` ve `../fusion-cli`) iki ayrı workspace gibi görünmemeli.
    """
    return str(deps.tool_context.root.resolve()) if deps.tool_context is not None else ""


def recall_lessons(task: str, deps: AgentDeps, *, scope: str | None) -> tuple[Lesson, ...]:
    """Göreve benzer, güveni eşiğin üstünde ve kapsamına uyan dersleri hatırla."""
    if deps.lessons is None or not deps.config.runtime.lessons:
        return ()
    recalled = deps.lessons.recall(task, scope=scope, workspace=_workspace(deps))
    if recalled:
        deps.publisher.publish(LessonsRecalled(count=len(recalled)))
    return recalled


async def reinforce_recalled(
    recalled: tuple[Lesson, ...],
    outcome: AgentOutcome,
    deps: AgentDeps,
    *,
    plan_mode: bool,
    verification: VerificationResult | None = None,
) -> None:
    """Enjekte edilen derslerin güvenini turun sonucuna göre güncelle.

    Tur başarısı: model temiz bitti, adım sınırına dayanılmadı ve (doğrulama kapısı
    devredeyse) kapı geçti. Böylece "doğrulamadan bitirme" gibi kurallar dekoratif
    kalmaz, gerçekten uygulanır.

    `verification` DIŞARIDAN gelir: kapı tur başına bir kez çalışır ve aynı sonuç hem
    modele düzeltme talimatı olur hem buraya sinyal olarak düşer. Burada ikinci kez
    çalıştırmak hem israftı hem de iki farklı cevap alma riskiydi.
    """
    if deps.lessons is None or not deps.config.runtime.lessons:
        return
    if plan_mode or not recalled:
        return
    success = resolve_turn_success(
        outcome_ok=outcome.ok, hit_step_limit=outcome.hit_step_limit, verification=verification
    )
    deps.lessons.reinforce(tuple(lesson.text for lesson in recalled), success=success)


def should_learn(
    outcome: AgentOutcome, *, plan_mode: bool, allow_read_only: bool = True
) -> bool:
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
    scope: str,
    allow_read_only: bool = True,
) -> None:
    """Turdan ders çıkar ve belleğe yaz. Kapı kararı `should_learn`'dedir."""
    if deps.lessons is None or not deps.config.runtime.lessons:
        return
    if not should_learn(outcome, plan_mode=plan_mode, allow_read_only=allow_read_only):
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
        task,
        messages,
        config=deps.config,
        publisher=deps.publisher,
        workspace=_workspace(deps),
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

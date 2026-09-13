"""Keşif adımına bağlanmış komut kontrolünü MODELE SORMADAN düzeltir.

Keşif evresinde kabuk kapalıdır; o evredeki bir `command`/`reproduction` kontrolü
hiçbir denemede geçemez. Çelişki yürütücü tarafından yakalanıyor ve modelden
yeniden plan isteniyordu.

Ölçüldü (13 Eylül, Godot koşusu): model keşif adımını ikiye böldü ve çelişkiyi
YENİ adıma (`step-1-b-check-godot`, `godot --version`) aynen taşıdı. İkinci
ziyarette onarım hakkı kalmadığı için koşu on dakika sonunda hiçbir şey teslim
etmeden duraklatıldı. Aynı çelişkiyi modele iki kez sormak, cevabın değişmediği
ölçülmüş bir yerde bütçe yakmaktır.

Düzeltme mekaniktir ve YENİ YETKİ AÇMAZ: kontrol, o keşif adımına bağlı ilk
yürütme adımına taşınır (kabuk orada zaten açıktır); böyle bir adım yoksa kontrol
düşürülür ve başarı koşulu adımın kendi raporuna kalır. Keşif adımı hiçbir
durumda kabuk kazanmaz.
"""

from __future__ import annotations

from dataclasses import replace

from ...core.execution_plan import (
    ExecutionPlan,
    PlanPhase,
    PlanStep,
    StepStatus,
    VerificationCheck,
    VerificationCheckKind,
)

__all__ = ["SHELL_CHECK_KINDS", "conflicting_checks", "repair_discovery_phase"]

#: Kabuk gerektiren kontrol türleri.
SHELL_CHECK_KINDS = frozenset({VerificationCheckKind.COMMAND, VerificationCheckKind.REPRODUCTION})


def conflicting_checks(
    step: PlanStep, unavailable_tools: frozenset[str] = frozenset()
) -> tuple[VerificationCheck, ...]:
    """Bu adımın evresinde ÇALIŞAMAYACAK kontroller.

    `unavailable_tools`, yürütücünün o adım için hesapladığı KAPALI araç adlarıdır;
    araç kontrolü (kind: tool) böyle bir aracı hedefliyorsa o da çelişkilidir.
    """
    if step.phase is not PlanPhase.DISCOVERY:
        return ()
    return tuple(
        check
        for check in step.verification_checks
        if check.kind in SHELL_CHECK_KINDS
        or (check.kind is VerificationCheckKind.TOOL and check.target in unavailable_tools)
    )


def _temiz_baslangic(step: PlanStep) -> PlanStep:
    """Onarılan adımı HİÇ DENENMEMİŞ say.

    Adım geçerli bir yapılandırmada bir kez bile çalışmadı: çelişki yüzünden
    başlamadan reddedildi. Deneme sayacını taşımak, onu "kurtarma" kipinde
    (gözlem turu, kapalı yazma araçları) yeniden başlatır ve mekanik onarımın
    açtığı yolu hemen kapatır.
    """
    return replace(
        step, status=StepStatus.PENDING, attempts=0, last_progress_fingerprint=""
    )


def _first_dependent_execution(plan: ExecutionPlan, step_id: str) -> PlanStep | None:
    """Bu adıma bağlı ilk yürütme adımı; yoksa None.

    Plan sırası korunur: kontrolü mümkün olan EN ERKEN yürütme adımına taşımak,
    doğrulamayı görevin sonuna ertelemekten iyidir.
    """
    for item in plan.steps:
        if item.phase is PlanPhase.EXECUTION and step_id in item.depends_on:
            return item
    return None


def repair_discovery_phase(
    plan: ExecutionPlan, step: PlanStep, unavailable_tools: frozenset[str] = frozenset()
) -> ExecutionPlan | None:
    """Çelişkiyi mekanik olarak gider; giderilemiyorsa None döndür.

    None dönmesi "sorun yok" demek DEĞİLDİR: çelişki mekanik olarak çözülemiyor,
    karar yeniden planlamaya (ya da duraklatmaya) kalıyor demektir. Kontrol
    sessizce düşürülmez — ölçülemeyen bir başarı koşuluyla adımı yürütmek, işi
    yapılmış saymanın sessiz yoludur.
    """
    cakisan = conflicting_checks(step, unavailable_tools)
    if not cakisan:
        return None

    tasinan = _first_dependent_execution(plan, step.step_id)
    if tasinan is None and "shell" in step.allowed_tool_families:
        # Adım kabuk araçlarını KENDİSİ istemiş; yanlış olan tek şey evre etiketi.
        # Yetki plandan gelir, bu onarımdan değil: `allowed_tool_families` zaten
        # "shell" diyor ve kontrol de kabuk komutu ölçüyor. Doğru düzeltme,
        # kontrolü düşürmek değil evreyi bildirilen araçlarla hizalamaktır.
        hizalanmis = tuple(
            _temiz_baslangic(replace(item, phase=PlanPhase.EXECUTION))
            if item.step_id == step.step_id
            else item
            for item in plan.steps
        )
        return replace(plan, steps=hizalanmis)

    if tasinan is None:
        # Ne taşınacak bir yürütme adımı var ne de adımın kendi araç bildirimi
        # kontrolü mümkün kılıyor. Burada yapılacak mekanik bir şey yok.
        return None

    kalan_kontroller = tuple(
        check for check in step.verification_checks if check not in cakisan
    )
    # Kontrolü kalmayan başarı koşulu adımda KALIR: koşul hâlâ doğrudur, yalnız
    # makinece ölçülmez. Koşulu silmek, adımın ne yapacağını da silmek olurdu.
    yeni_kesif = _temiz_baslangic(replace(step, verification_checks=kalan_kontroller))

    adimlar: list[PlanStep] = []
    for item in plan.steps:
        if item.step_id == step.step_id:
            adimlar.append(yeni_kesif)
        elif item.step_id == tasinan.step_id:
            # Taşınan kontrolün başarı koşulu, hedef adımda TANIMLI olmalı:
            # `validate_plan` her kontrolün koşulunu o adımın koşulları arasında
            # arar (bkz. `core.execution_plan.validate_plan`).
            eklenecek = tuple(
                check.criterion_id
                for check in cakisan
                if check.criterion_id not in item.success_criteria
            )
            adimlar.append(
                replace(
                    item,
                    success_criteria=item.success_criteria + eklenecek,
                    verification_checks=item.verification_checks + cakisan,
                )
            )
        else:
            adimlar.append(item)
    return replace(plan, steps=tuple(adimlar))

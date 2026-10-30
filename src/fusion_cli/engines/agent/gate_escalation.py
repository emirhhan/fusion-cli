"""Doğrulama kapısı kırmızı kalınca TEK bir üst modelle ek düzeltme turu.

Ölçüldü (30 Ekim): kod değiştiren tur kapıdan geçemezse `loop.run_agent` en çok iki
doğrula+düzelt turu açar (`MAX_VERIFY_ROUNDS`) ve son düzeltmeyi bir kez daha ölçer.
İki düzeltme de aynı modelle yapılır: ilki seçili modelin ilk yedeğiyle (çoğu zaman
AYNI modelin başka sağlayıcıdaki kopyası), ikincisi de aynı zincirle. Kademe
merdiveni tanımlı olduğu halde, modelin işi beceremediği yerde daha güçlü bir modele
çıkılmıyordu (bkz. `reports/Fusion ajan zekâsı eksikleri.md`, yol haritası 6. adım).

Bu modül yalnız KARARI ve kullanıcıya görünen metinleri taşır; düzeltme turunu
`loop._fix_findings` koşturur. Sinyal yalnız gerçek kapı sonucudur (test, derleme,
doğrulayıcı) — modelin "düzelttim" beyanı sayılmaz. Üst model yoksa hiçbir şey olmaz.

Birden çok aday üretip `attempts.choose_attempt` ile seçmek (yol haritası: isteğe bağlı)
BİLEREK yapılmadı: `choose_attempt` izole çalışma alanında koşan adaylara ve her
adayın kendi kök dizininde ölçülmüş kanıta dayanır (`plan_runner.run_candidates`);
kapı doğrulayıcısı (`deps.verifier`) ise tek bir proje köküne bağlıdır ve kopya kök
için kurulamaz. Kapı turunda aday çoğaltmak ayrıca model başı dakikalık hız sınırını
(NIM 40 istek) katlar.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ...config.model_select import EscalationTarget, escalation_target, select_agent_spec
from ...core.errors import ConfigError

if TYPE_CHECKING:
    from .loop import AgentDeps

#: Düzeltme başlarken kullanıcıya giden durum satırı.
STATUS_ESCALATING = "Doğrulama {rounds} kez başarısız; {model} modeliyle bir deneme daha yapılıyor"
#: Ek tur kapıyı geçti / geçemedi.
STATUS_GREEN = "Üst model denemesi kapıyı geçirdi ({model})"
STATUS_RED = "Üst model denemesi de kapıyı geçemedi ({model})"
#: Tur sonuç metnine eklenen rapor satırları (kullanıcı raporda görür).
REPORT_GREEN = (
    "\n\nDoğrulama {rounds} düzeltmeden sonra da başarısızdı; {model} modeliyle yapılan "
    "ek denemeden sonra kapı geçti."
)
REPORT_RED = (
    "\n\nDoğrulama {rounds} düzeltmeden sonra da başarısızdı; {model} modeliyle yapılan "
    "ek deneme de kapıyı geçemedi."
)
REPORT_UNMEASURED = (
    "\n\nDoğrulama {rounds} düzeltmeden sonra da başarısızdı; {model} modeliyle ek deneme "
    "yapıldı ama sonucu ölçülemedi."
)


@dataclass(frozen=True, slots=True)
class GateEscalation:
    """Hazırlanmış yükseltme: hedef, hangi modelden çıkıldığı ve ek turun bağımlılıkları."""

    target: EscalationTarget
    from_model: str
    deps: AgentDeps


def prepare(deps: AgentDeps) -> GateEscalation | None:
    """Bu tur için üst model varsa ek turun bağımlılıklarını kur; yoksa `None`.

    `None` döner: ayar kapalıysa (ya da yapılandırma nesnesi alanı taşımıyorsa), model
    devri (çırak/öğretmen) sürüyorsa, tur web taşımasındaysa, seçilen model `strict`
    ise ya da tanımlı bir üst model yoksa. Bağımlılık kopyası yalnız `config.agent`'ı
    değiştirir; bütçe, çalışma alanı, onay, sağlık/hız sınırı kapısı paylaşılır.
    """
    runtime = deps.config.runtime
    if not getattr(runtime, "escalate_on_gate_failure", False):
        return None
    if deps.active_model_override is not None:
        return None
    if deps.execution is not None and deps.execution.is_web:
        return None
    try:
        current = select_agent_spec(
            deps.config, deps.task_type, requirements=deps.task_requirements
        )
    except ConfigError:
        return None
    target = escalation_target(deps.config, current)
    if target is None:
        return None
    escalated = replace(
        deps,
        config=replace(deps.config, agent=target.spec, task_model_map={}),
    )
    # Görev gereksinimleri (ör. görsel girdi) üst modeli elerse havuz başka bir modele
    # düşerdi; kullanıcıya söylediğimizden farklı bir model çalıştırmayız.
    try:
        chosen = select_agent_spec(
            escalated.config, escalated.task_type, requirements=escalated.task_requirements
        )
    except ConfigError:
        return None
    if chosen.model != target.spec.model:
        return None
    return GateEscalation(target=target, from_model=current.model, deps=escalated)

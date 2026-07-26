"""Kurulum gerçekten kullanılabilir mi?

`detect().any_configured` bu soruyu cevaplamıyordu: bir anahtarın VARLIĞI, o
anahtarla zorunlu rollerin çalışabileceği anlamına gelmez. NIM anahtarı olan ama
zincirlerinde NIM modeli bulunmayan bir yapılandırmada "kurulum tamam" demek
kullanıcıyı ilk turda "hiçbir model yanıt veremedi" hatasına sürüklerdi.

Karar VARSAYIMLA değil, etkin yapılandırmadaki zincirlere bakılarak verilir:
her rol için "bu zincirde çalıştırabileceğim en az bir model var mı?".

Üç durum ayrılır çünkü tepkileri farklıdır:

- `READY`         — agent, hakem ve en az bir aday çalışır. Kullanıcı başlayabilir.
- `PARTIALLY_READY` — agent çalışır ama hakem ya da adaylar eksik. Agent turu döner,
  fusion motoru eksik çalışır. Kullanıcı uyarılır ama engellenmez.
- `NOT_READY`     — agent bile çalışmaz. Başlamanın anlamı yok.

Bu modül SAF'tır: ağ çağrısı yapmaz, dosya yazmaz. "Model gerçekten yanıt veriyor
mu" sorusu ayrıdır ve yalnızca `fusion doctor --live` ile sorulur.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..core.types import ModelSpec
from .keys import ProviderKeys
from .models import Config


class Readiness(Enum):
    """Kurulumun kullanılabilirlik durumu."""

    READY = "ready"
    PARTIALLY_READY = "partially_ready"
    NOT_READY = "not_ready"


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """Değerlendirmenin sonucu ve GEREKÇESİ.

    `reasons` boş değilse kullanıcıya ne eksik olduğu satır satır gösterilir;
    "hazır değil" demek tek başına kullanıcıya ne yapacağını söylemez.
    """

    state: Readiness
    agent_ok: bool
    judge_ok: bool
    candidates_ok: bool
    reasons: tuple[str, ...] = ()


def is_usable(spec: ModelSpec, keys: ProviderKeys) -> bool:
    """Bu rolün zincirinde çalıştırılabilir en az bir model var mı?

    Tanınmayan önekler (ollama, openai-uyumlu yerel uçlar) KULLANILABİLİR sayılır:
    onların anahtar gereksinimini bilemeyiz ve kullanıcı bilerek yazmıştır. Yerel
    model kullanan ileri kullanıcı, bulut anahtarı yok diye engellenmemelidir.
    """
    return any(keys.supports(model) for model in spec.models)


def evaluate(config: Config, keys: ProviderKeys) -> ReadinessReport:
    """Etkin yapılandırmayı kurulu anahtarlara karşı değerlendir."""
    agent_ok = is_usable(config.agent, keys)
    judge_ok = is_usable(config.judge, keys)
    candidates_ok = any(is_usable(spec, keys) for spec in config.candidates)

    reasons: list[str] = []
    if not agent_ok:
        reasons.append("Agent rolü için kullanılabilir model yok (agent turu çalışmaz).")
    if not judge_ok:
        reasons.append("Hakem rolü için kullanılabilir model yok (fusion motoru eksik çalışır).")
    if not candidates_ok:
        reasons.append("Aday havuzunda kullanılabilir model yok (fusion motoru çalışmaz).")
    if reasons and not keys.any_configured:
        # Anahtar yokluğu tek başına sorun DEĞİLDİR (yerel model kullanan kullanıcı
        # anahtarsız çalışır); ancak roller de eksikse muhtemel sebep budur.
        reasons.append("Hiçbir API anahtarı bulunamadı. `fusion setup` ile ekleyebilirsin.")

    return ReadinessReport(
        state=_state(agent_ok, judge_ok, candidates_ok),
        agent_ok=agent_ok,
        judge_ok=judge_ok,
        candidates_ok=candidates_ok,
        reasons=tuple(reasons),
    )


def _state(agent_ok: bool, judge_ok: bool, candidates_ok: bool) -> Readiness:
    """Agent belirleyicidir: o çalışmıyorsa başlamanın anlamı yok."""
    if not agent_ok:
        return Readiness.NOT_READY
    if judge_ok and candidates_ok:
        return Readiness.READY
    return Readiness.PARTIALLY_READY

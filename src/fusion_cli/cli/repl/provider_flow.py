"""`/provider` akışı — hangi sağlayıcının kullanılacağını seç ve kalıcılaştır.

Neden ayrı bir seçim: bir sağlayıcının tükenmesi ötekini de tüketiyordu. NIM
kredisi bitince tüm yük yedek zinciri üzerinden OpenRouter'a bindi ve günlük 50
istek birkaç dakikada bitti — kullanıcı iki kotayı birden kaybetti.

Tercih belirlenince ötekine HİÇ istek gitmez. Bedeli yedeğin kaybıdır; bu takas
kullanıcının kararıdır ve ekranda açıkça yazar.
"""

from __future__ import annotations

from dataclasses import replace

from ...config import writer
from ...config.keys import ProviderPreference
from ...config.models import Config
from ...core.errors import ConfigError
from ...ui import messages
from ...ui.picker import Choice, pick
from .model_flows import FlowResult, Picker

#: Seçim ekranındaki sıra: önce mevcut davranış (otomatik), sonra kilitlemeler.
_SECENEKLER = (
    (ProviderPreference.AUTO, messages.PROVIDER_AUTO, messages.PROVIDER_AUTO_HINT),
    (ProviderPreference.NVIDIA, messages.PROVIDER_NVIDIA, messages.PROVIDER_NVIDIA_HINT),
    (
        ProviderPreference.OPENROUTER,
        messages.PROVIDER_OPENROUTER,
        messages.PROVIDER_OPENROUTER_HINT,
    ),
)


def choose_provider(config: Config, *, picker: Picker = pick) -> FlowResult:
    """Sağlayıcıyı seçtir, uygula ve kaydet."""
    mevcut = messages.PROVIDER_CURRENT.format(name=config.runtime.provider)
    baslik = f"{mevcut}\n\n{messages.PROVIDER_TITLE}"
    secim = picker(
        tuple(Choice(tercih.value, etiket, ipucu) for tercih, etiket, ipucu in _SECENEKLER),
        title=baslik,
    )
    if secim is None:
        return FlowResult(config, messages.PICKER_CANCELLED)

    updated = replace(config, runtime=replace(config.runtime, provider=secim))
    return FlowResult(updated, f"{_applied(updated, secim)}\n{_persist(updated, secim)}")


def _applied(config: Config, secim: str) -> str:
    return messages.PROVIDER_APPLIED.format(name=secim, model=config.agent.model)


def _persist(config: Config, secim: str) -> str:
    """Seçimi kalıcılaştır. Yazamamak akışı bozmaz, yalnızca bildirilir.

    Tercih YENİDEN YÜKLEMEDE etkili olur: zincir budama yükleme sırasında yapılır.
    """
    try:
        return messages.LEVEL_SAVED.format(path=writer.write_provider(config, secim))
    except ConfigError as error:
        return messages.LEVEL_SAVE_FAILED.format(error=error)

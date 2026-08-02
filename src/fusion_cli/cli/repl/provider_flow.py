"""`/provider` akışı — hangi sağlayıcının kullanılacağını seç ve kalıcılaştır.

Neden ayrı bir seçim: bir sağlayıcının tükenmesi ötekini de tüketiyordu. NIM
kredisi bitince tüm yük yedek zinciri üzerinden OpenRouter'a bindi ve günlük 50
istek birkaç dakikada bitti — kullanıcı iki kotayı birden kaybetti.

Tercih belirlenince ötekine HİÇ istek gitmez. Bedeli yedeğin kaybıdır; bu takas
kullanıcının kararıdır ve ekranda açıkça yazar.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from ...config import writer
from ...config.credentials import FernetSecretStore
from ...config.keys import ProviderPreference
from ...config.models import Config
from ...core.errors import ConfigError
from ...providers.registry import BUILTIN_PROVIDERS, ProviderDefinition
from ...ui import messages
from ...ui.picker import Choice, pick
from .model_flows import FlowResult, Picker

#: Sırrı EKRANA YANSITMADAN alan girdi imzası. Vazgeçilirse None.
SecretAsker = Callable[[str], str | None]

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


# --------------------------------------------------------------------------- #
# /providers add — sağlayıcı anahtarı ekleme sihirbazı
# --------------------------------------------------------------------------- #


def _addable(providers: tuple[ProviderDefinition, ...]) -> tuple[ProviderDefinition, ...]:
    """Anahtar EKLENEBİLEN sağlayıcılar: yürütücüsü olan ve anahtar isteyen.

    Yerel (anahtarsız) ve yürütücüsü olmayan (web-session, framework) sağlayıcılar
    dışarıda kalır — onlara anahtar eklemek anlamsızdır.
    """
    return tuple(p for p in providers if p.implemented and p.auth_env is not None)


def add_credential(
    store: FernetSecretStore,
    *,
    picker: Picker = pick,
    ask_secret: SecretAsker,
    providers: tuple[ProviderDefinition, ...] = BUILTIN_PROVIDERS,
) -> str:
    """`/providers add` — bir sağlayıcı seç, anahtarını ŞİFRELİ depoya kaydet.

    Anahtar ekranda gösterilmez, log'a yazılmaz; yalnızca şifreli dosyaya girer ve
    sonraki oturumda ortama uygulanır. Depo ana anahtarı (FUSION_SECRET_KEY) yoksa
    işlem yapılmaz ve kullanıcı bilgilendirilir.
    """
    if not store.available:
        return messages.CRED_NO_KEY
    eklenebilir = _addable(providers)
    picked = picker(
        tuple(Choice(p.id, p.name, p.auth_env or "") for p in eklenebilir),
        title=messages.CRED_TITLE,
    )
    definition = next((p for p in eklenebilir if p.id == picked), None)
    if definition is None or definition.auth_env is None:
        return messages.PICKER_CANCELLED
    secret = ask_secret(messages.CRED_PROMPT.format(name=definition.name))
    if not secret or not secret.strip():
        return messages.PICKER_CANCELLED
    try:
        store.set(definition.auth_env, secret.strip())
    except ConfigError as error:
        return str(error)
    # DİKKAT: mesajda anahtar YOK; yalnızca hangi sağlayıcının kaydedildiği yazılır.
    return messages.CRED_SAVED.format(name=definition.name, env=definition.auth_env)

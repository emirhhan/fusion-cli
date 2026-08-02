"""Sağlayıcı tanım kayıt defteri — Fusion'ın TANIDIĞI sağlayıcıların metadata'sı.

Model ile sağlayıcı aynı şey değildir (master prompt §6): model bir aile/sürüm,
sağlayıcı onu sunan API/OAuth/yerel çalışma ortamıdır. Model kimliğinin öneki
(`nvidia_nim/…`, `openrouter/…`) sağlayıcıyı belirler (LiteLLM sözleşmesi).

Bu modül YÜRÜTÜCÜ DEĞİLDİR: çağrıyı yine LiteLLM yapar (universal adaptör). Burada
yalnızca sağlayıcının KİMLİĞİ tutulur — türü, kimlik doğrulama biçimi, resmî durumu
ve risk seviyesi. Bu metadata `/providers` ekranını besler ve dürüst etiketleme
sağlar (resmî/gayrıresmî, riskli). Yeni sağlayıcı eklemek buraya bir tanım eklemektir;
motor ya da router kodu değişmez.

Ortam değişkeni adları ve önekler `config.keys`'ten gelir — tek doğruluk kaynağı
orasıdır, burada kopyalanmaz.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from ..config.keys import NIM_ENV, NIM_PREFIX, OPENROUTER_ENV, OPENROUTER_PREFIX


class ProviderKind(Enum):
    """Sağlayıcının bağlantı türü."""

    API_KEY = "api_key"
    OAUTH = "oauth"
    CLI_OAUTH = "cli_oauth"
    WEB_SESSION = "web_session"
    BROWSER_BACKED = "browser_backed"
    LOCAL = "local"
    AGGREGATOR = "aggregator"


class OfficialStatus(Enum):
    """Entegrasyonun resmiyet düzeyi. Kullanıcı ne kullandığını bilmelidir."""

    OFFICIAL_API = "official_api"
    OFFICIAL_OAUTH = "official_oauth"
    COMPATIBLE_API = "compatible_api"
    OFFICIAL_CLI = "official_cli"
    UNOFFICIAL_WEB = "unofficial_web"
    EXPERIMENTAL = "experimental"


class RiskLevel(Enum):
    """Sağlayıcıyı kullanmanın riski. Web/abonelik sağlayıcıları normal değildir."""

    NORMAL = "normal"
    SUBSCRIPTION = "subscription"
    FRAGILE = "fragile"
    TERMS_REVIEW_REQUIRED = "terms_review_required"
    EXPERIMENTAL = "experimental"
    DISABLED_BY_DEFAULT = "disabled_by_default"


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    """Bir sağlayıcının kimliği ve metadata'sı."""

    #: Kararlı kimlik (`openrouter`, `nvidia_nim`, `ollama`).
    id: str
    #: Kullanıcıya görünen ad.
    name: str
    kind: ProviderKind
    official_status: OfficialStatus
    risk_level: RiskLevel
    #: Model kimliği öneki (`openrouter/`). Boşsa önekle çözülemez (ör. yereldeki
    #: serbest uçlar).
    model_prefix: str
    #: Kimlik doğrulama ortam değişkeni. `None` ise anahtar gerekmez (yerel).
    auth_env: str | None

    def owns(self, model_id: str) -> bool:
        """Bu model kimliği bu sağlayıcıya mı ait? (önek eşleşmesi)"""
        return bool(self.model_prefix) and model_id.startswith(self.model_prefix)

    def is_configured(self, environ: Mapping[str, str]) -> bool:
        """Bu sağlayıcı kullanıma hazır mı?

        Anahtar gerektirmeyen (yerel) sağlayıcı daima hazır sayılır — çalışma
        ortamının erişilebilirliği burada ölçülemez, çağrı anında belli olur.
        Anahtar gerektiren sağlayıcı ancak ilgili ortam değişkeni DOLU ise hazırdır.
        """
        if self.auth_env is None:
            return True
        return bool(environ.get(self.auth_env, "").strip())


#: Fusion'ın bugün TANIDIĞI sağlayıcılar. Liste körlemesine şişirilmez (gerçekçilik
#: kuralı §22): yalnızca gerçekten desteklenen sağlayıcılar dürüst metadata ile.
#: Web-session sağlayıcıları ayrı bir fazda, kendi yürütücüleriyle eklenecektir.
BUILTIN_PROVIDERS: tuple[ProviderDefinition, ...] = (
    ProviderDefinition(
        id="openrouter",
        name="OpenRouter",
        kind=ProviderKind.AGGREGATOR,
        official_status=OfficialStatus.OFFICIAL_API,
        risk_level=RiskLevel.NORMAL,
        model_prefix=OPENROUTER_PREFIX,
        auth_env=OPENROUTER_ENV,
    ),
    ProviderDefinition(
        id="nvidia_nim",
        name="NVIDIA NIM",
        kind=ProviderKind.API_KEY,
        official_status=OfficialStatus.OFFICIAL_API,
        risk_level=RiskLevel.NORMAL,
        model_prefix=NIM_PREFIX,
        auth_env=NIM_ENV,
    ),
    ProviderDefinition(
        id="ollama",
        name="Ollama (yerel)",
        kind=ProviderKind.LOCAL,
        # LiteLLM üzerinden OpenAI-uyumlu; anahtar gerekmez, çevrimdışı çalışır.
        official_status=OfficialStatus.COMPATIBLE_API,
        risk_level=RiskLevel.NORMAL,
        model_prefix="ollama/",
        auth_env=None,
    ),
)


def provider_for_model(
    model_id: str, providers: tuple[ProviderDefinition, ...] = BUILTIN_PROVIDERS
) -> ProviderDefinition | None:
    """Model kimliğinin ait olduğu sağlayıcı tanımını bul; tanınmıyorsa `None`.

    `None`, "bu önek yönetilen bir sağlayıcı değil" demektir (kullanıcının yazdığı
    serbest bir uç olabilir) — hata değildir.
    """
    return next((provider for provider in providers if provider.owns(model_id)), None)

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

from ..config.keys import (
    ANTHROPIC_ENV,
    ANTHROPIC_PREFIX,
    GEMINI_ENV,
    GEMINI_PREFIX,
    NIM_ENV,
    NIM_PREFIX,
    OPENAI_ENV,
    OPENAI_PREFIX,
    OPENROUTER_ENV,
    OPENROUTER_PREFIX,
)


class ProviderKind(Enum):
    """Sağlayıcının bağlantı türü."""

    API_KEY = "api_key"
    OAUTH = "oauth"
    CLI_OAUTH = "cli_oauth"
    WEB_SESSION = "web_session"
    BROWSER_BACKED = "browser_backed"
    LOCAL = "local"
    AGGREGATOR = "aggregator"
    #: Modalite türleri — sağlayıcı LLM değil, gömme/yeniden-sıralama sunar.
    EMBEDDING = "embedding"
    RERANK = "rerank"


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
    #: Yürütücüsü GERÇEKTEN var mı? `False` ise sağlayıcı yalnızca framework düzeyinde
    #: tanınır; çağrı yapılamaz (§22 "framework supported, adapter not yet implemented").
    #: Kullanıcı `/providers` ekranında bunu görür ve çalışıyor sanmaz.
    implemented: bool = True

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


# Sağlayıcı tablosu — hepsi GERÇEK ve LiteLLM üzerinden çalışır (kullanıcı anahtarıyla).
# Uydurma yok (§22): her satır LiteLLM'in tanıdığı bir önek + o sağlayıcının ortam
# değişkeni adıdır. Fusion çağrıyı LiteLLM'e verir; anahtar varsa model yanıt verir.
# Sütunlar: (id, ad, kind, resmiyet, model öneki, ortam değişkeni | None)
_K = ProviderKind
_S = OfficialStatus
_API = _S.OFFICIAL_API
_COMPAT = _S.COMPATIBLE_API

_TABLE: tuple[tuple[str, str, ProviderKind, OfficialStatus, str, str | None], ...] = (
    # Ürünün ücretsiz taban çizgisi
    ("openrouter", "OpenRouter", _K.AGGREGATOR, _API, OPENROUTER_PREFIX, OPENROUTER_ENV),
    ("nvidia_nim", "NVIDIA NIM", _K.API_KEY, _API, NIM_PREFIX, NIM_ENV),
    # Büyük resmî API'ler
    ("openai", "OpenAI", _K.API_KEY, _API, OPENAI_PREFIX, OPENAI_ENV),
    ("anthropic", "Anthropic", _K.API_KEY, _API, ANTHROPIC_PREFIX, ANTHROPIC_ENV),
    ("gemini", "Google Gemini", _K.API_KEY, _API, GEMINI_PREFIX, GEMINI_ENV),
    ("azure", "Azure OpenAI", _K.API_KEY, _API, "azure/", "AZURE_API_KEY"),
    ("azure_ai", "Azure AI", _K.API_KEY, _API, "azure_ai/", "AZURE_AI_API_KEY"),
    (
        "vertex_ai",
        "Google Vertex AI",
        _K.OAUTH,
        _API,
        "vertex_ai/",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ),
    ("bedrock", "AWS Bedrock", _K.API_KEY, _API, "bedrock/", "AWS_ACCESS_KEY_ID"),
    ("sagemaker", "AWS SageMaker", _K.API_KEY, _API, "sagemaker/", "AWS_ACCESS_KEY_ID"),
    ("mistral", "Mistral", _K.API_KEY, _API, "mistral/", "MISTRAL_API_KEY"),
    ("codestral", "Mistral Codestral", _K.API_KEY, _API, "codestral/", "CODESTRAL_API_KEY"),
    ("cohere", "Cohere", _K.API_KEY, _API, "cohere/", "COHERE_API_KEY"),
    ("ai21", "AI21", _K.API_KEY, _API, "ai21/", "AI21_API_KEY"),
    ("xai", "xAI (Grok)", _K.API_KEY, _API, "xai/", "XAI_API_KEY"),
    ("deepseek", "DeepSeek", _K.API_KEY, _API, "deepseek/", "DEEPSEEK_API_KEY"),
    ("moonshot", "Moonshot (Kimi)", _K.API_KEY, _API, "moonshot/", "MOONSHOT_API_KEY"),
    ("dashscope", "Alibaba DashScope (Qwen)", _K.API_KEY, _API, "dashscope/", "DASHSCOPE_API_KEY"),
    ("volcengine", "Volcengine", _K.API_KEY, _API, "volcengine/", "VOLCENGINE_API_KEY"),
    # Hızlı çıkarım / GPU bulutları
    ("groq", "Groq", _K.API_KEY, _API, "groq/", "GROQ_API_KEY"),
    ("cerebras", "Cerebras", _K.API_KEY, _API, "cerebras/", "CEREBRAS_API_KEY"),
    ("sambanova", "SambaNova", _K.API_KEY, _API, "sambanova/", "SAMBANOVA_API_KEY"),
    ("together_ai", "Together AI", _K.AGGREGATOR, _API, "together_ai/", "TOGETHERAI_API_KEY"),
    ("fireworks_ai", "Fireworks AI", _K.AGGREGATOR, _API, "fireworks_ai/", "FIREWORKS_AI_API_KEY"),
    ("deepinfra", "DeepInfra", _K.AGGREGATOR, _API, "deepinfra/", "DEEPINFRA_API_KEY"),
    ("anyscale", "Anyscale", _K.AGGREGATOR, _API, "anyscale/", "ANYSCALE_API_KEY"),
    ("perplexity", "Perplexity", _K.API_KEY, _API, "perplexity/", "PERPLEXITYAI_API_KEY"),
    ("replicate", "Replicate", _K.AGGREGATOR, _API, "replicate/", "REPLICATE_API_KEY"),
    ("novita", "Novita AI", _K.AGGREGATOR, _API, "novita/", "NOVITA_API_KEY"),
    ("baseten", "Baseten", _K.API_KEY, _API, "baseten/", "BASETEN_API_KEY"),
    ("cloudflare", "Cloudflare Workers AI", _K.API_KEY, _API, "cloudflare/", "CLOUDFLARE_API_KEY"),
    ("databricks", "Databricks", _K.API_KEY, _API, "databricks/", "DATABRICKS_API_KEY"),
    ("watsonx", "IBM watsonx", _K.API_KEY, _API, "watsonx/", "WATSONX_APIKEY"),
    ("clarifai", "Clarifai", _K.API_KEY, _API, "clarifai/", "CLARIFAI_API_KEY"),
    ("friendliai", "FriendliAI", _K.API_KEY, _API, "friendliai/", "FRIENDLI_TOKEN"),
    ("github", "GitHub Models", _K.API_KEY, _API, "github/", "GITHUB_API_KEY"),
    ("nlp_cloud", "NLP Cloud", _K.API_KEY, _API, "nlp_cloud/", "NLP_CLOUD_API_KEY"),
    ("huggingface", "Hugging Face", _K.AGGREGATOR, _API, "huggingface/", "HUGGINGFACE_API_KEY"),
    # Yerel / kendi barındırdığın (anahtar gerekmez)
    ("ollama", "Ollama (yerel)", _K.LOCAL, _COMPAT, "ollama/", None),
    ("ollama_chat", "Ollama Chat (yerel)", _K.LOCAL, _COMPAT, "ollama_chat/", None),
    ("hosted_vllm", "vLLM (yerel/uzak)", _K.LOCAL, _COMPAT, "hosted_vllm/", None),
    ("lm_studio", "LM Studio (yerel)", _K.LOCAL, _COMPAT, "lm_studio/", None),
    # Gömme / yeniden-sıralama (Fusion belleği ve arama için)
    ("voyage", "Voyage AI (embedding)", _K.EMBEDDING, _API, "voyage/", "VOYAGE_API_KEY"),
    ("jina_ai", "Jina AI (embedding/rerank)", _K.EMBEDDING, _API, "jina_ai/", "JINA_AI_API_KEY"),
)

#: Web-session sağlayıcıları: FRAMEWORK düzeyinde tanınır, yürütücüsü YOK (§22).
#: Çalışan bir web adaptörü kırılgandır, sağlayıcı şartlarının incelenmesini ister ve
#: dürüstçe "working" işaretlenemez; `implemented=False`, `disabled_by_default`.
#: CAPTCHA/anti-bot aşımı, izinsiz cookie okuma YAPILMAZ.
_WEB: tuple[tuple[str, str], ...] = (
    ("chatgpt_web", "ChatGPT Web (deneysel)"),
    ("gemini_web", "Gemini Web (deneysel)"),
    ("claude_web", "Claude Web (deneysel)"),
    ("copilot_web", "Microsoft Copilot Web (deneysel)"),
)


def _build_registry() -> tuple[ProviderDefinition, ...]:
    api = tuple(
        ProviderDefinition(
            id=pid,
            name=name,
            kind=kind,
            official_status=status,
            risk_level=RiskLevel.NORMAL,
            model_prefix=prefix,
            auth_env=env,
        )
        for pid, name, kind, status, prefix, env in _TABLE
    )
    web = tuple(
        ProviderDefinition(
            id=pid,
            name=name,
            kind=ProviderKind.WEB_SESSION,
            official_status=OfficialStatus.UNOFFICIAL_WEB,
            risk_level=RiskLevel.DISABLED_BY_DEFAULT,
            model_prefix="",
            auth_env=None,
            implemented=False,
        )
        for pid, name in _WEB
    )
    return api + web


#: Fusion'ın TANIDIĞI sağlayıcılar. Hepsi gerçek: API'ler LiteLLM ile çalışır,
#: web olanlar framework düzeyinde (adaptörü kullanıcı sağlar). Uydurma satır yok.
BUILTIN_PROVIDERS: tuple[ProviderDefinition, ...] = _build_registry()


def provider_for_model(
    model_id: str, providers: tuple[ProviderDefinition, ...] = BUILTIN_PROVIDERS
) -> ProviderDefinition | None:
    """Model kimliğinin ait olduğu sağlayıcı tanımını bul; tanınmıyorsa `None`.

    `None`, "bu önek yönetilen bir sağlayıcı değil" demektir (kullanıcının yazdığı
    serbest bir uç olabilir) — hata değildir.
    """
    return next((provider for provider in providers if provider.owns(model_id)), None)

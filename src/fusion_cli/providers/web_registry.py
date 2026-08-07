"""Web sağlayıcı kayıt defteri: kendi HTTP uçların ve tarayıcı tabanlı abonelikler.

Model kimliğinden yapılandırılmış web oturumuna eşleme burada yapılır. Sır asla
yapılandırmadan gelmez: HTTP ucu token'ı ortam değişkeninden, tarayıcı oturumunun
Cookie'si şifreli depodan okunur.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from ..config.credentials import FernetSecretStore
from ..config.models import WebSessionConfig
from ..config.paths import credentials_file
from ..core.model_capability import ToolSupport
from ..core.protocols import Clock, LlmProvider
from ..core.types import Message
from .web_browser import build_browser_transport
from .web_session import WebProviderAdapter, WebSessionCredential, WebTransport
from .web_transport import build_http_transport

if TYPE_CHECKING:  # pragma: no cover
    from ..config.models import Config

TransportFactory = Callable[..., WebTransport]
_TOOL_SUPPORT = {"none": ToolSupport.NONE, "emulated": ToolSupport.EMULATED}


class WebSessionRegistry:
    """Model kimliği → yapılandırılmış web sağlayıcı adaptörü."""

    def __init__(
        self,
        sessions: tuple[WebSessionConfig, ...],
        *,
        environ: Mapping[str, str],
        secret_store: FernetSecretStore | None = None,
        trace_dir: Path | None = None,
    ) -> None:
        self._by_model = {session.model: session for session in sessions if session.enabled}
        self._environ = environ
        self._secret_store = secret_store
        #: Verilirse tarayıcı alışverişi buraya redakte edilerek yazılır (teşhis).
        self._trace_dir = trace_dir

    @property
    def is_empty(self) -> bool:
        return not self._by_model

    @property
    def models(self) -> tuple[str, ...]:
        return tuple(self._by_model)

    def session_for(self, model: str) -> WebSessionConfig | None:
        return self._by_model.get(model)

    def build(
        self,
        model: str,
        *,
        clock: Clock | None = None,
        transport_factory: TransportFactory = build_http_transport,
    ) -> LlmProvider | None:
        session = self._by_model.get(model)
        if session is None:
            return None
        return self.build_session(session, clock=clock, transport_factory=transport_factory)

    def build_session(
        self,
        session: WebSessionConfig,
        *,
        clock: Clock | None = None,
        transport_factory: TransportFactory = build_http_transport,
    ) -> LlmProvider:
        """Verilen oturum yapılandırmasından sağlayıcı kur.

        Model kimliğiyle DEĞİL yapılandırmayla çalışır. Sebep ölçüldü: araç yeteneği
        sondası ham çıktı almak için araç desteği kapatılmış bir oturum KOPYASI
        üretiyor, ama yalnızca kopyanın `model` alanını `build()`'e veriyordu. Model
        kimliği değişmediği için kayıt defteri ORİJİNAL oturumu buluyor, adaptör
        emulated kipte kuruluyor ve araç bloklarını metinden çıkarıyordu. Sonuç:
        sonda "boş çıktı" görüyor ve modeli hiç araç üretmemiş sayıyordu.
        """
        credential = self._credential(session)
        if session.transport == "browser":
            transport = build_browser_transport(session, trace_dir=self._trace_dir)
        else:
            if not session.endpoint:
                return WebProviderAdapter(
                    model=session.model,
                    credential=credential,
                    transport=_missing_endpoint_transport,
                    tool_support=_TOOL_SUPPORT.get(session.tool_support, ToolSupport.NONE),
                    clock=clock,
                )
            transport = transport_factory(session.endpoint)
        return WebProviderAdapter(
            model=session.model,
            credential=credential,
            transport=transport,
            tool_support=_TOOL_SUPPORT.get(session.tool_support, ToolSupport.NONE),
            clock=clock,
        )

    def _credential(self, session: WebSessionConfig) -> WebSessionCredential:
        if session.transport == "browser":
            cookie = ""
            if session.credential_ref and self._secret_store and self._secret_store.available:
                cookie = self._secret_store.get(session.credential_ref) or ""
            return WebSessionCredential(token=cookie)
        token = self._environ.get(session.auth_env, "").strip() if session.auth_env else ""
        return WebSessionCredential(token=token)


async def _missing_endpoint_transport(
    credential: WebSessionCredential, messages: tuple[Message, ...], model: str
) -> str:
    del credential, messages, model
    raise RuntimeError("web HTTP endpoint tanımlı değil")


def unconfigured_web_provider(model: str, *, clock: Clock | None = None) -> LlmProvider:
    """Web kimliğini LiteLLM'e göndermek yerine ANLAŞILIR biçimde başarısız ol.

    `chatgpt_web/...` gibi bir kimlik LiteLLM'e giderse kullanıcı "bilinmeyen model"
    hatası görür ve sorunun eksik oturum olduğunu anlamaz.
    """
    return WebProviderAdapter(
        model=model,
        credential=WebSessionCredential(),
        transport=_missing_web_session_transport,
        tool_support=ToolSupport.NONE,
        clock=clock,
    )


async def _missing_web_session_transport(
    credential: WebSessionCredential, messages: tuple[Message, ...], model: str
) -> str:
    del credential, messages
    raise RuntimeError(
        f"not found: {model} için etkin web oturumu yok; Fusion Control Panel'den bağla"
    )


def web_registry_for(config: Config) -> WebSessionRegistry | None:
    if not config.web_sessions:
        return None
    from ..config.keys import environ_snapshot, secret_key

    store = FernetSecretStore(credentials_file(), secret_key=secret_key())
    return WebSessionRegistry(
        config.web_sessions,
        environ=environ_snapshot(),
        secret_store=store,
        trace_dir=config.memory_dir / "web-traces" if config.runtime.web_trace else None,
    )

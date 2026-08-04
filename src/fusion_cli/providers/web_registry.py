"""Web provider registry: custom HTTP sessions and native browser subscriptions."""

from __future__ import annotations

from collections.abc import Callable, Mapping
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
    """Model id -> configured web provider adapter."""

    def __init__(
        self,
        sessions: tuple[WebSessionConfig, ...],
        *,
        environ: Mapping[str, str],
        secret_store: FernetSecretStore | None = None,
    ) -> None:
        self._by_model = {session.model: session for session in sessions if session.enabled}
        self._environ = environ
        self._secret_store = secret_store

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
        credential = self._credential(session)
        if session.transport == "browser":
            transport = build_browser_transport(session)
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
    """Return a clear failing provider instead of sending a web id to LiteLLM."""
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
    )

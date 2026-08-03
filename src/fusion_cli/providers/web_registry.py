"""Web (oturum tabanlı) sağlayıcı kayıt defteri.

`config.web_sessions` tanımlarını ve bir ortam anlık görüntüsünü alır; bir model
kimliği için (varsa) hazır bir `WebProviderAdapter` üretir. Sır yönetimi RULES.md'ye
uyar: token yalnızca `auth_env` ile adı verilen ortam değişkeninden okunur ve tek yerde
(burada, kurulum anında) çözülür; frozen `Config`'te taşınmaz, log'a girmez.

`KeyPoolRegistry` ile aynı desendir: oturum boyunca tek örnek kurulur ve
`build_provider`'a enjekte edilir; factory içindeki `_leaf` model başına buna danışır.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from ..config.models import WebSessionConfig
from ..core.model_capability import ToolSupport
from ..core.protocols import Clock, LlmProvider
from .web_session import WebProviderAdapter, WebSessionCredential, WebTransport
from .web_transport import build_http_transport

if TYPE_CHECKING:  # pragma: no cover - yalnızca tip için
    from ..config.models import Config

#: Endpoint → gerçek I/O yapan transport üreten fabrika. Testte sahtesi enjekte edilir.
TransportFactory = Callable[..., WebTransport]

#: Config'teki metin araç desteği → enum. Bilinmeyen değer güvenli tarafa (NONE) düşer.
_TOOL_SUPPORT = {"none": ToolSupport.NONE, "emulated": ToolSupport.EMULATED}


class WebSessionRegistry:
    """Model kimliği → web sağlayıcı. Tanımsız model için None döner (API yolu sürer)."""

    def __init__(
        self, sessions: tuple[WebSessionConfig, ...], *, environ: Mapping[str, str]
    ) -> None:
        self._by_model = {session.model: session for session in sessions}
        self._environ = environ

    @property
    def is_empty(self) -> bool:
        return not self._by_model

    def build(
        self,
        model: str,
        *,
        clock: Clock | None = None,
        transport_factory: TransportFactory = build_http_transport,
    ) -> LlmProvider | None:
        """Model bir web ucuyla eşleşiyorsa hazır adaptörü kur; değilse None."""
        session = self._by_model.get(model)
        if session is None:
            return None
        credential = self._credential(session)
        transport = transport_factory(session.endpoint)
        return WebProviderAdapter(
            model=session.model,
            credential=credential,
            transport=transport,
            tool_support=_TOOL_SUPPORT.get(session.tool_support, ToolSupport.NONE),
            clock=clock,
        )

    def _credential(self, session: WebSessionConfig) -> WebSessionCredential:
        """Token'ı `auth_env` ile adı verilen ortam değişkeninden çöz (tek yer)."""
        token = self._environ.get(session.auth_env, "").strip() if session.auth_env else ""
        return WebSessionCredential(token=token)


def web_registry_for(config: Config) -> WebSessionRegistry | None:
    """Config'ten web kayıt defteri kur; tanımlı web ucu yoksa None (sıfır ek yük).

    Ortam erişimi config-katmanı fonksiyonu `environ_snapshot` üzerinden yapılır
    (RULES.md: env doğrudan okunmaz). Boş durumda None döner ve `build_provider`
    web yolunu tamamen atlar; mevcut API davranışı birebir korunur.
    """
    if not config.web_sessions:
        return None
    from ..config.keys import environ_snapshot

    return WebSessionRegistry(config.web_sessions, environ=environ_snapshot())

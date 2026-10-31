"""Terminal ve TUI onayında "Her zaman reddet" (P-007): masaüstü kartıyla aynı davranış.

Ölçüldü (31 Ekim): seçenek yalnız masaüstü uygulamasının kartındaydı; TUI ve düz terminal
`never` bilmiyordu, belge ise üçünde de varmış gibi anlatıyordu. Seçilen uygulama
`desktop.denied_apps`'e yazılır ve aynı turda (tur ayarı tur başındaki kopyadır) o uygulamanın
sonraki çağrısı sorulmadan gerekçeli retle kapanır.
"""

from __future__ import annotations

from collections.abc import Callable

from ..config.desktop_denied import with_denied_app
from ..config.models import Config
from ..core.errors import ConfigError
from ..engines.agent.approval import ApprovalAnswer, ApprovalReply, ApprovalRequest
from ..ui import messages

#: Terminalde "Her zaman reddet" sayılan cevaplar (`r <gerekçe>` notu da taşır).
NEVER_WORDS = frozenset({"r", "reddet", "never"})


def offers_never(request: ApprovalRequest) -> bool:
    """Seçenek yalnız uygulama başına masaüstü onayında sunulur (kartla aynı kural)."""
    return request.desktop_target is not None and request.consent_key is not None


class AppDenials:
    """Bir turun "Her zaman reddet" kararları; kalıcı yazımı sahip verir (`persist`)."""

    def __init__(self, persist: Callable[[str], str] | None = None) -> None:
        self._persist = persist
        self._keys: set[str] = set()

    def short_circuit(self, request: ApprovalRequest) -> ApprovalReply | None:
        """Bu turda reddedilen uygulamaya yeni istek: sormadan gerekçeli ret."""
        target = request.desktop_target
        if target is None or target.key not in self._keys:
            return None
        return ApprovalReply(
            ApprovalAnswer.DENY, messages.BILGISAYAR_DENIED_IN_TURN.format(app=target.app)
        )

    def deny(self, request: ApprovalRequest) -> str:
        """Uygulamayı reddet; kullanıcıya gösterilecek metni döndür."""
        target = request.desktop_target
        if target is None:
            return ""
        self._keys.add(target.key)
        if self._persist is None:
            return messages.BILGISAYAR_DENIED_NOT_SAVED.format(app=target.app)
        return self._persist(target.app)


def config_persist(
    current: Callable[[], Config], apply: Callable[[Config], None] | None = None
) -> Callable[[str], str]:
    """`desktop.denied_apps`'e yazan geri çağrı; `apply` canlı yapılandırmayı günceller."""

    def persist(app: str) -> str:
        try:
            updated, text = with_denied_app(current(), app)
        except ConfigError as error:
            return str(error)
        if apply is not None:
            apply(updated)
        return text

    return persist

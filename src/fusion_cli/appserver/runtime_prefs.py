"""Oturumda seçilen motor ve izin modunu kalıcı yapılandırmaya yaz.

Yazma hatası SESSİZCE yutulmaz: çağıran, kullanıcıya seçimin yalnız bu oturumda
geçerli olduğunu söyleyebilsin diye hata metni döner.
"""

from __future__ import annotations

import logging

from ..config.models import Config
from ..config.writer import write_approval_mode, write_engine
from ..engines.agent.approval import ApprovalMode

_LOG = logging.getLogger(__name__)


def persist_engine(config: Config, engine: str) -> str | None:
    """Motor seçimini yaz; başarısızsa kullanıcıya gösterilecek hata metni döner."""
    try:
        write_engine(config, engine)
    except (OSError, ValueError) as error:
        _LOG.warning("Motor seçimi kaydedilemedi: %s", error)
        return f"Motor seçimi kaydedilemedi, yalnız bu oturumda geçerli: {error}"
    return None


def persist_approval(config: Config, mode: ApprovalMode) -> str | None:
    """İzin modunu yaz. `bypass` bilerek yazılmaz (oturumluk), hata sayılmaz."""
    if mode is ApprovalMode.BYPASS:
        return None
    try:
        write_approval_mode(config, mode.value)
    except (OSError, ValueError) as error:
        _LOG.warning("İzin modu kaydedilemedi: %s", error)
        return f"İzin modu kaydedilemedi, yalnız bu oturumda geçerli: {error}"
    return None

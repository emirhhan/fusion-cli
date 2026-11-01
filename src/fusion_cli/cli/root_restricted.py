"""Kök komutta (etkileşimli oturum) `fusion --restricted` (#301).

`-p --restricted` ile aynı sözleşme (`print_restricted.py`): komut ya da kod çalıştıran
araçlar ve WebFetch her turda sunulmaz, dosya araçları çalışma dizinlerine sınırlanır,
kullanıcı/proje/yerel ayar katmanları yüklenmez (yalnız `--settings`), yapılandırmadaki MCP
bağlanmaz ve `bypassPermissions` kullanılamaz: `--settings permissions.defaultMode
bypassPermissions` açılışı reddeder, oturum içinde `/bypass` ya da shift-tab ile seçilen
kip tur başında `auto`ya indirilir.
"""

from __future__ import annotations

from dataclasses import replace

from ..config.models import Config
from ..engines.agent.approval import ApprovalMode
from .print_restricted import (
    RESTRICTED_TOOLS,
    apply_restricted_config,
    check_restricted_mode,
)


def restricted_root_config(config: Config, *, settings_mode: str | None) -> Config:
    """Yapılandırmayı daralt; `--settings` bypass kipi verdiyse `ValueError`."""
    if settings_mode == ApprovalMode.BYPASS.value:
        check_restricted_mode(ApprovalMode.BYPASS)
    if config.runtime.approval_mode == ApprovalMode.BYPASS.value:
        # Kayıtlı kip bypass ise (REPL zaten açılışta `auto`ya indirir) kısıtlı kipte de öyle.
        config = replace(
            config, runtime=replace(config.runtime, approval_mode=ApprovalMode.AUTO.value)
        )
    return apply_restricted_config(config)


def restricted_turn_tools(tools: frozenset[str] | None) -> frozenset[str]:
    """Turda sunulacak araçlar: mevcut kısıt (ör. `--bare`) ile güvenli küme kesişimi."""
    return RESTRICTED_TOOLS if tools is None else tools & RESTRICTED_TOOLS


def guard_turn_mode(state: object) -> None:
    """Kısıtlı oturumda bypass seçildiyse turdan önce `auto`ya indir."""
    if getattr(state, "approval", None) is ApprovalMode.BYPASS:
        state.approval = ApprovalMode.AUTO  # type: ignore[attr-defined]

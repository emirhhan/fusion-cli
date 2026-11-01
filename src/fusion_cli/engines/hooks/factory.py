"""Yapılandırmadan kanca oturumu kurma (`open_hook_session`)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from ...config.hooks import DEFAULT_HOOK_TIMEOUT_S, load_hooks
from ...config.models import Config, RuntimeConfig, mcp_secret_env_names
from ...core.hooks.events import HookSet
from .session import HookSession
from .terminal import tty_writer
from .transcript import HOOK_TRANSCRIPT_DIR

NOTICE_ALLOW_PRIVATE = (
    "runtime.hook_http_allow_private kullanımdan kalktı; bu sürümde `false` hâlâ uygulanıyor "
    "(http kancası iç ağ adresine gitmez). Kısıtı ayar dosyasında `allowedHttpHookUrls` ile "
    "koyun."
)
NOTICE_TIMEOUT = (
    "runtime.hook_timeout_s kullanımdan kalktı; bu sürümde süresi yazılmamış kancaya hâlâ "
    "{value:g} sn uygulanıyor. Kanca başına `timeout` yazın (Claude varsayılanı 600 sn)."
)


def deprecated_runtime_notices(runtime: RuntimeConfig) -> tuple[str, ...]:
    """Kullanımdan kalkan anahtar varsayılandan farklıysa (kullanıcı yazmış) uyarı."""
    notices: list[str] = []
    if getattr(runtime, "hook_http_allow_private", True) is False:
        notices.append(NOTICE_ALLOW_PRIVATE)
    timeout = legacy_timeout_s(runtime)
    if timeout != DEFAULT_HOOK_TIMEOUT_S:
        notices.append(NOTICE_TIMEOUT.format(value=timeout))
    return tuple(notices)


def legacy_timeout_s(runtime: RuntimeConfig) -> float:
    value = getattr(runtime, "hook_timeout_s", DEFAULT_HOOK_TIMEOUT_S)
    return float(value) if isinstance(value, int | float) and value > 0 else DEFAULT_HOOK_TIMEOUT_S


def open_hook_session(
    root: Path,
    config: Config | Callable[[], Config],
    *,
    session_id: str | None = None,
    permission_mode: Callable[[], str] | None = None,
    home: Path | None = None,
    source: str = "startup",
    transcript_dir: Path | None = None,
    interactive: bool = True,
) -> HookSession:
    """Yapılandırmaya göre kanca oturumu kur (dosyalar ilk kullanımda okunur).

    `config` çağrılabilirse her yüklemede okunur: `/config set runtime.hooks_enabled false`
    açık oturumda bir sonraki turda etkili olur. Ölçüldü (31 Ekim): `runtime` kapanışla
    yakalandığı için REPL yeniden başlatılana kadar kancalar çalışmaya devam ediyordu.
    """

    def _config() -> Config:
        return config() if callable(config) else config

    def _load() -> HookSet:
        runtime = _config().runtime
        hooks = load_hooks(
            session.root,
            enabled=runtime.hooks_enabled,
            include_claude=runtime.claude_hooks,
            default_timeout_s=legacy_timeout_s(runtime),
            home=home,
            interactive=interactive,
            pinned=session.pinned_settings,
        )
        notices = deprecated_runtime_notices(runtime)
        return replace(hooks, notices=(*hooks.notices, *notices)) if notices else hooks

    session = HookSession(
        root=root,
        loader=_load,
        permission_mode=permission_mode,
        next_source=source,
        transcript_dir=transcript_dir or _config().memory_dir / HOOK_TRANSCRIPT_DIR,
        hidden_env=lambda: mcp_secret_env_names(_config().mcp_servers),
        http_allow_private=lambda: (
            getattr(_config().runtime, "hook_http_allow_private", True) is not False
        ),
        project_dir=root,
        effort=lambda: str(getattr(_config().runtime.reasoning_effort, "value", "auto")),
        model=lambda: str(getattr(getattr(_config(), "agent", None), "model", "") or ""),
        interactive=interactive,
        terminal_writer=tty_writer() if interactive else None,
        home=home,
    )
    if session_id:
        session.session_id = session_id
        session.conversation_id = session_id
    return session

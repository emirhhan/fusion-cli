"""Yapılandırmadan kanca oturumu kurma (`open_hook_session`)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ...config.hooks import load_hooks
from ...config.models import Config, mcp_secret_env_names
from ...core.hooks.events import HookSet
from .session import HookSession
from .terminal import tty_writer
from .transcript import HOOK_TRANSCRIPT_DIR


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
        return load_hooks(
            session.root,
            enabled=runtime.hooks_enabled,
            include_claude=runtime.claude_hooks,
            home=home,
            interactive=interactive,
        )

    session = HookSession(
        root=root,
        loader=_load,
        permission_mode=permission_mode,
        next_source=source,
        transcript_dir=transcript_dir or _config().memory_dir / HOOK_TRANSCRIPT_DIR,
        hidden_env=lambda: mcp_secret_env_names(_config().mcp_servers),
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

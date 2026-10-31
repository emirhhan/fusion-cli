"""Oturum başına kanca yürütücüsü (P-009): olay → eşleşen komutlar → birleşik karar.

Her yüzey (REPL, masaüstü oturumu, tek atışlık `fusion agent`) bir `HookSession` tutar ve
`AgentDeps.hooks` ile motora verir. Tanımlar her kök turun başında yeniden okunur
(`refresh`): masaüstünde "Bu projeye güven" ya da dosya düzenlemesi bir sonraki turda
etkili olur; tur ORTASINDA değişmez.

`SessionStart` ilk kök turda bir kez tetiklenir (ek bağlamı o tura eklenir); `SessionEnd`
yalnız başlamış oturumda, kapanışta bir kez. Sohbet sıfırlanınca ya da değişince
(`restart`: `/reset`, `/resume`, masaüstünde başka sohbet) eski oturum `SessionEnd` alır ve
yenisi bir sonraki kök turda `SessionStart` (`source: clear|resume`) ile açılır. Kök değişimi
(worktree) oturumu YENİLEMEZ: `root` güncellenir, tanımlar yeni kökten okunur.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ...config.hooks import DISABLE_ALL_KEY, hook_environment, load_hooks
from ...config.models import Config
from ...core.hooks.decision import merge_verdicts, verdict_from_run
from ...core.hooks.events import HookEvent, HookSet, HookVerdict
from .runner import run_hook

#: Boş karar: hiçbir kanca eşleşmedi.
NO_VERDICT = HookVerdict()


@dataclass(slots=True)
class HookSession:
    """Bir oturumun kancaları ve yaşam döngüsü durumu."""

    root: Path
    loader: Callable[[], HookSet]
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    #: Anlık onay kipinin adı (Claude'un `permission_mode` alanı); verilmezse alan yazılmaz.
    permission_mode: Callable[[], str] | None = None
    hooks: HookSet = field(default_factory=HookSet)
    started: bool = False
    ended: bool = False
    #: Dosyadaki `disableAllHooks` kapatması kullanıcıya bildirildi mi? (oturumda bir kez)
    disabled_notified: bool = False
    #: Bir sonraki `SessionStart`'ın kaynağı (`startup`, `resume`, `clear`).
    next_source: str = "startup"
    _loaded: bool = False
    #: `restart` sonrası henüz gönderilmemiş eski oturum `SessionEnd`'i: (kimlik, neden).
    _pending_end: tuple[str, str] | None = None

    def refresh(self) -> HookSet:
        """Tanımları yeniden oku (kök tur başı)."""
        self.hooks = self.loader()
        self._loaded = True
        return self.hooks

    def disabled_notice(self) -> str | None:
        """Bir dosya (`disableAllHooks`) kancaları kapattıysa gerekçe; oturumda yalnız bir kez.

        Ayar ya da ortam değişkeniyle kapatma kullanıcının kendi kararıdır, bildirilmez.
        """
        reason = self.current().disabled_reason
        if self.disabled_notified or reason is None or not reason.startswith(DISABLE_ALL_KEY):
            return None
        self.disabled_notified = True
        return reason

    def current(self) -> HookSet:
        return self.hooks if self._loaded else self.refresh()

    def has(self, event: HookEvent) -> bool:
        return any(command.event is event for command in self.current().commands)

    async def emit(
        self,
        event: HookEvent,
        *,
        subjects: tuple[str, ...] = (),
        fields: Mapping[str, object] | None = None,
    ) -> HookVerdict:
        """Olayın eşleşen komutlarını paralel çalıştır ve kararlarını birleştir."""
        commands = self.current().for_event(event, subjects)
        if not commands:
            return NO_VERDICT
        payload = self._payload(event, fields or {})
        environment = hook_environment(self.root)
        runs = await asyncio.gather(
            *(
                run_hook(command, payload, cwd=self.root, environment=environment)
                for command in commands
            )
        )
        return merge_verdicts(verdict_from_run(event, run) for run in runs)

    def restart(self, source: str, *, reason: str, session_id: str | None = None) -> None:
        """Sohbet sıfırlandı/değişti: eski oturum `SessionEnd(reason)` alır, yenisi açılır.

        Çağıranlar eşzamanlıdır (`/reset`); `SessionEnd` bir sonraki `start`/`end`'de, eski
        oturum kimliğiyle gönderilir. Başlamamış oturumda kapanış yoktur.
        """
        if self.started and not self.ended:
            self._pending_end = (self.session_id, reason)
        self.started = False
        self.ended = False
        self.session_id = session_id or uuid.uuid4().hex
        self.next_source = source

    async def _flush_pending_end(self) -> HookVerdict:
        pending, self._pending_end = self._pending_end, None
        if pending is None:
            return NO_VERDICT
        old_id, reason = pending
        return await self.emit(
            HookEvent.SESSION_END,
            subjects=(reason,),
            fields={"reason": reason, "session_id": old_id},
        )

    async def start(self, source: str | None = None) -> HookVerdict:
        """`SessionStart`: ilk çağrıda bir kez; sonrakiler boş karar."""
        await self._flush_pending_end()
        if self.started:
            return NO_VERDICT
        self.started = True
        source = source or self.next_source
        return await self.emit(
            HookEvent.SESSION_START, subjects=(source,), fields={"source": source}
        )

    async def end(self, reason: str = "other") -> HookVerdict:
        """`SessionEnd`: yalnız başlamış oturumda bir kez."""
        await self._flush_pending_end()
        if not self.started or self.ended:
            return NO_VERDICT
        self.ended = True
        return await self.emit(HookEvent.SESSION_END, subjects=(reason,), fields={"reason": reason})

    async def notify(self, kind: str, message: str) -> HookVerdict:
        """`Notification`: kullanıcının dikkati gerektiğinde (izin istemi vb.)."""
        return await self.emit(
            HookEvent.NOTIFICATION,
            subjects=(kind,),
            fields={"notification_type": kind, "message": message},
        )

    async def pre_compact(self, trigger: str) -> HookVerdict:
        """`PreCompact`: bağlam özetlenmeden önce (`manual` = /compact, `auto` = eşik)."""
        return await self.emit(
            HookEvent.PRE_COMPACT,
            subjects=(trigger,),
            fields={"trigger": trigger, "custom_instructions": ""},
        )

    def _payload(self, event: HookEvent, fields: Mapping[str, object]) -> dict[str, object]:
        payload: dict[str, object] = {
            "session_id": self.session_id,
            "cwd": str(self.root),
            "hook_event_name": event.value,
        }
        if self.permission_mode is not None:
            payload["permission_mode"] = self.permission_mode()
        return {**payload, **fields}


def open_hook_session(
    root: Path,
    config: Config | Callable[[], Config],
    *,
    session_id: str | None = None,
    permission_mode: Callable[[], str] | None = None,
    home: Path | None = None,
    source: str = "startup",
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
            default_timeout_s=runtime.hook_timeout_s,
            home=home,
        )

    session = HookSession(
        root=root, loader=_load, permission_mode=permission_mode, next_source=source
    )
    if session_id:
        session.session_id = session_id
    return session

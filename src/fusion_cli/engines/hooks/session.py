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
from ...config.models import Config, mcp_secret_env_names
from ...core.hooks.decision import merge_verdicts, verdict_from_run
from ...core.hooks.events import HookEvent, HookSet, HookVerdict
from .runner import run_hook
from .transcript import HOOK_TRANSCRIPT_DIR, HookTranscript, transcript_for

#: Boş karar: hiçbir kanca eşleşmedi.
NO_VERDICT = HookVerdict()
#: Özetleme sonrası `SessionStart` kaynağı (Claude Code ile aynı).
COMPACT_SOURCE = "compact"


@dataclass(slots=True)
class HookSession:
    """Bir oturumun kancaları ve yaşam döngüsü durumu."""

    root: Path
    loader: Callable[[], HookSet]
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    #: Oturumun bağlı olduğu sohbet kimliği. `/reset` sohbeti korur ama `session_id`'yi
    #: yeniler (Claude `/clear` gibi); sohbet değişimi bu alanla ayırt edilir.
    conversation_id: str = ""
    #: Anlık onay kipinin adı (Claude'un `permission_mode` alanı); verilmezse alan yazılmaz.
    permission_mode: Callable[[], str] | None = None
    hooks: HookSet = field(default_factory=HookSet)
    started: bool = False
    ended: bool = False
    #: Dosyadaki `disableAllHooks` kapatması kullanıcıya bildirildi mi? (oturumda bir kez)
    disabled_notified: bool = False
    #: Bir sonraki `SessionStart`'ın kaynağı (`startup`, `resume`, `clear`).
    next_source: str = "startup"
    #: `transcript_path` dökümlerinin klasörü; `None` = alan yazılmaz (alt sistem testleri).
    transcript_dir: Path | None = None
    #: Kanca sürecine VERİLMEYEN ortam adları (MCP sırları); her çağrıda taze okunur.
    hidden_env: Callable[[], frozenset[str]] | None = None
    #: `http` kancası iç ağ adresine gidebilir mi? (`runtime.hook_http_allow_private`)
    http_allow_private: Callable[[], bool] | None = None
    _loaded: bool = False
    #: `restart` sonrası henüz gönderilmemiş eski oturum `SessionEnd`'i: (kimlik, neden).
    _pending_end: tuple[str, str] | None = None
    #: Eşzamanlı koddan (slash komutu) kuyruğa alınmış olaylar; `flush_deferred` gönderir.
    _deferred: list[tuple[HookEvent, tuple[str, ...], dict[str, object]]] = field(
        default_factory=list
    )

    def transcript(self, session_id: str | None = None) -> HookTranscript | None:
        if self.transcript_dir is None:
            return None
        return transcript_for(self.transcript_dir, session_id or self.session_id)

    def record(self, role: str, text: str) -> None:
        """Dökümüne istem/cevap ekle; tanımlı kanca yoksa hiçbir şey yazılmaz."""
        transcript = self.transcript()
        if transcript is not None and text.strip() and self.current().commands:
            transcript.append(role, text, self.session_id)

    def record_tool_use(
        self, name: str, tool_input: Mapping[str, object], tool_use_id: str
    ) -> None:
        transcript = self._recording()
        if transcript is not None:
            transcript.append_tool_use(name, tool_input, tool_use_id, self.session_id)

    def record_tool_result(self, tool_use_id: str, output: str, *, is_error: bool) -> None:
        transcript = self._recording()
        if transcript is not None:
            transcript.append_tool_result(tool_use_id, output, self.session_id, is_error=is_error)

    def _recording(self) -> HookTranscript | None:
        """Döküm yalnız tanımlı kanca varken yazılır."""
        transcript = self.transcript()
        return transcript if transcript is not None and self.current().commands else None

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
        hidden = self.hidden_env() if self.hidden_env is not None else frozenset()
        environment = hook_environment(self.root, hidden)
        private = self.http_allow_private() if self.http_allow_private is not None else False
        runs = await asyncio.gather(
            *(
                run_hook(
                    command,
                    payload,
                    cwd=self.root,
                    environment=environment,
                    allow_private=private,
                )
                for command in commands
            )
        )
        return merge_verdicts(verdict_from_run(event, run) for run in runs)

    def defer(
        self,
        event: HookEvent,
        *,
        subjects: tuple[str, ...] = (),
        fields: Mapping[str, object] | None = None,
    ) -> None:
        """Olayı eşzamanlı koddan kuyruğa al (`/cd` işleyicisi); çağıran yüzey `flush_deferred`."""
        self._deferred.append((event, subjects, dict(fields or {})))

    def defer_cwd_changed(self, old: Path, new: Path) -> None:
        """`CwdChanged` (Claude Code ile aynı yük): `/cd` oturum kökünü değiştirdi."""
        self.defer(HookEvent.CWD_CHANGED, fields={"old_cwd": str(old), "new_cwd": str(new)})

    def defer_directory_added(self, directory: Path, source: str = "slash_command") -> None:
        """`DirectoryAdded` (Claude Code ile aynı yük, #213): eşleştirici kaynağa bakar."""
        self.defer(
            HookEvent.DIRECTORY_ADDED,
            subjects=(source,),
            fields={"directory": str(directory), "source": source},
        )

    def drop_deferred(self) -> None:
        """Kuyruktaki olayları gönderilmeden at (değişiklik geri alındı)."""
        self._deferred.clear()

    async def flush_deferred(self) -> HookVerdict:
        """Kuyruktaki olayları sırayla gönder; kararları birleştir (engelleyemezler)."""
        pending, self._deferred = self._deferred, []
        verdicts = [
            await self.emit(event, subjects=subjects, fields=fields)
            for event, subjects, fields in pending
        ]
        return merge_verdicts(verdicts) if verdicts else NO_VERDICT

    def restart(
        self,
        source: str,
        *,
        reason: str,
        session_id: str | None = None,
        conversation_id: str | None = None,
    ) -> None:
        """Sohbet sıfırlandı/değişti: eski oturum `SessionEnd(reason)` alır, yenisi açılır.

        Çağıranlar eşzamanlıdır (`/reset`); `SessionEnd` bir sonraki `start`/`end`'de, eski
        oturum kimliğiyle gönderilir. Başlamamış oturumda kapanış yoktur. `session_id`
        verilmezse yeni kimlik üretilir. Ölçüldü (1 Kasım): `/reset` sohbet kimliğini yeni
        oturum kimliği olarak veriyordu; SessionEnd(clear) ile SessionStart(clear) aynı
        `session_id`'yi taşıyor, betikler iki oturumu ayıramıyordu.
        """
        if self.started and not self.ended:
            self._pending_end = (self.session_id, reason)
        self.started = False
        self.ended = False
        self.session_id = session_id or uuid.uuid4().hex
        if conversation_id is not None:
            self.conversation_id = conversation_id
        self.next_source = source

    async def _flush_pending_end(self) -> HookVerdict:
        pending, self._pending_end = self._pending_end, None
        if pending is None:
            return NO_VERDICT
        old_id, reason = pending
        fields: dict[str, object] = {"reason": reason, "session_id": old_id}
        old = self.transcript(old_id)
        if old is not None:
            fields["transcript_path"] = str(old.ensure())
        verdict = await self.emit(HookEvent.SESSION_END, subjects=(reason,), fields=fields)
        if old is not None:
            old.remove()
        return verdict

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
        verdict = await self.emit(
            HookEvent.SESSION_END, subjects=(reason,), fields={"reason": reason}
        )
        transcript = self.transcript()
        if transcript is not None:
            transcript.remove()
        return verdict

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

    async def compacted(self) -> HookVerdict:
        """`SessionStart(source: compact)`: bağlam özetlendi (oturum yaşam döngüsü değişmez)."""
        return await self.emit(
            HookEvent.SESSION_START, subjects=(COMPACT_SOURCE,), fields={"source": COMPACT_SOURCE}
        )

    def _payload(self, event: HookEvent, fields: Mapping[str, object]) -> dict[str, object]:
        payload: dict[str, object] = {
            "session_id": self.session_id,
            "cwd": str(self.root),
            "hook_event_name": event.value,
        }
        if self.permission_mode is not None:
            payload["permission_mode"] = self.permission_mode()
        transcript = self.transcript()
        if transcript is not None and "transcript_path" not in fields:
            payload["transcript_path"] = str(transcript.ensure())
        return {**payload, **fields}


def open_hook_session(
    root: Path,
    config: Config | Callable[[], Config],
    *,
    session_id: str | None = None,
    permission_mode: Callable[[], str] | None = None,
    home: Path | None = None,
    source: str = "startup",
    transcript_dir: Path | None = None,
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
        root=root,
        loader=_load,
        permission_mode=permission_mode,
        next_source=source,
        transcript_dir=transcript_dir or _config().memory_dir / HOOK_TRANSCRIPT_DIR,
        hidden_env=lambda: mcp_secret_env_names(_config().mcp_servers),
        http_allow_private=lambda: bool(
            getattr(_config().runtime, "hook_http_allow_private", False)
        ),
    )
    if session_id:
        session.session_id = session_id
        session.conversation_id = session_id
    return session

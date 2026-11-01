"""Oturum başına kanca yürütücüsü (P-009): olay → eşleşen komutlar → birleşik karar.

Her yüzey (REPL, masaüstü oturumu, tek atışlık `fusion agent`) bir `HookSession` tutar ve
`AgentDeps.hooks` ile motora verir. Tanımlar her kök turun başında yeniden okunur
(`refresh`): masaüstünde "Bu projeye güven" ya da dosya düzenlemesi bir sonraki turda
etkili olur; tur ORTASINDA değişmez.

`SessionStart` yüzey oturumu açınca (`open`) ya da en geç ilk kök turda bir kez tetiklenir;
bağlamı konuşmanın başına, ilk istemden önce eklenir. `SessionEnd` yalnız başlamış
oturumda, kapanışta bir kez. Sohbet sıfırlanınca ya da değişince
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

from ...config.hooks import DISABLE_ALL_KEY, hook_environment
from ...core.hooks.decision import merge_verdicts, verdict_from_run
from ...core.hooks.events import HookCommand, HookEvent, HookSet, HookVerdict
from . import dispatch
from .overflow import spill_verdict
from .runner import run_hook
from .transcript import HookTranscript, transcript_for

#: Boş karar: hiçbir kanca eşleşmedi.
NO_VERDICT = HookVerdict()
#: Özetleme sonrası `SessionStart` kaynağı (Claude Code ile aynı).
COMPACT_SOURCE = "compact"
#: Fusion onay kipi → Claude `permission_mode` değeri (Manual kip `default` gelir).
_CLAUDE_MODES = {
    "security": "default",
    "edits": "acceptEdits",
    "bypass": "bypassPermissions",
    "auto": "auto",
    "plan": "plan",
    "dontAsk": "dontAsk",
}


def claude_permission_mode(mode: str) -> str:
    return _CLAUDE_MODES.get(mode, mode)


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
    #: Oturumun BAŞLADIĞI proje kökü: `CLAUDE_PROJECT_DIR` worktree/`/cd` ile değişmez.
    project_dir: Path | None = None
    #: Anlık reasoning yoğunluğu (`effort.level`, `CLAUDE_EFFORT`); verilmezse yazılmaz.
    effort: Callable[[], str] | None = None
    #: Etkileşimli oturum mu? (`-p`'de `defer`, terminal dizisi ve güven kuralı farklı.)
    interactive: bool = True
    #: Tur kimliği (`prompt_id`): her kök istemde yenilenir.
    prompt_id: str = ""
    #: Kancanın verdiği oturum başlığı (`sessionTitle`).
    session_title: str = ""
    #: PreToolUse `additionalContext`: çağrı kimliği → araç sonucuna eklenecek hatırlatma.
    pending_tool_context: dict[str, str] = field(default_factory=dict)
    #: Çağrı kimliği → başlama anı (`duration_ms`).
    tool_started: dict[str, float] = field(default_factory=dict)
    #: Çağrı kimliği → yazılan dosya çalışmadan önce var mıydı? (Write `type`)
    tool_existed: dict[str, bool] = field(default_factory=dict)
    #: `asyncRewake` kancalarının bir sonraki tura bıraktığı metinler.
    rewake_notes: list[str] = field(default_factory=list)
    _loaded: bool = False
    #: Açılışta çalışmış SessionStart'ın henüz istemle birleşmemiş bağlamı.
    _start_context: str = ""
    _notices_shown: bool = False
    _background: set[asyncio.Task[None]] = field(default_factory=set)
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

    def take_notices(self) -> tuple[str, ...]:
        """Katman uyarıları (kullanımdan kalkan dosya vb.); oturumda bir kez."""
        if self._notices_shown:
            return ()
        self._notices_shown = True
        return self.current().notices

    def new_prompt(self) -> str:
        """Yeni kök istem: `prompt_id` yenilenir."""
        self.prompt_id = uuid.uuid4().hex
        return self.prompt_id

    def take_start_context(self) -> str:
        context, self._start_context = self._start_context, ""
        return context

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
        target: tuple[str, Mapping[str, object]] | None = None,
    ) -> HookVerdict:
        """Olayın eşleşen komutlarını paralel çalıştır ve kararlarını birleştir.

        `target` (Fusion araç adı, argümanlar) `if` koşulunun değerlendirildiği çağrıdır.
        """
        root = self.project_dir or self.root
        commands = tuple(
            command
            for command in self.current().for_event(event, subjects)
            if dispatch.condition_allows(command, event, target, self.root)
        )
        if not commands:
            return NO_VERDICT
        payload = self._payload(event, fields or {})
        hidden = self.hidden_env() if self.hidden_env is not None else frozenset()
        environment = hook_environment(root, hidden, self._extra_env())
        private = self.http_allow_private() if self.http_allow_private is not None else True
        subject = subjects[0] if subjects else ""
        timed = dispatch.with_event_timeout(commands, event)
        for command in timed:
            if dispatch.is_background(command):
                self._run_background(event, command, payload, environment, private)
        foreground = [command for command in timed if not dispatch.is_background(command)]
        runs = await asyncio.gather(
            *(
                run_hook(
                    command, payload, cwd=self.root, environment=environment, allow_private=private
                )
                for command in foreground
            )
        )
        verdicts = [
            dispatch.apply_on_failure(event, run, verdict_from_run(event, run, subject))
            for run in runs
        ]
        return spill_verdict(merge_verdicts(verdicts), self._output_dir())

    def _run_background(
        self,
        event: HookEvent,
        command: HookCommand,
        payload: Mapping[str, object],
        environment: Mapping[str, str],
        private: bool,
    ) -> None:
        """`async`/`asyncRewake`: karar beklenmez; rewake çıkış 2'yi sonraki tura bırakır."""

        async def _run() -> None:
            run = await run_hook(
                command, payload, cwd=self.root, environment=environment, allow_private=private
            )
            text = dispatch.rewake_text(run)
            if text:
                self.rewake_notes.append(f"{event.value} hook (async): {text}")

        task = asyncio.get_running_loop().create_task(_run())
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    def take_rewake_notes(self) -> tuple[str, ...]:
        notes, self.rewake_notes = tuple(self.rewake_notes), []
        return notes

    def _output_dir(self) -> Path | None:
        if self.transcript_dir is None:
            return None
        return self.transcript_dir / f"{self.session_id}-hook-output"

    def _extra_env(self) -> dict[str, str]:
        if self.effort is None:
            return {}
        return {"CLAUDE_EFFORT": self.effort()}

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

    async def open(self) -> HookVerdict:
        """Yüzey oturumu açtı: SessionStart hemen (ilk istem beklenmez); bağlam ilk isteme."""
        from ..agent.hook_text import context_reminder

        verdict = await self.start()
        if verdict.context_text:
            self._start_context = context_reminder(HookEvent.SESSION_START, verdict.context_text)
        if verdict.session_title:
            self.session_title = verdict.session_title
        return verdict

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

    async def notify(self, kind: str, message: str, *, title: str = "") -> HookVerdict:
        """`Notification`: kullanıcının dikkati gerektiğinde (izin istemi vb.)."""
        fields: dict[str, object] = {"notification_type": kind, "message": message}
        if title:
            fields["title"] = title
        return await self.emit(HookEvent.NOTIFICATION, subjects=(kind,), fields=fields)

    async def pre_compact(self, trigger: str, instructions: str | None = None) -> HookVerdict:
        """`PreCompact`: özetlemeden önce (`manual` = /compact, `auto` = eşik); engelleyebilir.

        `custom_instructions`: elle `/compact <metin>`'de metin, yoksa ve `auto`'da `null`.
        """
        text = instructions.strip() if trigger == "manual" and instructions else None
        return await self.emit(
            HookEvent.PRE_COMPACT,
            subjects=(trigger,),
            fields={"trigger": trigger, "custom_instructions": text or None},
        )

    async def post_compact(self, trigger: str, summary: str) -> HookVerdict:
        """`PostCompact`: özetleme bitti (`compact_summary`)."""
        return await self.emit(
            HookEvent.POST_COMPACT,
            subjects=(trigger,),
            fields={"trigger": trigger, "compact_summary": summary},
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
        if self.prompt_id:
            payload["prompt_id"] = self.prompt_id
        if self.permission_mode is not None:
            payload["permission_mode"] = claude_permission_mode(self.permission_mode())
        if self.effort is not None:
            payload["effort"] = {"level": self.effort()}
        transcript = self.transcript()
        if transcript is not None and "transcript_path" not in fields:
            payload["transcript_path"] = str(transcript.ensure())
        return {**payload, **fields}


# Geriye uyum: kurucu ayrı modülde (dosya boyu sınırı); eski içe aktarmalar çalışır.
from .factory import open_hook_session  # noqa: E402

__all__ = ["HookSession", "claude_permission_mode", "open_hook_session"]

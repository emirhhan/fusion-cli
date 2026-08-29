"""Oturum ömrü: istekleri karşılar, turu çalıştırır, kapanışı düzenler.

Bir süreç BİR oturum yürütür. Uygulama ikinci bir sohbet istiyorsa ikinci bir
süreç başlatır; böylece paylaşılan durum, kilit ve sahiplik sorunları hiç
doğmaz ve bir oturumun çökmesi diğerini etkilemez.

`self._state` (bir `ReplState`) TEK doğru durum kaynağıdır: yapılandırma, onay
modu, motor ve sohbet geçmişi burada yaşar. Komut akışları (`/model`,
`/security`, `/plan`…) `state.config`/`state.approval`'i DEĞİŞTİRİR; bu yüzden
tur çalıştırma ve durum bildirimi HER ZAMAN `self._state` üzerinden okur —
ayrı bir kopya tutulursa (`self._config` gibi) komutlar "uygulandı" der ama
sonraki tur eski değerle koşar (bkz. `docs/superpowers/sdd/final-fix-report.md`
C1/C4).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..cli.repl.commands import build_registry
from ..cli.repl.state import Engine, ReplState
from ..config.credentials import FernetSecretStore
from ..config.keys import secret_key
from ..config.loader import load_config
from ..config.models import Config
from ..config.paths import credentials_file
from ..core.health import HealthRegistry
from ..engines.agent.approval import ApprovalMode
from ..memory.factory import build_memory
from ..ui import messages
from .bridges import PendingQuestions, ProtocolPrompter, ProtocolSink, Writer
from .commands import command_choices, list_commands, run_command
from .history import PreparedResume, list_sessions, list_sources, prepare_resume, preview_session
from .processes import ProcessManager
from .protocol import Reply, Request, encode_result
from .workspace import (
    WorkspaceJournal,
    list_changes,
    list_entries,
    read_entry,
    undo_entry,
    workspace_status,
    write_entry,
)


def _build_health(config: Config) -> HealthRegistry:
    """Oturum için sağlık kaydını yapılandırma eşiklerinden kur.

    `cli/repl/loop.py::_build_health` ile aynı mantık — terminal REPL'i
    kurduğu gibi appserver da kurar, aksi halde `/health` her zaman boş
    döner ve sağlayıcı circuit breaker'ı turlar arasında hiç yaşamaz.
    """
    runtime = config.runtime
    return HealthRegistry(
        failure_threshold=runtime.circuit_failure_threshold,
        cooldown_s=runtime.circuit_cooldown_s,
        alpha=runtime.reliability_alpha,
    )


class AppSession:
    """Uygulamanın sürdüğü tek oturum."""

    def __init__(self, writer: Writer, *, root: Path, home: Path) -> None:
        self._writer = writer
        self._root = root
        self._home = home
        config = load_config()
        self._secret_store = FernetSecretStore(credentials_file(), secret_key=secret_key())
        self.pending = PendingQuestions()
        self._registry = build_registry(home)
        self._state = ReplState(
            config=config,
            memory=build_memory(config, root=root),
            root=root,
            home=home,
            health=_build_health(config),
        )
        self._workspace_journal = WorkspaceJournal()
        self._processes = ProcessManager(self._state.root, writer)
        self._turn: asyncio.Task[Any] | None = None

    async def handle(self, request: Request) -> None:
        """İsteği çalıştır ve sonucunu yaz. İstisna sızdırmaz."""
        try:
            data = await self._dispatch(request)
        except Exception as error:  # istek sınırı: süreç çökmemeli
            data = {"ok": False, "metin": str(error)}
        self._writer(encode_result(request.id, data))

    async def _dispatch(self, request: Request) -> dict[str, Any]:
        if request.name == "oturum.baslat":
            return self._start_session(request.data)
        if request.name == "oturum.durum":
            return self._status()
        if request.name == "gecmis.kaynaklar":
            return list_sources(self._home)
        if request.name == "gecmis.oturumlar":
            return list_sessions(self._home, self._state.root, request.data)
        if request.name == "gecmis.onizle":
            return preview_session(self._home, request.data)
        if request.name == "gecmis.surdur":
            prepared = prepare_resume(self._home, self._state.root, request.data)
            if isinstance(prepared, PreparedResume):
                self._state.pending_digest = prepared.digest
                return prepared.payload
            return prepared
        if request.name == "proje.durum":
            return workspace_status(self._state.root)
        if request.name == "proje.listele":
            return list_entries(self._state.root, request.data)
        if request.name == "proje.oku":
            return read_entry(self._state.root, request.data)
        if request.name == "proje.yaz":
            return write_entry(self._state.root, request.data, self._workspace_journal)
        if request.name == "proje.degisiklikler":
            return list_changes(self._state.root, self._workspace_journal)
        if request.name == "proje.geri_al":
            return undo_entry(self._state.root, request.data, self._workspace_journal)
        if request.name == "surec.baslat":
            return await self._processes.start(request.data)
        if request.name == "surec.yaz":
            return await self._processes.write(request.data)
        if request.name == "surec.listele":
            return self._processes.list()
        if request.name == "surec.kes":
            return await self._processes.stop(request.data)
        if request.name == "komut.listele":
            return {"ok": True, "komutlar": list_commands(self._registry)}
        if request.name == "komut.calistir":
            return self._run_command(request.data)
        if request.name == "komut.secenekler":
            return self._command_options(request.data)
        if request.name == "tur.calistir":
            return await self._run_turn(str(request.data.get("gorev", "")))
        if request.name == "tur.kes":
            return self._cancel_turn()
        return {"ok": False, "metin": messages.APP_UNKNOWN_REQUEST.format(name=request.name)}

    def _start_session(self, data: dict[str, Any]) -> dict[str, Any]:
        """`oturum.baslat`: kök dizin, ev dizini, onay modu ve motoru kurar.

        Tüm alanlar opsiyoneldir; verilmeyen alan mevcut değerinde kalır. Süreç
        `fusion app` çağrısında zaten kök/ev dizinini alır (bkz. `cli/app.py`);
        bu istek uygulamanın onay modunu ve motoru PROTOKOL üzerinden açıkça
        seçebilmesi içindir — önceden yalnız AUTO'ya çivili başlıyordu.
        """
        root_value = data.get("kok")
        if isinstance(root_value, str) and root_value:
            self._root = Path(root_value)
            self._state.root = self._root
            self._workspace_journal.clear()
            self._processes.update_root(self._root)
        home_value = data.get("ev")
        if isinstance(home_value, str) and home_value:
            self._home = Path(home_value)
            self._state.home = self._home
        mode_error = self._apply_mode(data.get("mod"))
        if mode_error is not None:
            return mode_error
        engine_error = self._apply_engine(data.get("motor"))
        if engine_error is not None:
            return engine_error
        return self._status()

    def _apply_mode(self, value: str | None) -> dict[str, Any] | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            self._state.approval = ApprovalMode(value)
        except ValueError:
            valid = ", ".join(mode.value for mode in ApprovalMode)
            return {
                "ok": False,
                "metin": messages.RUN_UNKNOWN_MODE.format(given=value, valid=valid),
            }
        return None

    def _apply_engine(self, value: str | None) -> dict[str, Any] | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            self._state.engine = Engine(value)
        except ValueError:
            valid = ", ".join(engine.value for engine in Engine)
            return {
                "ok": False,
                "metin": messages.RUN_UNKNOWN_ENGINE.format(given=value, valid=valid),
            }
        return None

    def _status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "kok": str(self._state.root),
            "model": self._state.config.agent.model,
            "mod": self._state.approval.value,
            "motor": self._state.engine.value,
        }

    def _run_command(self, data: dict[str, Any]) -> dict[str, Any]:
        """`run_command` sonucu tel-hazır — olduğu gibi geri gönder."""
        name = str(data.get("ad", ""))
        argument = str(data.get("arguman", ""))
        return run_command(
            self._registry, self._state, name, argument, secret_store=self._secret_store
        )

    def _command_options(self, data: dict[str, Any]) -> dict[str, Any]:
        """Sıradaki seçici/metin adımını döndür; yoksa `ok: False`."""
        name = str(data.get("ad", ""))
        argument = str(data.get("arguman", ""))
        payload = command_choices(self._state, name, argument)
        if payload is None:
            return {"ok": False, "metin": messages.APP_COMMAND_UNKNOWN}
        return {"ok": True, "secici": payload}

    async def _run_turn(self, task: str) -> dict[str, Any]:
        """Görevi agent motoruyla çalıştır; olaylar tel üzerinden akar.

        Yapılandırma ve onay modu `self._state`'TEN okunur (bkz. modül
        docstring'i): `/model` ya da `/security` gibi komutlar `self._state`i
        güncelledikten HEMEN SONRAKİ turda etkili olmalı, bir tur gecikmeli
        değil.
        """
        if not task.strip():
            return {"ok": False, "metin": messages.RUN_EMPTY_TASK}
        if self._turn is not None and not self._turn.done():
            return {"ok": False, "metin": messages.APP_TURN_ALREADY_RUNNING}
        from ..cli.session import run_agent_task

        sink = ProtocolSink(self._writer)
        prompter = ProtocolPrompter(self._writer, self.pending)
        self._turn = asyncio.ensure_future(
            run_agent_task(
                task,
                self._state.config,
                sinks=(sink,),
                prompter_factory=lambda _drain: prompter,
                mode=self._state.approval,
                root=self._state.root,
                home=self._state.home,
                history=self._state.history,
                extra_system=self._state.take_pending_digest(),
                interactive=True,
            )
        )
        try:
            outcome = await self._turn
        except asyncio.CancelledError:
            return {"ok": False, "metin": messages.APP_TURN_CANCELLED}
        finally:
            self._turn = None
        # Çok-turlu sohbet: bu turun ürettiği geçmiş bir SONRAKİ `tur.calistir`e
        # taşınsın diye durumda saklanır (bkz. `tui_loop.py:417` ile aynı desen).
        self._state.history = outcome.messages
        return {"ok": outcome.ok, "metin": outcome.final_text}

    def _cancel_turn(self) -> dict[str, Any]:
        if self._turn is None or self._turn.done():
            return {"ok": False, "metin": messages.APP_NO_RUNNING_TURN}
        self._turn.cancel()
        return {"ok": True, "metin": messages.APP_TURN_CANCELLED}

    def resolve_reply(self, reply: Reply) -> bool:
        """Uygulamanın cevabını bekleyen soruya bağla."""
        return self.pending.resolve(reply.id, reply.data)

    async def close(self) -> None:
        """Çalışan turu iptal et, bekleyen soruları serbest bırak."""
        if self._turn is not None and not self._turn.done():
            self._turn.cancel()
        await self._processes.close()
        self.pending.cancel_all()

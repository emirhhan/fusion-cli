"""Oturum ömrü: istekleri karşılar, turu çalıştırır, kapanışı düzenler.

Bir süreç BİR oturum yürütür. Uygulama ikinci bir sohbet istiyorsa ikinci bir
süreç başlatır; böylece paylaşılan durum, kilit ve sahiplik sorunları hiç
doğmaz ve bir oturumun çökmesi diğerini etkilemez.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..cli.repl.commands import build_registry
from ..cli.repl.state import ReplState
from ..config.credentials import FernetSecretStore
from ..config.keys import secret_key
from ..config.loader import load_config
from ..config.paths import credentials_file
from ..engines.agent.approval import ApprovalMode
from ..memory.factory import null_memory
from ..ui import messages
from .bridges import PendingQuestions, ProtocolPrompter, ProtocolSink, Writer
from .commands import command_choices, list_commands, run_command
from .protocol import Reply, Request, encode_result


class AppSession:
    """Uygulamanın sürdüğü tek oturum."""

    def __init__(self, writer: Writer, *, root: Path, home: Path) -> None:
        self._writer = writer
        self._root = root
        self._home = home
        self._config = load_config()
        self._mode = ApprovalMode.AUTO
        self._secret_store = FernetSecretStore(credentials_file(), secret_key=secret_key())
        self.pending = PendingQuestions()
        self._registry = build_registry(home)
        self._state = ReplState(config=self._config, memory=null_memory(), root=root, home=home)
        self._turn: asyncio.Task[Any] | None = None

    async def handle(self, request: Request) -> None:
        """İsteği çalıştır ve sonucunu yaz. İstisna sızdırmaz."""
        try:
            data = await self._dispatch(request)
        except Exception as error:  # istek sınırı: süreç çökmemeli
            data = {"ok": False, "metin": str(error)}
        self._writer(encode_result(request.id, data))

    async def _dispatch(self, request: Request) -> dict[str, Any]:
        if request.name == "oturum.durum":
            return self._status()
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

    def _status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "kok": str(self._root),
            "model": self._config.agent.model,
            "mod": self._mode.value,
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
        """Görevi agent motoruyla çalıştır; olaylar tel üzerinden akar."""
        if not task.strip():
            return {"ok": False, "metin": messages.RUN_EMPTY_TASK}
        from ..cli.session import run_agent_task

        sink = ProtocolSink(self._writer)
        prompter = ProtocolPrompter(self._writer, self.pending)
        self._turn = asyncio.ensure_future(
            run_agent_task(
                task,
                self._config,
                sinks=(sink,),
                prompter_factory=lambda _drain: prompter,
                mode=self._mode,
                root=self._root,
                home=self._home,
                history=self._state.history,
                interactive=True,
            )
        )
        try:
            outcome = await self._turn
        except asyncio.CancelledError:
            return {"ok": False, "metin": messages.APP_TURN_CANCELLED}
        finally:
            self._turn = None
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
        self.pending.cancel_all()

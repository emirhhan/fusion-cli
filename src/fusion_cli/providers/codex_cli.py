"""Codex CLI sağlayıcısı — ChatGPT aboneliğini ÇEREZSİZ, resmî yoldan kullanır.

Kullanıcı `codex login` ile ChatGPT hesabıyla bir kez giriş yapar; Codex kendi
OAuth jetonunu tutar ve yeniler. Fusion yalnızca `codex exec` süreci başlatır:
tarayıcı, çerez, captcha ya da profil kilidi yoktur. Model kimliği
`codex_cli/<model>`; `codex_cli/default` Codex'in kendi varsayılanını kullanır.

Bu sağlayıcı düz metin (araçsız) turlar içindir: öğretmen danışması, hakem, özet.
Codex her çağrıda salt-okunur kum havuzunda, boş geçici dizinde ve oturum
kaydı tutmadan (`--ephemeral`) çalışır; çalışma alanına dokunamaz.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from collections.abc import AsyncIterator
from pathlib import Path

from ..core.types import (
    CompletionRequest,
    ModelResult,
    StreamDone,
    StreamItem,
    TextChunk,
)

PREFIX = "codex_cli/"
DEFAULT_MODEL = "default"
AUTH_FILE = Path.home() / ".codex" / "auth.json"


def is_codex_model(model: str) -> bool:
    return model.startswith(PREFIX)


def codex_binary() -> str | None:
    """`codex` ikilisinin yolu; kurulu değilse None."""
    return shutil.which("codex") or next(
        (p for p in ("/opt/homebrew/bin/codex", "/usr/local/bin/codex") if Path(p).exists()),
        None,
    )


def codex_ready() -> bool:
    """Codex kurulu ve ChatGPT ile giriş yapılmış mı? (Ağ çağrısı yapmaz.)"""
    if codex_binary() is None or not AUTH_FILE.is_file():
        return False
    try:
        data = json.loads(AUTH_FILE.read_text())
    except (OSError, ValueError):
        return False
    return bool(data.get("tokens") or data.get("OPENAI_API_KEY"))


def _render_prompt(request: CompletionRequest) -> str:
    parts: list[str] = []
    for message in request.messages:
        if message.role == "system":
            parts.append(f"[SİSTEM]\n{message.content}")
        elif message.role == "assistant":
            parts.append(f"[ASİSTAN]\n{message.content}")
        else:
            parts.append(message.content)
    return "\n\n".join(parts)


def _friendly_error(stderr: str) -> str:
    text = stderr.strip()
    lowered = text.lower()
    if "usage limit" in lowered or "rate limit" in lowered:
        return f"codex kullanım sınırı doldu (429): {_last_line(text)}"
    if "not logged in" in lowered or ("login" in lowered and "codex login" in lowered):
        return "codex girişi yok: terminalde `codex login` çalıştır."
    return f"codex hatası: {_last_line(text) or 'bilinmeyen'}"


def _last_line(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1][:300] if lines else ""


class CodexCliProvider:
    """`codex exec` çağıran `LlmProvider`."""

    def __init__(self, model: str, *, role: str = "") -> None:
        self._model = model
        self._role = role
        name = model[len(PREFIX) :] or DEFAULT_MODEL
        self._codex_model = None if name == DEFAULT_MODEL else name

    @property
    def label(self) -> str:
        return self._model

    async def complete(self, request: CompletionRequest) -> ModelResult:
        started = time.monotonic()

        def _fail(error: str) -> ModelResult:
            return ModelResult(
                name=self._role,
                model=self._model,
                text="",
                latency_ms=int((time.monotonic() - started) * 1000),
                ok=False,
                error=error,
            )

        binary = codex_binary()
        if binary is None:
            return _fail("codex kurulu değil: `brew install codex` ardından `codex login`.")
        if not codex_ready():
            return _fail("codex girişi yok: terminalde `codex login` çalıştır.")
        with tempfile.TemporaryDirectory(prefix="fusion-codex-") as workdir:
            out = Path(workdir) / "cevap.txt"
            cmd = [
                binary,
                "exec",
                "--skip-git-repo-check",
                "--ephemeral",
                "-s",
                "read-only",
                "-o",
                str(out),
            ]
            if self._codex_model:
                cmd += ["-m", self._codex_model]
            cmd.append("-")
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=workdir,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _stdout, stderr = await asyncio.wait_for(
                    proc.communicate(_render_prompt(request).encode()),
                    timeout=request.timeout_s,
                )
            except TimeoutError:
                proc.kill()
                return _fail(f"codex {request.timeout_s:.0f} sn içinde cevap vermedi (zaman aşımı)")
            except OSError as exc:
                return _fail(f"codex başlatılamadı: {exc}")
            text = out.read_text().strip() if out.is_file() else ""
        if proc.returncode != 0 or not text:
            return _fail(_friendly_error(stderr.decode(errors="replace")))
        return ModelResult(
            name=self._role,
            model=self._model,
            text=text,
            latency_ms=int((time.monotonic() - started) * 1000),
            ok=True,
            served_by="Codex (ChatGPT aboneliği)",
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        result = await self.complete(request)
        if result.text:
            yield TextChunk(result.text)
        yield StreamDone(result)

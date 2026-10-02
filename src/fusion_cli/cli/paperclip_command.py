"""`fusion paperclip` — Fusion'ı Paperclip'e "process" adaptörüyle ajan olarak bağla.

Paperclip (paperclipai/paperclip) ajanları heartbeat'lerle uyandırır: process
adaptörü verilen komutu `PAPERCLIP_*` ortam değişkenleriyle çalıştırır, görevi
argüman olarak VERMEZ; ajan atamasını API'den kendisi alır. Bu komut uyanma
bilgisini ortamdan okuyup görevi kurar ve ajanı etkileşimsiz çalıştırır.

Paperclip'te kurulum: adaptör `process`, komut `fusion`, argüman `["paperclip"]`,
cwd çalışılacak proje. Skill'i bir kez kur:
`paperclipai agent local-cli <ajan> --company-id <şirket>` (~/.claude/skills'e yazar).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path

import typer

from ..config.keys import environ_snapshot
from ..config.loader import load_config
from ..engines.agent.approval import ApprovalMode
from .session import run_agent_task

#: Görevi kuran uyanma alanları (Paperclip skill'inin belgelediği adlar).
WAKE_KEYS = (
    "PAPERCLIP_TASK_ID",
    "PAPERCLIP_WAKE_REASON",
    "PAPERCLIP_WAKE_COMMENT_ID",
    "PAPERCLIP_APPROVAL_ID",
    "PAPERCLIP_APPROVAL_STATUS",
    "PAPERCLIP_LINKED_ISSUE_IDS",
    "PAPERCLIP_AGENT_ID",
    "PAPERCLIP_COMPANY_ID",
)


class PaperclipEnvError(ValueError):
    """Paperclip ortamı eksik; komut Paperclip dışından çalıştırıldı."""


def heartbeat_task(environ: Mapping[str, str]) -> str:
    """Ortamdaki uyanma bilgisinden ajan görevini kur (anahtar görevde YER ALMAZ)."""
    missing = [key for key in ("PAPERCLIP_API_URL", "PAPERCLIP_API_KEY") if not environ.get(key)]
    if missing:
        raise PaperclipEnvError(
            "Paperclip ortamı yok (" + ", ".join(missing) + "). Bu komutu Paperclip "
            "process adaptörü çalıştırır; elle denemek için `paperclipai agent local-cli` "
            "çıktısındaki değişkenleri dışa aktar."
        )
    uyanma = "\n".join(
        f"- {key}: {environ[key]}" for key in WAKE_KEYS if environ.get(key, "").strip()
    )
    sablon = (files("fusion_cli.engines.agent") / "prompts" / "paperclip_heartbeat.md").read_text(
        encoding="utf-8"
    )
    return sablon.replace("{uyanma}", uyanma or "- (atanmış iş bilgisi yok: gelen kutusuna bak)")


def paperclip() -> None:
    """Paperclip heartbeat'ini çalıştır (Paperclip process adaptörü çağırır)."""
    try:
        task = heartbeat_task(environ_snapshot())
    except PaperclipEnvError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from error
    config = load_config()
    outcome = asyncio.run(
        run_agent_task(
            task,
            config,
            sinks=(),
            prompter_factory=_no_prompter,
            mode=ApprovalMode.AUTO,
            root=Path.cwd(),
            home=Path.home(),
            interactive=False,
            conversation_id="paperclip-" + environ_snapshot().get("PAPERCLIP_RUN_ID", "elle"),
        )
    )
    typer.echo(outcome.final_text)
    if not outcome.ok:
        raise typer.Exit(1)


class _UnattendedPrompter:
    """Heartbeat etkileşimsizdir: onay gerektiren her işlem REDDEDİLİR, soru sorulmaz."""

    async def confirm(self, request: object) -> bool:
        return False

    async def ask(
        self, question: str, options: tuple[object, ...] = (), recommended: str | None = None
    ) -> str:
        return "Paperclip heartbeat'i etkileşimsizdir; soruyu Paperclip yorumu olarak sor."


def _no_prompter(_flush: object) -> _UnattendedPrompter:
    return _UnattendedPrompter()

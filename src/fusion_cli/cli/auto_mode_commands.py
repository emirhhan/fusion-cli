"""`fusion auto-mode` — Otomatik kip denetçisi (P-011): ayar, durum ve deneme.

    fusion auto-mode durum                      ayar, model, eşikler
    fusion auto-mode ayar <off|ask_only|on>     `runtime.auto_classifier` yaz
    fusion auto-mode dene "<komut>" [--niyet …] komutu denetçiye sor (gerçek model çağrısı)

`dene`, Otomatik kipte bu komut için ne olacağını gösterir: kural sormuyorsa ya da sabit
riskliyse model ÇAĞRILMAZ; aksi halde yapılandırılmış denetçi modeline tek istek gider.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape

from ..config.loader import load_config
from ..core.auto_review import AutoClassifierMode, AutoReviewSnapshot
from ..core.errors import FusionError
from ..engines.agent.approval import build_request
from ..engines.agent.risk_classifier import classifier_label, classify, review_kind
from ..tools.builtin import build_registry
from ..ui import messages
from ..ui.auto_review_view import source_label, status_text, verdict_label
from .repl.auto_mode_command import parse_setting, save_setting

console = Console()
app = typer.Typer(
    no_args_is_help=True,
    help="Otomatik kip denetçisi (risk sınıflandırıcısı): durum, ayar, deneme.",
)

_EMPTY = AutoReviewSnapshot(0, 0, 0, 0, False, "", ())


@app.command("durum")
def show() -> None:
    """Denetçi ayarı, modeli ve engel eşikleri (oturum sayaçları REPL'de: /auto-mode)."""
    config = load_config()
    text = status_text(_EMPTY, config.runtime.auto_classifier, classifier_label(config))
    console.print(escape(text), highlight=False)


@app.command("ayar")
def set_mode(
    value: Annotated[str, typer.Argument(help="off | ask_only | on (kapat | ac | tum)")],
) -> None:
    """`runtime.auto_classifier` ayarını kullanıcı yapılandırmasına yaz."""
    try:
        mode = parse_setting(value)
    except ValueError:
        raise FusionError(messages.AUTO_REVIEW_USAGE) from None
    _, text = save_setting(load_config(), mode)
    console.print(escape(text), highlight=False)


@app.command("dene")
def try_command(
    command: Annotated[str, typer.Argument(help="Denetçiye sorulacak kabuk komutu.")],
    intent: Annotated[
        list[str] | None,
        typer.Option("--niyet", "-n", help="Kullanıcı mesajı (birden çok verilebilir)."),
    ] = None,
) -> None:
    """Komutu Otomatik kipteki gibi denetçiden geçir ve kararı göster."""
    config = load_config()
    root = Path.cwd()
    tool = build_registry().get("run_shell")
    if tool is None:
        raise FusionError("run_shell aracı bulunamadı.")
    request = build_request(tool, {"command": command}, root=root)
    setting = config.runtime.auto_classifier
    if setting is AutoClassifierMode.OFF:
        setting = AutoClassifierMode.ON
    kind = review_kind(request, setting, root)
    if kind is None:
        reason = (
            messages.AUTO_REVIEW_TRY_NOT_RISKY
            if request.risk is None and request.danger is None
            else messages.AUTO_REVIEW_TRY_FIXED
        )
        console.print(escape(messages.AUTO_REVIEW_TRY_SKIPPED.format(reason=reason)))
        return
    outcome = asyncio.run(
        classify(request, tuple(intent or ()), config, None, root=root, kind=kind)
    )
    console.print(
        escape(
            messages.AUTO_REVIEW_TRY_RESULT.format(
                verdict=verdict_label(outcome.verdict),
                source=source_label(outcome.source),
                reason=outcome.reason,
            )
        ),
        highlight=False,
    )

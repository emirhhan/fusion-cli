"""`fusion gh-action kur` — depoya Fusion GitHub Actions iş akışı şablonu bırak (P-057).

Claude Code `/install-github-app` karşılığı: GitHub App yerine depo içi bir iş akışı
dosyası. Şablon paket verisidir (`cli/templates/fusion-action.yml`); var olan dosya
`--force` olmadan ezilmez.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ..core.errors import FusionError
from ..ui import messages

console = Console()

WORKFLOW_RELATIVE_PATH = Path(".github") / "workflows" / "fusion.yml"
_TEMPLATE = "fusion-action.yml"


def workflow_template() -> str:
    """Paketlenmiş şablon metni."""
    return (resources.files(__package__) / "templates" / _TEMPLATE).read_text(encoding="utf-8")


def install_workflow(root: Path, *, force: bool = False) -> Path:
    """Şablonu `root/.github/workflows/fusion.yml`'e yaz; dosya varsa `force` şart."""
    target = root / WORKFLOW_RELATIVE_PATH
    if target.exists() and not force:
        raise FusionError(messages.GH_ACTION_EXISTS.format(path=target))
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(workflow_template(), encoding="utf-8")
    except OSError as error:
        raise FusionError(
            messages.GH_ACTION_WRITE_FAILED.format(path=target, error=error)
        ) from error
    return target


def gh_action(
    action: Annotated[str, typer.Argument(help="`kur`: iş akışı dosyasını yaz.")] = "kur",
    force: bool = typer.Option(False, "--force", help="Var olan fusion.yml dosyasını ez."),
) -> None:
    """GitHub Actions'ta "@fusion <görev>" yorumuyla Fusion çalıştıran iş akışını kur."""
    if action != "kur":
        raise typer.BadParameter(messages.GH_ACTION_USAGE)
    target = install_workflow(Path.cwd(), force=force)
    console.print(messages.GH_ACTION_INSTALLED.format(path=target))
    for line in messages.GH_ACTION_NEXT_STEPS:
        console.print(f"  {line}")

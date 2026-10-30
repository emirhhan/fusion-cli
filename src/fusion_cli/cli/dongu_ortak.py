"""Kendini geliştirme döngüsü komutlarının ortak parçaları (`eval_commands`, `prompt_opt_commands`).

Tüm veri `config.paths.loop_dir()` altında, kullanıcının makinesinde kalır. `evals` ve
`prompt_opt` depo kökündeki geliştirici araçlarıdır (pakete girmez); komutlar onları ilk
kullanımda tembel yükler ve bulunamazsa ne yapılacağını söyler.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

from ..config.paths import loop_dir
from ..ui import theme

error_console = Console(stderr=True)

DEFAULT_SUITE = "kullanici"
DEFAULT_PROMPT = "system"
#: Çıkış kodları: ölçüm durdu (kota/erişim) ayrı, kullanıcı/yapılandırma hatası ayrı.
EXIT_FAILED = 1
EXIT_MEASUREMENT_STOPPED = 2

_TOOLS_MISSING = (
    "Bu komut depodaki geliştirici araçlarına (evals, prompt_opt) dayanır; kurulu pakette "
    "bulunmuyorlar. Depo kökünden çalıştır: .venv/bin/fusion ..."
)
_BUNDLED_SUITES = "evals/suite"


@dataclass(frozen=True, slots=True)
class LoopPaths:
    """Döngünün kullanıcıya özel dizinleri ve ölçüm izi dosyası."""

    drafts: Path
    suites: Path
    proposals: Path
    versions: Path
    log: Path
    bundled_suites: Path


def loop_paths() -> LoopPaths:
    root = loop_dir()
    repo = _repo_root()
    return LoopPaths(
        drafts=root / "taslak",
        suites=root / "kume",
        proposals=root / "oneriler",
        versions=root / "surumler",
        log=root / "kayit.jsonl",
        bundled_suites=(repo or Path()) / _BUNDLED_SUITES,
    )


def _repo_root() -> Path | None:
    """Kaynak deposunun kökü (`src/fusion_cli/cli/` üç seviye yukarı); kurulu pakette yok."""
    root = Path(__file__).resolve().parents[3]
    return root if (root / "evals" / "__init__.py").is_file() else None


def require_dev_tools() -> None:
    """`evals` ve `prompt_opt` içe aktarılabilir olsun; değilse depo kökünü yola ekle."""
    try:
        import evals  # noqa: F401
        import prompt_opt  # noqa: F401

        return
    except ImportError:
        pass
    root = _repo_root()
    if root is None or not (root / "prompt_opt" / "__init__.py").is_file():
        error_console.print(f"[{theme.WARN}]{escape(_TOOLS_MISSING)}[/{theme.WARN}]")
        raise typer.Exit(EXIT_FAILED)
    # Editable kurulum yalnız `src/`yi yola koyar; araçlar depo kökünde durur.
    sys.path.insert(0, str(root))


def fail(message: str) -> typer.Exit:
    error_console.print(f"[{theme.WARN}]{escape(message)}[/{theme.WARN}]")
    return typer.Exit(EXIT_FAILED)


def iso_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat(timespec="seconds")

"""`.worktreeinclude` eşlemesi Claude Code gibi `.gitignore` söz dizimiyle (#359).

Claude Code (worktrees, "Copy gitignored files into worktrees"): dosya `.gitignore` söz
dizimindedir; yalnız desene uyan VE git tarafından yok sayılan (gitignored) dosyalar yeni
ağaca kopyalanır. İzlenen dosyalar zaten ağaçtadır; izlenmeyen ama yok sayılmayan dosya
kopyalanmaz.

Eşleme git'e bırakılır: `git ls-files --others --ignored --exclude-from=.worktreeinclude`
desene uyan izlenmeyen dosyaları, `git check-ignore --stdin` bunlardan gitignored olanları
verir (`!`, dizin ve `**/` kuralları git'in kendisi). Eski Fusion davranışı (1 Kasım öncesi):
desenler `Path.glob` ile köke göre eşleniyordu (`.env` yalnız kökteki dosya) ve gitignore
denetimi yoktu.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__ = ["included_files"]

_TIMEOUT_S = 30.0


def _run(origin: Path, args: list[str], stdin: str | None = None) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=origin,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    # check-ignore hiçbir yol yok sayılmadıysa 1 döner; bu bir hata değildir.
    if completed.returncode not in (0, 1):
        return None
    return completed.stdout


def included_files(origin: Path, include_file: str) -> tuple[Path, ...]:
    """Desene uyan ve gitignored olan dosyalar (köke göreli, sıralı); git yoksa boş."""
    if not (origin / include_file).is_file():
        return ()
    listed = _run(
        origin,
        ["ls-files", "--others", "--ignored", f"--exclude-from={include_file}", "-z"],
    )
    if not listed:
        return ()
    candidates = [item for item in listed.split("\0") if item]
    ignored = _run(origin, ["check-ignore", "--stdin", "-z"], "\0".join(candidates) + "\0")
    if not ignored:
        return ()
    names = {item for item in ignored.split("\0") if item}
    return tuple(sorted(Path(item) for item in candidates if item in names))

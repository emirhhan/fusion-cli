"""Çalışma ağacı için soru sormayan `git fetch` ve "fresh" taban (Claude Code, #338, #341).

Claude Code (worktrees, "Choose the base branch"): `worktree.baseRef` varsayılanı `"fresh"`:
ağaç uzak varsayılan daldan (`origin/HEAD`) dallanır. Depo son 24 saatte çekilmediyse
varsayılan dal en çok 5 sn'de çekilir, başarısızsa yereldeki kayıt kullanılır; uzak yoksa ya da
`origin/HEAD` bilinmiyorsa yerel `HEAD`'e düşülür. `"head"`: bulunulan checkout'un `HEAD`'i.
Çekme hiçbir zaman terminalden girdi beklemez: parola, anahtar parolası ya da yeni SSH
sunucusu onayı gerekecekse başarısız sayılır.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from .errors import WorktreeError

BASE_FRESH = "fresh"
BASE_HEAD = "head"
BASE_REFS = (BASE_FRESH, BASE_HEAD)
#: "fresh" tabanda depo bu süreden eskiyse varsayılan dal yeniden çekilir.
FRESH_FETCH_AGE_S = 24 * 60 * 60
#: "fresh" tabanda varsayılan dal çekme üst süresi.
FRESH_FETCH_TIMEOUT_S = 5.0
#: Ağ gerektirmeyen yerel git komutlarının üst süresi.
GIT_LOCAL_TIMEOUT_S = 60.0
#: PR/MR başını çekme üst süresi.
PR_FETCH_TIMEOUT_S = 60.0
_ORIGIN_HEAD = "refs/remotes/origin/HEAD"


def quiet_env(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Terminal sorusu açmayan git ortamı."""
    env = dict(os.environ if environ is None else environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    return env


def quiet_git(cwd: Path, args: Sequence[str], *, timeout_s: float) -> str | None:
    """`git` çalıştır; başarısızlık, zaman aşımı ya da soru gereksinimi `None`."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            env=quiet_env(),
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout if completed.returncode == 0 else None


def fetch_pull_request(origin: Path, refspecs: Sequence[str], number: int) -> None:
    """PR/MR başını `origin`'den `FETCH_HEAD`'e çek; hiçbiri olmazsa `WorktreeError`."""
    for refspec in refspecs:
        if quiet_git(origin, ("fetch", "--quiet", "origin", refspec), timeout_s=PR_FETCH_TIMEOUT_S) is not None:
            return
    raise WorktreeError(f"Çalışma ağacı oluşturulamadı: PR/MR #{number} çekilemedi.")


def fresh_base(origin: Path, *, now: float | None = None) -> str:
    """"fresh" tabanın commit'e çözülebilir başvurusu: `origin/HEAD` ya da yedek `HEAD`."""
    if quiet_git(origin, ("remote", "get-url", "origin"), timeout_s=FRESH_FETCH_TIMEOUT_S) is None:
        return "HEAD"
    branch = _origin_head_branch(origin)
    if branch is None:
        quiet_git(origin, ("remote", "set-head", "origin", "--auto"), timeout_s=FRESH_FETCH_TIMEOUT_S)
        branch = _origin_head_branch(origin)
        if branch is None:
            return "HEAD"
    elif _fetch_is_stale(origin, time.time() if now is None else now):
        quiet_git(origin, ("fetch", "--quiet", "origin", branch), timeout_s=FRESH_FETCH_TIMEOUT_S)
    resolved = quiet_git(
        origin, ("rev-parse", "--verify", "--quiet", f"{_ORIGIN_HEAD}^{{commit}}"), timeout_s=FRESH_FETCH_TIMEOUT_S
    )
    return _ORIGIN_HEAD if resolved else "HEAD"


def _origin_head_branch(origin: Path) -> str | None:
    """`origin/HEAD`'in gösterdiği dal adı (`main`); yerelde kayıt yoksa `None`."""
    output = quiet_git(
        origin, ("symbolic-ref", "--quiet", _ORIGIN_HEAD), timeout_s=FRESH_FETCH_TIMEOUT_S
    )
    prefix = "refs/remotes/origin/"
    target = (output or "").strip()
    return target[len(prefix) :] if target.startswith(prefix) else None


def _fetch_is_stale(origin: Path, now: float) -> bool:
    """Depo son `FRESH_FETCH_AGE_S` içinde çekilmedi mi (`FETCH_HEAD` zamanı)?"""
    common = quiet_git(origin, ("rev-parse", "--git-common-dir"), timeout_s=FRESH_FETCH_TIMEOUT_S)
    if not common:
        return True
    git_dir = Path(common.strip())
    if not git_dir.is_absolute():
        git_dir = origin / git_dir
    try:
        return now - (git_dir / "FETCH_HEAD").stat().st_mtime > FRESH_FETCH_AGE_S
    except OSError:
        return True

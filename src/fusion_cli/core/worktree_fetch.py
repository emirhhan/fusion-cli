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


def quiet_env(
    environ: Mapping[str, str] | None = None, *, batch_ssh: bool = True
) -> dict[str, str]:
    """Terminal sorusu açmayan git ortamı.

    `batch_ssh=False`: kullanıcının `core.sshCommand` ayarı var; ortam değişkeni onu ezerdi
    (git'te `GIT_SSH_COMMAND` > `core.sshCommand`), BatchMode o ayara eklenir (`_ssh_options`).
    """
    env = dict(os.environ if environ is None else environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    if batch_ssh:
        env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    return env


def _ssh_options(cwd: Path) -> tuple[list[str], bool]:
    """(git `-c` seçenekleri, ortamda BatchMode kullanılsın mı) — `core.sshCommand`'a göre."""
    if os.environ.get("GIT_SSH_COMMAND") or os.environ.get("GIT_SSH"):
        return [], True
    configured = _run(cwd, ("config", "--get", "core.sshCommand"), GIT_LOCAL_TIMEOUT_S) or ""
    command = configured.strip()
    if not command:
        return [], True
    first = command.split(maxsplit=1)[0].rsplit("/", 1)[-1]
    if first == "ssh" and "BatchMode" not in command:
        return ["-c", f"core.sshCommand={command} -o BatchMode=yes"], False
    return [], False


def _run(cwd: Path, args: Sequence[str], timeout_s: float, *, network: bool = False) -> str | None:
    completed = _completed(cwd, args, timeout_s, network=network)
    return completed.stdout if completed is not None and completed.returncode == 0 else None


def _completed(
    cwd: Path, args: Sequence[str], timeout_s: float, *, network: bool = False
) -> subprocess.CompletedProcess[str] | None:
    options, batch_ssh = _ssh_options(cwd) if network else ([], True)
    try:
        return subprocess.run(
            ["git", *options, *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            env=quiet_env(batch_ssh=batch_ssh),
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def quiet_git(
    cwd: Path, args: Sequence[str], *, timeout_s: float, network: bool = False
) -> str | None:
    """`git` çalıştır; başarısızlık, zaman aşımı ya da soru gereksinimi `None`.

    `network=True` (fetch, set-head): kullanıcının `core.sshCommand` ayarı korunur.
    """
    return _run(cwd, args, timeout_s, network=network)


def fetch_pull_request(origin: Path, refspecs: Sequence[str], number: int) -> None:
    """PR/MR başını `origin`'den `FETCH_HEAD`'e çek; hiçbiri olmazsa nedeniyle `WorktreeError`."""
    reason = ""
    for refspec in refspecs:
        completed = _completed(
            origin, ("fetch", "--quiet", "origin", refspec), PR_FETCH_TIMEOUT_S, network=True
        )
        if completed is not None and completed.returncode == 0:
            return
        reason = "zaman aşımı" if completed is None else completed.stderr.strip()
    lines = reason.splitlines()
    first = next((line for line in lines if line.startswith(("fatal:", "error:"))), "")
    detail = f" ({first or lines[0]})" if lines else ""
    raise WorktreeError(f"Çalışma ağacı oluşturulamadı: PR/MR #{number} çekilemedi{detail}.")


def fresh_base(origin: Path, *, now: float | None = None) -> str:
    """ "fresh" tabanın commit'e çözülebilir başvurusu: `origin/HEAD` ya da yedek `HEAD`."""
    if quiet_git(origin, ("remote", "get-url", "origin"), timeout_s=FRESH_FETCH_TIMEOUT_S) is None:
        return "HEAD"
    branch = _origin_head_branch(origin)
    if branch is None:
        quiet_git(
            origin,
            ("remote", "set-head", "origin", "--auto"),
            timeout_s=FRESH_FETCH_TIMEOUT_S,
            network=True,
        )
        branch = _origin_head_branch(origin)
        if branch is None:
            return "HEAD"
    elif _fetch_is_stale(origin, time.time() if now is None else now):
        quiet_git(
            origin,
            ("fetch", "--quiet", "origin", branch),
            timeout_s=FRESH_FETCH_TIMEOUT_S,
            network=True,
        )
    resolved = quiet_git(
        origin,
        ("rev-parse", "--verify", "--quiet", f"{_ORIGIN_HEAD}^{{commit}}"),
        timeout_s=FRESH_FETCH_TIMEOUT_S,
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

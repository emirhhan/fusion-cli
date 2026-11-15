"""Sohbete bağlı PR'ların durumu: Claude Desktop "Auto-archive after PR merge or close" (#443).

Masaüstü kenar çubuğu, ayar açıkken arşivlenmemiş ve çalışmayan sohbetler için bu RPC'yi
(`sohbet.pr_durumlari`) çağırır; PR'ı birleşen (`MERGED`) ya da kapanan (`CLOSED`) sohbeti
arşivler. PR künyesi `cli/repl/linked_pr` kaydından okunur; durum `gh pr view <no> --repo
<depo> --json state` ile sorulur (yalnız okuma, kabuk yok, zaman aşımlı). `gh` yoksa ya da
hata verirse o sohbet atlanır: otomatik arşiv tahminle yapılmaz.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path

from ..cli.repl import linked_pr
from ..core.pull_request import PullRequestLink

#: Tek istekte sorulan en çok sohbet (kenar çubuğu yüzlerce sohbet tutabilir).
MAX_CONVERSATIONS = 50
_TIMEOUT_SECONDS = 10.0
_STATES = frozenset({"OPEN", "MERGED", "CLOSED"})

#: `(link) -> "OPEN"|"MERGED"|"CLOSED"|None`; testte sahte koşucu verilir.
StateReader = Callable[[PullRequestLink], str | None]


def pr_states(
    memory_dir: Path, conversation_ids: Iterable[object], reader: StateReader | None = None
) -> dict[str, str]:
    """PR'ı bağlı sohbetlerin PR durumu; künyesi olmayan ya da okunamayan sohbet yer almaz."""
    read = reader or gh_pr_state
    found: dict[str, str] = {}
    cache: dict[tuple[str, int], str | None] = {}
    for conversation in _valid_ids(conversation_ids):
        link = linked_pr.load(memory_dir, conversation)
        if link is None:
            continue
        key = (link.repo, link.number)
        if key not in cache:
            cache[key] = read(link)
        state = cache[key]
        if state in _STATES:
            found[conversation] = state
    return found


def _valid_ids(values: Iterable[object]) -> list[str]:
    ids = [value for value in values if isinstance(value, str) and value.strip()]
    return list(dict.fromkeys(ids))[:MAX_CONVERSATIONS]


def gh_pr_state(link: PullRequestLink) -> str | None:
    """`gh` ile PR durumunu oku; `gh` yok, ağ hatası ya da beklenmeyen çıktıda `None`."""
    gh = shutil.which("gh")
    if gh is None:
        return None
    command = [gh, "pr", "view", str(link.number), "--repo", link.repo, "--json", "state"]
    try:
        done = subprocess.run(
            command, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    try:
        state = json.loads(done.stdout).get("state")
    except (ValueError, AttributeError):
        return None
    return state if isinstance(state, str) and state in _STATES else None

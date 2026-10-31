"""Salt-okunur `gh` (GitHub CLI) aracı — PR/CI bağlamı (P-057).

Claude Code PR işlerini `gh` üzerinden yapar ("create a pr" → `gh pr create`, `--from-pr`,
`/pr-comments`). Fusion'da okuma `gh` aracıyla onaysızdır; yazan `gh` komutları
(`pr create`, `pr merge`, `pr comment`…) bu araçtan GEÇMEZ: model onları `run_shell` ile
çalıştırır ve onay akışına girer (`tools/auto_policy.py::_GH_WRITES` dışa dönük risk sayar).

Yalnız şu biçimler kabul edilir:
- `pr view|diff|checks|status|list …`, `issue view|list …`, `run list|view …`, `repo view …`
- `api <yol>` yalnız GET: `-X/--method`, `-f/-F/--field/--raw-field/--input` reddedilir.

`gh` kurulu değilse araç kurulum ipucuyla başarısız döner; tur çökmez.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess

from ..core.constants import GH_TIMEOUT_S, MAX_OUTPUT_CHARS, truncate_notice
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_str

#: `gh <komut> <alt komut>` çiftlerinden salt-okunur olanlar.
READONLY_GH_COMMANDS: frozenset[tuple[str, str]] = frozenset(
    {
        ("pr", "view"),
        ("pr", "diff"),
        ("pr", "checks"),
        ("pr", "status"),
        ("pr", "list"),
        ("issue", "view"),
        ("issue", "list"),
        ("run", "list"),
        ("run", "view"),
        ("repo", "view"),
        ("auth", "status"),
    }
)
#: `gh api` için yazma anlamına gelen bayraklar.
_API_WRITE_FLAGS = frozenset(
    {"-X", "--method", "-f", "-F", "--field", "--raw-field", "--input", "--silent"}
)
GH_MISSING = (
    "GitHub CLI (gh) kurulu değil. Kur: https://cli.github.com (macOS: brew install gh), "
    "sonra `gh auth login`."
)


def gh_reads_only(parts: list[str]) -> bool:
    """Argüman listesi salt-okunur bir `gh` çağrısı mı?"""
    if not parts:
        return False
    if parts[0] == "api":
        if len(parts) < 2:
            return False
        for argument in parts[1:]:
            if argument in _API_WRITE_FLAGS or argument.startswith(("-X", "--method=")):
                return False
        return True
    if len(parts) < 2:
        return False
    return (parts[0], parts[1]) in READONLY_GH_COMMANDS


def gh(args: ToolArgs, context: ToolContext) -> ToolResult:
    """`gh` aracı executor'ı: salt-okunur komutu proje kökünde çalıştır."""
    command = require_str(args, "args")
    try:
        parts = shlex.split(command)
    except ValueError as error:
        return ToolResult.failure(f"gh argümanları ayrıştırılamadı (tırnak hatası?): {error}")
    if not gh_reads_only(parts):
        allowed = ", ".join(sorted(f"{a} {b}" for a, b in READONLY_GH_COMMANDS))
        return ToolResult.failure(
            f"Yalnızca salt-okunur gh komutlarına izin var ({allowed}; api yalnız GET). "
            "PR oluşturma/yorum/merge için run_shell kullan (onay istenir)."
        )
    executable = shutil.which("gh")
    if executable is None:
        return ToolResult.failure(GH_MISSING)
    try:
        process = subprocess.run(
            [executable, *parts],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GH_TIMEOUT_S,
            cwd=context.root,
            env=_child_env(),
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        return ToolResult.failure(f"gh çalıştırılamadı: {error}")
    text = process.stdout or ""
    if process.stderr:
        text += f"\n[stderr]\n{process.stderr}"
    body = truncate_notice(text, MAX_OUTPUT_CHARS, ne="gh çıktısı").strip()
    return ToolResult(body or "(çıktı yok)", ok=process.returncode == 0)


def _child_env() -> dict[str, str]:
    """`gh` sayfalayıcı/istem açmasın: etkileşimsiz çalışır."""
    import os

    return {**os.environ, "GH_PAGER": "cat", "GH_PROMPT_DISABLED": "1", "NO_COLOR": "1"}


def pr_context(number: int, *, root: object) -> str:
    """`--from-pr N` için PR özeti (başlık, dallar, açıklama, adres); `gh` yoksa `RuntimeError`.

    Metin modele görevin başına eklenir; yorum/diff'i model gerekirse `gh` aracıyla okur.
    """
    executable = shutil.which("gh")
    if executable is None:
        raise RuntimeError(GH_MISSING)
    try:
        process = subprocess.run(
            [
                executable,
                "pr",
                "view",
                str(number),
                "--json",
                "number,title,body,url,headRefName,baseRefName,state",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GH_TIMEOUT_S,
            cwd=str(root),
            env=_child_env(),
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        raise RuntimeError(f"gh çalıştırılamadı: {error}") from error
    if process.returncode != 0:
        raise RuntimeError(f"PR #{number} okunamadı: {(process.stderr or process.stdout).strip()}")
    import json

    try:
        data = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"PR #{number} cevabı okunamadı: {error}") from error
    body = str(data.get("body") or "").strip()
    return (
        f"# Bağlam: PR #{data.get('number', number)} — {data.get('title', '')}\n"
        f"Adres: {data.get('url', '')}\n"
        f"Dal: {data.get('headRefName', '')} → {data.get('baseRefName', '')} "
        f"(durum: {data.get('state', '')})\n"
        f"Açıklama:\n{body or '(boş)'}\n"
        "Yorumlar, diff ve CI için `gh` aracını kullan: `pr view N --comments`, "
        "`pr diff N`, `pr checks N`."
    )

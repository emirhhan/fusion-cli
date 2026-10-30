"""Projenin kullanıcıya gösterilecek doğrulama komutları ve Git özeti."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def _command(kind: str, label: str, command: str) -> dict[str, str]:
    return {"tur": kind, "ad": label, "komut": command}


#: Kilit dosyası → paket yöneticisi. `npm` sabit yazılması pnpm/yarn/bun projesinde yanlış
#: komut öneriyordu (ölçüldü 30 Ekim).
_LOCKFILES = (
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("bun.lockb", "bun"),
    ("bun.lock", "bun"),
)


def _package_manager(root: Path) -> str:
    return next((manager for lock, manager in _LOCKFILES if (root / lock).is_file()), "npm")


def _python_command() -> str:
    """macOS/Linux'ta çoğu zaman yalnız `python3` vardır; Windows'ta `python`."""
    return "python" if sys.platform == "win32" else "python3"


def suggested_commands(root: Path) -> dict[str, Any]:
    commands: list[dict[str, str]] = []
    makefile = root / "Makefile"
    if makefile.is_file():
        try:
            text = makefile.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        targets = set(re.findall(r"^([A-Za-z0-9_.-]+):(?!=)", text, flags=re.MULTILINE))
        if "check" in targets:
            return {"ok": True, "komutlar": [_command("check", "Tüm kalite kapısı", "make check")]}
        for target, kind, label in (
            ("test", "test", "Testleri çalıştır"),
            ("lint", "lint", "Kod denetimi"),
            ("build", "build", "Üretim derlemesi"),
        ):
            if target in targets:
                commands.append(_command(kind, label, f"make {target}"))
        if commands:
            return {"ok": True, "komutlar": commands}

    package = root / "package.json"
    if package.is_file():
        try:
            raw = json.loads(package.read_text(encoding="utf-8"))
            scripts = raw.get("scripts", {}) if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError):
            scripts = {}
        if isinstance(scripts, dict):
            manager = _package_manager(root)
            for name, kind, label in (
                ("test", "test", "Testleri çalıştır"),
                ("lint", "lint", "Kod denetimi"),
                ("build", "build", "Üretim derlemesi"),
                ("dev", "dev", "Önizlemeyi başlat"),
            ):
                if name in scripts:
                    command = f"{manager} test" if name == "test" else f"{manager} run {name}"
                    commands.append(_command(kind, label, command))
    if not commands and ((root / "pyproject.toml").is_file() or (root / "tests").is_dir()):
        # package.json'da script yoksa (ya da hiç yoksa) Python projesi olabilir.
        commands.append(_command("test", "Testleri çalıştır", f"{_python_command()} -m pytest -q"))
    return {"ok": True, "komutlar": commands}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def git_status(root: Path) -> dict[str, Any]:
    # `.git` yalnız kökte aranırsa depo alt klasörü "git yok" sanılırdı (ölçüldü 30 Ekim).
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if inside is None or inside.returncode != 0 or inside.stdout.strip() != "true":
        return {"ok": True, "git": False, "branch": None, "degisen": 0, "ileride": 0, "geride": 0}
    branch_result = _git(root, "branch", "--show-current")
    status_result = _git(root, "status", "--porcelain=v1")
    branch = branch_result.stdout.strip() if branch_result and branch_result.returncode == 0 else ""
    changed = (
        len(status_result.stdout.splitlines())
        if status_result and status_result.returncode == 0
        else 0
    )
    ahead = behind = 0
    divergence = _git(root, "rev-list", "--left-right", "--count", "@{upstream}...HEAD")
    if divergence is not None and divergence.returncode == 0:
        values = divergence.stdout.split()
        if len(values) == 2:
            behind, ahead = (int(value) for value in values)
    return {
        "ok": True,
        "git": True,
        "branch": branch or None,
        "degisen": changed,
        "ileride": ahead,
        "geride": behind,
    }

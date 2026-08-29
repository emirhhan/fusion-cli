"""Projenin kullanıcıya gösterilecek doğrulama komutları ve Git özeti."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any


def _command(kind: str, label: str, command: str) -> dict[str, str]:
    return {"tur": kind, "ad": label, "komut": command}


def suggested_commands(root: Path) -> dict[str, Any]:
    commands: list[dict[str, str]] = []
    makefile = root / "Makefile"
    if makefile.is_file():
        try:
            text = makefile.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        targets = set(re.findall(r"^([A-Za-z0-9_.-]+):", text, flags=re.MULTILINE))
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
            for name, kind, label, command in (
                ("test", "test", "Testleri çalıştır", "npm test"),
                ("lint", "lint", "Kod denetimi", "npm run lint"),
                ("build", "build", "Üretim derlemesi", "npm run build"),
                ("dev", "dev", "Önizlemeyi başlat", "npm run dev"),
            ):
                if name in scripts:
                    commands.append(_command(kind, label, command))
    elif (root / "pyproject.toml").is_file() or (root / "tests").is_dir():
        commands.append(_command("test", "Testleri çalıştır", "python -m pytest -q"))
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
    if not (root / ".git").exists():
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

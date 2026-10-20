"""Bir GitHub reposunu yetenek olarak kur — "şu repoyla çalış" isteğinin altyapısı.

Örnek: `kaomei/stickman-video-director` bir Codex SKILL paketidir (SKILL.md +
references/). Kullanıcı "stickman video director ile video yap" dediğinde Fusion'ın
o skill'i bulup okuyabilmesi için reponun bilinen bir yerde durması yeter.

Kurallar:

- Repo `git clone --depth 1` ile Fusion veri klasörüne alınır ve kurulduğu commit
  kaydedilir (`fusion-yetenek.json`). Sonradan gelen değişiklik kendiliğinden girmez.
- Kurulumda repodaki HİÇBİR betik çalıştırılmaz (npm install, setup.sh yok). Betik
  gerekiyorsa ajan onu `run_shell` ile, onay alarak çalıştırır.
- Yalnız `https://github.com/<sahip>/<repo>` adresleri kabul edilir.
- Kaldırma kalıcı değildir: klasör Fusion çöpüne taşınır.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from ..config.keys import environ_snapshot
from ..config.paths import capabilities_dir
from ..core.constants import GIT_TIMEOUT_S
from ..core.errors import FusionError
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_str

_GITHUB = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
_MANIFEST = "fusion-yetenek.json"
#: Klonlama ağ işidir ve büyük repoda uzun sürebilir; git varsayılanı süresiz.
#: 120 sn: sığ klonun (--depth 1) yavaş bağlantıda bile bitmesi için geniş pay.
CLONE_TIMEOUT_S = 120.0


class CapabilityInstallError(FusionError):
    """Yetenek kurulamadı; mesaj kullanıcıya gösterilir."""


@dataclass(frozen=True, slots=True)
class InstalledCapability:
    name: str
    url: str
    commit: str
    path: Path
    skills: tuple[str, ...]
    agents: tuple[str, ...]


def parse_repo(url: str) -> tuple[str, str]:
    match = _GITHUB.match(url.strip())
    if match is None:
        raise CapabilityInstallError(
            "Yalnız https://github.com/<sahip>/<repo> biçimindeki adresler kurulabilir."
        )
    return match.group(1), match.group(2)


def install(url: str, root: Path) -> InstalledCapability:
    """Repoyu `root/<sahip>-<repo>` altına sığ klonla ve içeriğini çıkar."""
    owner, repo = parse_repo(url)
    name = f"{owner}-{repo}".lower()
    target = root / name
    if target.exists():
        raise CapabilityInstallError(
            f"'{name}' zaten kurulu ({target}). Güncellemek için önce kaldır."
        )
    root.mkdir(parents=True, exist_ok=True)
    clean_url = f"https://github.com/{owner}/{repo}.git"
    _git(
        ["clone", "--depth", "1", "--quiet", clean_url, str(target)],
        cwd=root,
        timeout=CLONE_TIMEOUT_S,
    )
    commit = _git(["rev-parse", "HEAD"], cwd=target, timeout=GIT_TIMEOUT_S).strip()
    installed = describe(name, f"https://github.com/{owner}/{repo}", commit, target)
    (target / _MANIFEST).write_text(
        json.dumps(
            {"url": installed.url, "commit": commit, "kurulum": time.time()}, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    return installed


def describe(name: str, url: str, commit: str, path: Path) -> InstalledCapability:
    skills = tuple(
        sorted(p.parent.relative_to(path).as_posix() or "." for p in path.rglob("SKILL.md"))
    )
    agents = tuple(
        sorted(
            p.stem
            for folder in (path / "agents", path / ".claude" / "agents")
            if folder.is_dir()
            for p in folder.glob("*.md")
        )
    )
    return InstalledCapability(name, url, commit, path, skills, agents)


def installed(root: Path) -> list[InstalledCapability]:
    found: list[InstalledCapability] = []
    if not root.is_dir():
        return found
    for folder in sorted(root.iterdir()):
        try:
            data = json.loads((folder / _MANIFEST).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        found.append(describe(folder.name, str(data["url"]), str(data["commit"]), folder))
    return found


def _git(args: list[str], *, cwd: Path, timeout: float) -> str:
    try:
        process = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            # Özel repo için kimlik bilgisi SORULMAZ: etkileşimsiz süreç takılırdı.
            env={**environ_snapshot(), "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CapabilityInstallError(f"git çalıştırılamadı: {error}") from error
    if process.returncode != 0:
        raise CapabilityInstallError(f"git başarısız: {process.stderr.strip()[:300]}")
    return process.stdout


def install_tool(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Ajan aracı: repoyu yetenek olarak kur ve içindeki skill/ajanları bildir."""
    try:
        kurulan = install(require_str(args, "url"), capabilities_dir())
    except CapabilityInstallError as error:
        return ToolResult.failure(str(error))
    return ToolResult(summary(kurulan) + "\nSkill'leri find_skill/read_skill ile kullan.")


def summary(item: InstalledCapability) -> str:
    return (
        f"Kuruldu: {item.name} @ {item.commit[:10]} ({item.path})\n"
        f"Skill'ler: {', '.join(item.skills) or 'yok'}\n"
        f"Ajanlar: {', '.join(item.agents) or 'yok'}\n"
        "Repodaki betikler ÇALIŞTIRILMADI; gerekirse run_shell ile onaylı çalıştır."
    )

"""Kullanıcının verdiği pazar kaynağını çekme: git (https/http/SSH, `--sparse`) ve url türü.

Claude Code (cli-reference "plugin marketplace add"): özel depolar yerel git kimlik bilgileri
ve SSH ile klonlanır; `--sparse <yollar...>` monorepo'da checkout'u bu klasörlerle sınırlar
(git sparse-checkout); `.git` olmayan http(s) adresi doğrudan `marketplace.json` indirilir.

Pazar GİRDİSİNDEKİ eklenti kaynakları bu yolu KULLANMAZ (`plugin_install._clone`: yalnız genel
https). Klon etkileşimsizdir: SSH `BatchMode=yes`, parola istemi yok, yönlendirme izlenmez.
"""

from __future__ import annotations

import json
import shutil
import urllib.request
from collections.abc import Sequence
from pathlib import Path

from ..core.constants import GIT_TIMEOUT_S
from ..core.plugins import PluginError
from . import capability_install

MARKETPLACE_FILE = Path(".claude-plugin") / "marketplace.json"
MAX_MARKETPLACE_BYTES = 10 * 1024 * 1024
FETCH_TIMEOUT_S = 60.0

_USER_GIT_CONFIG: tuple[str, ...] = (
    "http.followRedirects=false",
    "protocol.allow=never",
    "protocol.https.allow=always",
    "protocol.http.allow=always",
    "protocol.ssh.allow=always",
    "core.sshCommand=ssh -o BatchMode=yes",
)

ERR_DOWNLOAD = "marketplace.json indirilemedi ({url}): {error}"
ERR_TOO_LARGE = "marketplace.json çok büyük ({url}): {size} bayt üstü"
ERR_SPARSE = "--sparse yalnız git pazarlarında kullanılır"


def _options() -> list[str]:
    return [item for config in _USER_GIT_CONFIG for item in ("-c", config)]


def clone_user_source(url: str, target: Path, *, ref: str = "", sparse: Sequence[str] = ()) -> str:
    """Sığ klon (`--sparse` ile seyrek); commit döner. `.git` silinir (yeniden klonlanır)."""
    timeout = capability_install.CLONE_TIMEOUT_S
    args = [*_options(), "clone", "--depth", "1", "--quiet"]
    if ref:
        args += ["--branch", ref]
    if sparse:
        args += ["--filter=blob:none", "--sparse"]
    try:
        capability_install._git([*args, url, str(target)], cwd=target.parent, timeout=timeout)
        if sparse:
            capability_install._git(
                ["sparse-checkout", "set", "--", *sparse], cwd=target, timeout=timeout
            )
        commit = capability_install._git(["rev-parse", "HEAD"], cwd=target, timeout=GIT_TIMEOUT_S)
    except capability_install.CapabilityInstallError as error:
        raise PluginError(str(error)) from error
    shutil.rmtree(target / ".git", ignore_errors=True)
    return commit.strip().lower()


def _read_limited(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "fusion-cli"})
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_S) as response:
        data = response.read(MAX_MARKETPLACE_BYTES + 1)
    if len(data) > MAX_MARKETPLACE_BYTES:
        raise PluginError(ERR_TOO_LARGE.format(url=url, size=MAX_MARKETPLACE_BYTES))
    return bytes(data)


def download_marketplace(url: str, target: Path) -> Path:
    """url türü: `marketplace.json`'ı `<target>/.claude-plugin/` altına indir; dosya yolu."""
    try:
        data = _read_limited(url)
        json.loads(data.decode("utf-8"))
    except (OSError, ValueError) as error:
        raise PluginError(ERR_DOWNLOAD.format(url=url, error=error)) from error
    path = target / MARKETPLACE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path

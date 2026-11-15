"""`fusion plugin tag [yol]` — sürüm etiketi (Claude Code `claude plugin tag`, #380).

Ölçülen Claude 2.1.287 davranışı: `<yol>/.claude-plugin/plugin.json` gerekir ("No plugin
manifest found"); `version` yoksa etiketlenmez; üst klasörlerdeki `marketplace.json` girdisi bu
eklentiyi gösteriyor ve farklı `version` bildiriyorsa "Version mismatch" hatası; sürüme giren
yollarda kaydedilmemiş değişiklik ya da aynı adlı etiket varsa `--force` olmadan reddedilir.
Etiket `<ad>--v<sürüm>`, açıklama `-m` (içindeki `%s` sürüm) yoksa `"<ad> <sürüm>"`,
`git tag -a` ile HEAD'e konur; `--push` `--remote`'a (varsayılan origin) gönderir.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..core.constants import GIT_TIMEOUT_S
from ..core.plugins import PluginError

PLUGIN_FILE = Path(".claude-plugin") / "plugin.json"
MARKET_FILE = Path(".claude-plugin") / "marketplace.json"

ERR_PATH = "Yol bulunamadı: {path}"
ERR_MANIFEST = "Eklenti bildirimi yok. Beklenen: {path}"
ERR_NO_VERSION = (
    '"{path}" içinde "version" yok; etiketlenecek sürüm yok. Etiketler yalnız bağımlılık sürüm '
    "kısıtları içindir ve açık semver ister"
)
ERR_MISMATCH = (
    'Sürüm uyuşmuyor: plugin.json "{manifest}" diyor ama {market} plugins[{index}].version '
    '"{entry}" diyor. Kurulumda plugin.json kazanır; etiketlemeden önce pazar girdisini '
    '"{manifest}" yap (ya da kaldır).'
)
ERR_NOT_GIT = "Git deposu değil: {path}"
ERR_DIRTY = (
    "Bu sürümü etkileyen kaydedilmemiş değişiklikler var; etiket istediğin sürümü göstersin diye "
    "önce kaydet (ya da --force): {files}"
)
ERR_TAG_EXISTS = (
    '"{tag}" etiketi yerelde zaten var. plugin.json\'da sürümü artır ya da etiketi taşımak için '
    "--force ile yeniden çalıştır."
)
ERR_GIT = "git {command} başarısız: {error}"


@dataclass(frozen=True, slots=True)
class TagPlan:
    name: str
    version: str
    tag: str
    repo: Path
    message: str
    remote: str

    @property
    def tag_command(self) -> str:
        return f'git -C {self.repo} tag -a {self.tag} -m "{self.message}"'

    @property
    def push_command(self) -> str:
        return f"git -C {self.repo} push {self.remote} refs/tags/{self.tag}"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise PluginError(ERR_GIT.format(command=args[0], error=error)) from error


def _read_json(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PluginError(f"{path}: okunamadı: {error}") from error
    return raw if isinstance(raw, dict) else {}


def _check_marketplace(folder: Path, version: str) -> None:
    """Üst klasörlerdeki pazar bu eklentiyi göreli yolla gösteriyorsa sürümler aynı olmalı."""
    for parent in (folder, *folder.parents):
        market = parent / MARKET_FILE
        if not market.is_file():
            continue
        entries = _read_json(market).get("plugins")
        for index, entry in enumerate(entries if isinstance(entries, list) else ()):
            if not isinstance(entry, dict) or not isinstance(entry.get("source"), str):
                continue
            target = (parent / str(entry["source"])).resolve()
            declared = entry.get("version")
            if target == folder and isinstance(declared, str) and declared != version:
                raise PluginError(
                    ERR_MISMATCH.format(
                        manifest=version, market=MARKET_FILE, index=index, entry=declared
                    )
                )
        return


def plan_tag(
    path: Path, *, message: str = "", remote: str = "origin", force: bool = False
) -> TagPlan:
    """Doğrula ve planla (hiçbir şey yazmaz)."""
    folder = path.expanduser().resolve()
    if not folder.exists():
        raise PluginError(ERR_PATH.format(path=folder))
    manifest_path = folder / PLUGIN_FILE
    if not manifest_path.is_file():
        raise PluginError(ERR_MANIFEST.format(path=manifest_path))
    manifest = _read_json(manifest_path)
    name, version = str(manifest.get("name") or folder.name), manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        raise PluginError(ERR_NO_VERSION.format(path=manifest_path))
    _check_marketplace(folder, version)
    top = _git(folder, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        raise PluginError(ERR_NOT_GIT.format(path=folder))
    repo = Path(top.stdout.strip())
    tag = f"{name}--v{version}"
    if not force:
        dirty = _git(repo, "status", "--porcelain", "--", str(folder)).stdout.split("\n")
        files = [line[3:] for line in dirty if line.strip()]
        if files:
            raise PluginError(ERR_DIRTY.format(files=", ".join(files)))
        if _git(repo, "rev-parse", "-q", "--verify", f"refs/tags/{tag}").returncode == 0:
            raise PluginError(ERR_TAG_EXISTS.format(tag=tag))
    text = message.replace("%s", version) if message else f"{name} {version}"
    return TagPlan(name, version, tag, repo, text, remote)


def create_tag(plan: TagPlan, *, force: bool = False, push: bool = False) -> None:
    flags = ["-f"] if force else []
    done = _git(plan.repo, "tag", "-a", *flags, plan.tag, "-m", plan.message)
    if done.returncode != 0:
        raise PluginError(ERR_GIT.format(command="tag", error=done.stderr.strip()))
    if push:
        sent = _git(plan.repo, "push", plan.remote, f"refs/tags/{plan.tag}")
        if sent.returncode != 0:
            raise PluginError(ERR_GIT.format(command="push", error=sent.stderr.strip()))

"""`archive`, `npm` ve `command` eklenti kaynaklarını çekme (Claude Code, #399/#381).

- archive: https zip indirilir (yönlendirme her adımda yeniden denetlenir), `sha256` pini
  doğrulanır, arşiv güvenli açılır (mutlak yol/`..`/sembolik bağ reddi, 20.000 girdi/256 MiB);
  sürüm kimliği özetin ilk 12 karakteri. `headersHelper` komutu (stdout'a JSON başlık nesnesi)
  ancak gösterilip onaylandıktan sonra çalışır.
- npm: `npm pack <paket>[@sürüm] --ignore-scripts [--registry]` ile paket indirilir ve
  `package/` klasörü açılır (paket betikleri ÇALIŞMAZ). Sürüm `unknown` (Claude loading.md).
- command: kullanıcıya gösterilip onaylanan komut kabukta, ev klasöründen çalışır; stdout tek
  satır mutlak klasör yolu olmalı. `copy` klasörü kopyalar (içerik karması sürüm kimliğidir),
  `link` klasörü yerinde kullanır.

Onay (`ShownCommand`): Claude'daki gibi `-y` gösterilen komutu, `--accept-command <sha256>`
yalnız daha önce `--json` ile bildirilen tam o komutu (eklenti + komut + kip/arşiv adresi +
katalog sürümü) kabul eder; katalog değişirse özet değişir ve yeniden gösterilir.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http.client import HTTPMessage
from pathlib import Path
from typing import IO

from ..config.keys import environ_snapshot
from ..config.plugin_archive import MAX_BYTES, extract_zip_into
from ..core.plugin_marketplace import MarketplaceSource
from ..core.plugin_source_kinds import (
    COMMAND_DEFAULT_TIMEOUT_S,
    HEADER_PREFIX,
    archive_url_allowed,
)
from ..core.plugins import PluginError

KIND_COMMAND = "command_source"
KIND_HELPER = "entry_helper"
FETCH_TIMEOUT_S = 120.0
NPM_TIMEOUT_S = 300.0

ERR_REFUSED = (
    'Eklenti "{plugin}" pazarın bildirdiği bir komutu çalıştırıyor ve onaylanmadı: {command}\n'
    "Onaylamak için -y ya da --accept-command {sha} (komut özeti) verin."
)
ERR_DECLINED = "Aborted."
ERR_DIGEST = "Arşiv özeti uyuşmuyor ({url}): beklenen {expected}, gelen {actual}"
ERR_DOWNLOAD = "Arşiv indirilemedi ({url}): {error}"
ERR_REDIRECT = "Arşiv yönlendirmesi izin verilmeyen adrese gidiyor: {url}"
ERR_COMMAND_RUN = "Kaynak komutu başarısız ({command}): {error}"
ERR_COMMAND_OUTPUT = (
    "Kaynak komutu stdout'a tek satır mutlak klasör yolu basmalı; gelen: {output!r}"
)
ERR_HELPER_OUTPUT = "headersHelper çıktısı JSON başlık nesnesi değil: {error}"
ERR_NPM = "npm paketi indirilemedi ({package}): {error}"
ERR_NO_NPM = "npm bulunamadı: npm kaynaklı eklenti için Node.js/npm kurulu olmalı"


class CommandRefusedError(PluginError):
    """Pazarın bildirdiği komut onaylanmadı (`failureCode: command_source_refused`)."""

    def __init__(self, message: str, shown: ShownCommand) -> None:
        super().__init__(message)
        self.shown = shown


@dataclass(frozen=True, slots=True)
class ShownCommand:
    """Kullanıcıya gösterilen komut; `sha256` `--accept-command` değeridir."""

    kind: str
    plugin_id: str
    command: str
    mode: str = ""
    archive_url: str = ""
    catalog_revision: str = ""

    @property
    def sha256(self) -> str:
        last = self.mode if self.kind == KIND_COMMAND else self.archive_url
        parts = [self.kind, self.plugin_id, self.command, last, self.catalog_revision]
        text = json.dumps(parts, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": self.kind,
            "pluginId": self.plugin_id,
            "command": self.command,
            "catalogRevision": self.catalog_revision,
            "sha256": self.sha256,
        }
        if self.kind == KIND_COMMAND:
            payload["mode"] = self.mode
        else:
            payload["archiveUrl"] = self.archive_url
        return payload


CommandConsent = Callable[[ShownCommand], bool]


def accept_by_sha(expected: str) -> CommandConsent:
    """`--accept-command <sha256>`: yalnız bu özetli komutu kabul et."""
    wanted = expected.strip().lower()
    return lambda shown: shown.sha256 == wanted


def require_consent(shown: ShownCommand, consent: CommandConsent | None) -> None:
    if consent is None or not consent(shown):
        raise CommandRefusedError(
            ERR_REFUSED.format(plugin=shown.plugin_id, command=shown.command, sha=shown.sha256),
            shown,
        )


# --- archive ------------------------------------------------------------------ #


class _CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        if not archive_url_allowed(newurl):
            raise PluginError(ERR_REDIRECT.format(url=newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _helper_headers(command: str) -> dict[str, str]:
    output = _run_shell(command, COMMAND_DEFAULT_TIMEOUT_S)
    try:
        raw = json.loads(output)
    except ValueError as error:
        raise PluginError(ERR_HELPER_OUTPUT.format(error=error)) from error
    if not isinstance(raw, Mapping):
        raise PluginError(ERR_HELPER_OUTPUT.format(error="nesne değil"))
    return {str(k): str(v) for k, v in raw.items()}


def _download(url: str, headers: Mapping[str, str], target: Path) -> str:
    """İndir, boyutu sınırla; sha256 özeti döner."""
    opener = urllib.request.build_opener(_CheckedRedirect)
    request = urllib.request.Request(url, headers={"User-Agent": "fusion-cli", **headers})
    sha = hashlib.sha256()
    read = 0
    try:
        with opener.open(request, timeout=FETCH_TIMEOUT_S) as response, target.open("wb") as out:
            while block := response.read(1 << 20):
                read += len(block)
                if read > MAX_BYTES:
                    raise PluginError(ERR_DOWNLOAD.format(url=url, error="256 MiB sınırı"))
                sha.update(block)
                out.write(block)
    except (OSError, ValueError) as error:
        raise PluginError(ERR_DOWNLOAD.format(url=url, error=error)) from error
    return sha.hexdigest()


def fetch_archive(
    source: MarketplaceSource,
    workspace: Path,
    *,
    plugin_id: str,
    revision: str,
    consent: CommandConsent | None,
) -> tuple[Path, str]:
    """(eklenti kökü, sha256 özeti)."""
    url = source.location
    if not archive_url_allowed(url):
        raise PluginError(ERR_DOWNLOAD.format(url=url, error="izin verilmeyen adres"))
    headers = {
        key.removeprefix(HEADER_PREFIX): value
        for key, value in source.options
        if key.startswith(HEADER_PREFIX)
    }
    helper = source.option("headersHelper")
    if helper:
        shown = ShownCommand(
            KIND_HELPER, plugin_id, helper, archive_url=url, catalog_revision=revision
        )
        require_consent(shown, consent)
        headers.update(_helper_headers(helper))
    target = workspace / "arsiv.zip"
    digest = _download(url, headers, target)
    pin = source.option("sha256")
    if pin and pin != digest:
        raise PluginError(ERR_DIGEST.format(url=url, expected=pin[:12], actual=digest[:12]))
    root = extract_zip_into(target, workspace / "acilan")
    target.unlink(missing_ok=True)
    return root, digest


# --- npm ------------------------------------------------------------------------ #


def fetch_npm(source: MarketplaceSource, workspace: Path) -> Path:
    """`npm pack` ile indir ve aç; eklenti kökü (`package/`)."""
    npm = shutil.which("npm")
    if npm is None:
        raise PluginError(ERR_NO_NPM)
    spec = source.location
    if source.ref and not spec.startswith((".", "/", "~")) and ":" not in spec:
        spec = f"{spec}@{source.ref}"
    args = [npm, "pack", spec, "--json", "--ignore-scripts", "--pack-destination", str(workspace)]
    if source.option("registry"):
        args += ["--registry", source.option("registry")]
    try:
        process = subprocess.run(
            args,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=NPM_TIMEOUT_S,
            env=environ_snapshot(),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PluginError(ERR_NPM.format(package=spec, error=error)) from error
    if process.returncode != 0:
        raise PluginError(ERR_NPM.format(package=spec, error=process.stderr.strip()[-300:]))
    tarballs = sorted(workspace.glob("*.tgz"))
    if not tarballs:
        raise PluginError(ERR_NPM.format(package=spec, error="paket arşivi yok"))
    destination = workspace / "npm"
    try:
        with tarfile.open(tarballs[0]) as archive:
            archive.extractall(destination, filter="data")
    except (OSError, tarfile.TarError) as error:
        raise PluginError(ERR_NPM.format(package=spec, error=error)) from error
    package = destination / "package"
    return package if package.is_dir() else destination


# --- command --------------------------------------------------------------------- #


def _run_shell(command: str, timeout: float) -> str:
    try:
        process = subprocess.run(
            command,
            shell=True,  # kullanıcı gördü ve onayladı (Claude: platform kabuğu)
            cwd=Path.home(),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environ_snapshot(),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PluginError(ERR_COMMAND_RUN.format(command=command, error=error)) from error
    if process.returncode != 0:
        detail = process.stderr.strip()[-300:] or f"çıkış {process.returncode}"
        raise PluginError(ERR_COMMAND_RUN.format(command=command, error=detail))
    return process.stdout


def run_command_source(
    source: MarketplaceSource,
    *,
    plugin_id: str,
    revision: str,
    consent: CommandConsent | None,
) -> Path:
    """Onaylat, çalıştır; basılan mutlak klasör yolu."""
    mode = source.option("mode", "copy")
    shown = ShownCommand(KIND_COMMAND, plugin_id, source.location, mode, catalog_revision=revision)
    require_consent(shown, consent)
    timeout = float(source.option("timeout", str(COMMAND_DEFAULT_TIMEOUT_S)))
    lines = [line for line in _run_shell(source.location, timeout).splitlines() if line.strip()]
    path = Path(lines[0].strip()) if len(lines) == 1 else None
    if path is None or not path.is_absolute() or not path.is_dir():
        raise PluginError(ERR_COMMAND_OUTPUT.format(output="\n".join(lines)[:200]))
    return path


def catalog_revision(manifest: Path) -> str:
    """Katalog sürümü: pazar bildiriminin içerik özeti (yenileme değiştirirse onay yenilenir)."""
    try:
        return hashlib.sha256(manifest.read_bytes()).hexdigest()[:16]
    except OSError:
        return f"unreadable:{os.getpid()}"

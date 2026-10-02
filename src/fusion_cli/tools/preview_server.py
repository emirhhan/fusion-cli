"""Projeyi yerel bir sunucuda ÇALIŞTIRIP kullanıcıya açılabilir adres ver.

Ölçüldü (2 Ekim 2026, "sneaksup" sohbeti): kullanıcı "ekstra bir şey kurmadan
önizlememi sağla" dedi; Fusion bir `preview.html` yazıp bıraktı, siteyi hiç açmadı.
Claude/Codex bu noktada sunucuyu kendisi başlatır ve adres verir.

Proje türü dosyalardan anlaşılır, komut uydurulmaz:

- **wordpress** — `wp-content/` ya da `wp-config.php` (çekirdek yoksa `wordpress_setup` kurar)
- **php** — kökte `index.php`
- **node** — `package.json`'da `dev` ya da `start` betiği
- **static** — kökte ya da tek klasörde `.html`

Sunucular `fusion app` süreci yaşadıkça açık kalır (kullanıcı adresi açabilsin);
süreç kapanırken hepsi kapatılır. Aynı kök için ikinci çağrı çalışanı yeniden kullanır.
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import functools
import http.server
import json
import os
import signal
import socket
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from .wordpress_setup import has_core, is_wordpress_project, php_env

#: Sunucunun yanıt vermeye başlaması için tanınan süre. `next dev` soğuk başlangıçta
#: ~2 sn + ilk derleme birkaç sn (ölçüldü, `browser_verify`); php -S anında açılır.
SERVER_READY_S = 45.0
#: `npm install` için süre: bağımlılık indirmesi dakikalar sürebilir.
NPM_INSTALL_TIMEOUT_S = 300.0
#: Önizleme portlarının tercih edilen başlangıcı; doluysa sonrakiler denenir.
#: Sabit aralık kullanıcıya hep benzer adres verir (8000/3000 genelde başka işte).
PREVIEW_PORT_START = 8770
PREVIEW_PORT_SPAN = 30


class PreviewKind(StrEnum):
    WORDPRESS = "wordpress"
    PHP = "php"
    NODE = "node"
    STATIC = "static"


class PreviewError(RuntimeError):
    """Önizleme başlatılamadı; mesaj modele olduğu gibi gider (ne yapılacağıyla)."""


@dataclass
class RunningPreview:
    root: Path
    kind: PreviewKind
    url: str
    process: asyncio.subprocess.Process | None = None
    httpd: http.server.ThreadingHTTPServer | None = None
    #: Son yoklamanın özeti (doğrulama kapısı okur).
    last_probe: dict[str, object] = field(default_factory=dict)

    @property
    def alive(self) -> bool:
        if self.httpd is not None:
            return True
        return self.process is not None and self.process.returncode is None


_RUNNING: dict[Path, RunningPreview] = {}


def detect_kind(root: Path) -> PreviewKind | None:
    """Kökün nasıl çalıştırılacağı; tanınmıyorsa None."""
    if is_wordpress_project(root):
        return PreviewKind.WORDPRESS
    if (root / "index.php").is_file():
        return PreviewKind.PHP
    if _node_script(root) is not None:
        return PreviewKind.NODE
    if static_entry(root) is not None:
        return PreviewKind.STATIC
    return None


def static_entry(root: Path) -> str | None:
    """Statik sitenin açılış sayfası (köke göreli); yoksa None."""
    if (root / "index.html").is_file():
        return "index.html"
    pages = sorted(root.glob("*.html")) or sorted(root.glob("*/index.html"))
    return pages[0].relative_to(root).as_posix() if pages else None


def running(root: Path) -> RunningPreview | None:
    preview = _RUNNING.get(root.resolve())
    return preview if preview is not None and preview.alive else None


def needs_wordpress_setup(root: Path) -> bool:
    return is_wordpress_project(root) and (
        not has_core(root) or not (root / "wp-config.php").is_file()
    )


def free_port() -> int:
    """Tercih edilen aralıkta boş port; hepsi doluysa işletim sisteminin verdiği."""
    for port in range(PREVIEW_PORT_START, PREVIEW_PORT_START + PREVIEW_PORT_SPAN):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def start(
    root: Path, kind: PreviewKind, port: int, *, php: str | None, entry: str = ""
) -> RunningPreview:
    """Sunucuyu başlat ve yanıt verene kadar bekle. Çalışan varsa onu döndür."""
    root = await asyncio.to_thread(root.resolve)
    existing = running(root)
    if existing is not None:
        return existing
    base = f"http://127.0.0.1:{port}"
    if kind is PreviewKind.STATIC:
        preview = RunningPreview(root, kind, f"{base}/{entry}", httpd=_static_server(root, port))
    elif kind in (PreviewKind.PHP, PreviewKind.WORDPRESS):
        if php is None:
            raise PreviewError("PHP bulunamadı. Kurmak için: `brew install php`.")
        process = await _spawn([php, "-S", f"127.0.0.1:{port}", "-t", str(root)], root)
        preview = RunningPreview(root, kind, f"{base}/", process=process)
    else:
        command = await _node_command(root, port)
        process = await _spawn(command, root, extra_env={"PORT": str(port)})
        preview = RunningPreview(root, kind, f"{base}/", process=process)
    if not await wait_until_serving(preview.url):
        stop(preview)
        raise PreviewError(
            f"Sunucu {SERVER_READY_S:.0f} sn içinde yanıt vermedi ({kind.value}). "
            "Kabukta aynı komutu çalıştırıp hatasına bak."
        )
    _RUNNING[root] = preview
    return preview


def stop(preview: RunningPreview) -> None:
    if preview.httpd is not None:
        preview.httpd.shutdown()
        preview.httpd.server_close()
        preview.httpd = None
    if preview.process is not None and preview.process.returncode is None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            if sys.platform == "win32":
                preview.process.terminate()
            else:
                os.killpg(preview.process.pid, signal.SIGTERM)
    _RUNNING.pop(preview.root, None)


@atexit.register
def stop_all() -> None:
    """Süreç kapanırken hiçbir sunucu sahipsiz kalmasın."""
    for preview in list(_RUNNING.values()):
        stop(preview)


async def wait_until_serving(url: str, timeout_s: float = SERVER_READY_S) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        if await asyncio.to_thread(_responds, url):
            return True
        await asyncio.sleep(0.5)
    return False


def _responds(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5):
            return True
    except urllib.error.HTTPError:
        return True  # 404/500 de "sunucu ayakta" demektir; içerik yoklamada ölçülür
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _static_server(root: Path, port: int) -> http.server.ThreadingHTTPServer:
    """Statik dosya sunucusu süreç İÇİNDE çalışır: paketli uygulamada `python -m` yok."""
    handler = functools.partial(_QuietHandler, directory=str(root))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        del format, args


async def _spawn(
    command: list[str], root: Path, extra_env: dict[str, str] | None = None
) -> asyncio.subprocess.Process:
    env = {**php_env(), **(extra_env or {})}
    return await asyncio.create_subprocess_exec(
        *command,
        cwd=str(root),
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        # Kendi süreç grubu: npm'in başlattığı alt süreçler de birlikte kapanır.
        start_new_session=sys.platform != "win32",
    )


def _node_script(root: Path) -> str | None:
    try:
        scripts = json.loads((root / "package.json").read_text(encoding="utf-8")).get("scripts")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(scripts, dict):
        return None
    return next((name for name in ("dev", "start") if isinstance(scripts.get(name), str)), None)


async def _node_command(root: Path, port: int) -> list[str]:
    script = _node_script(root)
    if script is None:
        raise PreviewError("package.json'da `dev` ya da `start` betiği yok.")
    if not (root / "node_modules").is_dir():
        install = await _spawn(["npm", "install"], root)
        try:
            await asyncio.wait_for(install.wait(), timeout=NPM_INSTALL_TIMEOUT_S)
        except TimeoutError as exc:
            install.kill()
            raise PreviewError("`npm install` zaman aşımına uğradı.") from exc
        if install.returncode != 0:
            raise PreviewError("`npm install` başarısız oldu; kabukta çalıştırıp hataya bak.")
    return ["npm", "run", script, "--", "--port", str(port)]

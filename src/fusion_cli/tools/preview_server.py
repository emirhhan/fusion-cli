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
import io
import json
import os
import signal
import socket
import ssl
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO

from ..core.process_control import terminate_async_process_tree
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
#: Önizleme sunucusunun cevap verdiği Host başlıkları (port hariç). Başka bir ad,
#: DNS yeniden bağlama ile yerel sunucuya erişmeye çalışan bir sayfanın işaretidir.
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})
#: `php -S`'e yönlendirici olarak verilen betik (paket verisi; kuralları aşağıdakiyle aynı).
PHP_ROUTER = Path(__file__).parent / "assets" / "preview_router.php"


class PreviewKind(StrEnum):
    WORDPRESS = "wordpress"
    PHP = "php"
    NODE = "node"
    STATIC = "static"
    #: Kullanıcının `.fusion/launch.json` ile tanımladığı sunucu (bkz. `preview_launch`).
    LAUNCH = "launch"


class PreviewError(RuntimeError):
    """Önizleme başlatılamadı; mesaj modele olduğu gibi gider (ne yapılacağıyla)."""


@dataclass
class RunningPreview:
    root: Path
    kind: PreviewKind
    url: str
    process: asyncio.subprocess.Process | None = None
    #: Sürecin stdout/stderr günlüğü; hata mesajına kuyruğu eklenir.
    log_path: Path | None = None
    httpd: http.server.ThreadingHTTPServer | None = None
    #: Son yoklamanın özeti (doğrulama kapısı okur).
    last_probe: dict[str, object] = field(default_factory=dict)
    #: Süreç bizim değil: zaten çalışan sunucuya bağlanıldı (`launch.json` yalnız `url`).
    attached: bool = False
    #: Eşzamanlı başlatmalar aynı readiness sonucuna katılır; hazır olmadan URL verilmez.
    starting: asyncio.Future[RunningPreview] | None = None
    #: Başlatma anı (monotonik); "en son başlatılan önizleme" seçimi buna bakar.
    started_at: float = field(default_factory=time.monotonic)

    @property
    def alive(self) -> bool:
        if self.httpd is not None or self.attached:
            return True
        return self.process is not None and self.process.returncode is None


_RUNNING: dict[Path, RunningPreview] = {}


def request_block_reason(path: str, host_header: str | None) -> str | None:
    """Önizleme sunucusunun reddedeceği istek için Türkçe gerekçe; geçerliyse None.

    İki kural: Host yerel değilse (DNS yeniden bağlama) ve yol bileşenlerinden biri
    nokta ile başlıyorsa (`.fusion/onizleme-giris.txt`, `.env`, `.git/`) reddedilir.
    `assets/preview_router.php` aynı kuralı `php -S` için uygular; ikisi birlikte değişir.
    """
    host = (host_header or "").lower()
    host = host.split("]")[0] + "]" if host.startswith("[") else host.split(":")[0]
    if host not in LOCAL_HOSTS:
        return f"yerel olmayan Host başlığı ({host_header or 'yok'})"
    decoded = urllib.parse.unquote(urllib.parse.urlsplit(path).path).replace("\\", "/")
    if any(part.startswith(".") for part in decoded.split("/")):
        return "nokta ile başlayan yol (gizli dosya)"
    return None


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
    return preview if preview is not None and preview.alive and preview.starting is None else None


def needs_wordpress_setup(root: Path) -> bool:
    return is_wordpress_project(root) and (
        not has_core(root) or not (root / "wp-config.php").is_file()
    )


def free_port() -> int:
    """Tercih edilen aralıkta boş port; hepsi doluysa işletim sisteminin verdiği.

    Boşluk BIND ederek sınanır: bağlanma denemesinin reddedilmesi portun boş olduğunu
    kanıtlamaz (ölçüldü: macOS sharingd 8770'i IPv6'da tutarken IPv4 bağlantısı
    reddediliyor, sunucu ise bind'de "Address already in use" ile düşüyordu).
    """
    for port in range(PREVIEW_PORT_START, PREVIEW_PORT_START + PREVIEW_PORT_SPAN):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def start(
    root: Path, kind: PreviewKind, port: int, *, php: str | None, entry: str = ""
) -> RunningPreview:
    """Sunucuyu başlat ve yanıt verene kadar bekle. Çalışan varsa onu döndür."""
    root = await asyncio.to_thread(root.resolve)
    pending = _RUNNING.get(root)
    if pending is not None and pending.starting is not None:
        return await asyncio.shield(pending.starting)
    existing = running(root)
    if existing is not None:
        return existing
    ready = asyncio.get_running_loop().create_future()
    preview = RunningPreview(root, kind, f"http://127.0.0.1:{port}/", starting=ready)
    _RUNNING[root] = preview
    try:
        command = await _launch_preview(preview, port, php=php, entry=entry)
        if not await wait_until_serving(preview.url, process=preview.process):
            raise PreviewError(_failure_message(preview, command))
        preview.starting = None
        ready.set_result(preview)
        return preview
    except BaseException as error:
        try:
            await dispose(preview)
        finally:
            if isinstance(error, asyncio.CancelledError):
                ready.cancel()
            else:
                ready.set_exception(error)
                ready.exception()  # Bekleyen başka çağrı olmasa da hata tüketilmiş olsun.
        raise


async def _launch_preview(
    preview: RunningPreview, port: int, *, php: str | None, entry: str
) -> list[str]:
    """Kaynak sahipliği kaydedilmiş örneği başlat; await boşluğunda ikinci süreç açılmaz."""
    root, kind = preview.root, preview.kind
    if kind is PreviewKind.STATIC:
        preview.url += entry
        preview.httpd = _static_server(root, port)
        return []
    if kind in (PreviewKind.PHP, PreviewKind.WORDPRESS):
        if php is None:
            raise PreviewError("PHP bulunamadı. Kurmak için: `brew install php`.")
        command = [
            php, "-d", "display_errors=1", "-S", f"127.0.0.1:{port}", "-t", str(root),
            str(PHP_ROUTER),
        ]  # fmt: skip
        preview.process, preview.log_path = await spawn_logged(command, root)
    else:
        command = await _node_command(root, port)
        preview.process, preview.log_path = await spawn_logged(
            command, root, extra_env={"PORT": str(port)}
        )
    return command


async def dispose(preview: RunningPreview) -> None:
    """Başlatılamayan önizlemenin sahipli kaynaklarını kapat ve gerçek çıkışını bekle."""
    try:
        if preview.process is not None:
            await terminate_async_process_tree(preview.process)
        if preview.httpd is not None:
            await asyncio.to_thread(terminate, preview)
    finally:
        if preview.log_path is not None:
            preview.log_path.unlink(missing_ok=True)
        if _RUNNING.get(preview.root) is preview:
            _RUNNING.pop(preview.root, None)


def stop(preview: RunningPreview) -> None:
    terminate(preview)
    _RUNNING.pop(preview.root, None)


def terminate(preview: RunningPreview) -> None:
    """Sunucuyu kapat ve günlüğünü sil; defterden DÜŞÜRMEZ (adlı önizlemelerin defteri ayrı)."""
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
    if preview.log_path is not None:
        preview.log_path.unlink(missing_ok=True)


def all_running() -> tuple[RunningPreview, ...]:
    """Türü dosyalardan anlaşılan çalışan önizlemeler (en eski önce)."""
    return tuple(preview for preview in _RUNNING.values() if preview.alive)


@atexit.register
def stop_all() -> None:
    """Süreç kapanırken hiçbir sunucu sahipsiz kalmasın."""
    for preview in list(_RUNNING.values()):
        stop(preview)


def _log_tail(path: Path | None, chars: int = 1_500) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-chars:].strip()
    except OSError:
        return ""


def _failure_message(preview: RunningPreview, command: list[str]) -> str:
    """Sunucu ayağa kalkmadı: süreç öldüyse çıkış kodunu, komutu ve çıktı kuyruğunu göster.

    Eskiden süreç hemen ölse bile 45 sn beklenip "kabukta aynı komutu çalıştır" deniyordu;
    komut satırı (port, ortam) ve hata çıktısı modele verilmiyordu (ölçüldü, 30 Ekim).
    """
    process = preview.process
    tail = _log_tail(preview.log_path)
    kind = preview.kind.value
    if process is not None and process.returncode is not None:
        head = f"Sunucu süreci hemen kapandı (çıkış kodu {process.returncode}, {kind})."
    else:
        head = f"Sunucu {SERVER_READY_S:.0f} sn içinde yanıt vermedi ({kind})."
    detail = f"\nKomut: {' '.join(command)}"
    if tail:
        detail += f"\n[sürecin son çıktısı]\n{tail}"
    hint = (
        "\nBetik `--port`'u yok sayıyor olabilir (CRA, düz node/Express): PORT ortam "
        "değişkenini okuyacak şekilde ayarla."
        if preview.kind not in (PreviewKind.STATIC, PreviewKind.PHP, PreviewKind.WORDPRESS)
        else ""
    )
    return head + detail + hint


async def wait_until_serving(
    url: str,
    timeout_s: float = SERVER_READY_S,
    *,
    process: asyncio.subprocess.Process | None = None,
) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        if process is not None and process.returncode is not None:
            return False  # süreç öldü: beklemek boşuna
        if await asyncio.to_thread(responds, url):
            return True
        await asyncio.sleep(0.5)
    return False


def loopback_tls_context() -> ssl.SSLContext:
    """Yalnız loopback için: yerel geliştirme sertifikası (mkcert, basicSsl) imzasız olabilir."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def tls_context_for(url: str) -> ssl.SSLContext | None:
    """`https://localhost` için sorgusuz bağlam; uzak ya da http adreste None (doğrulama sürer).

    Ölçüldü (31 Ekim, inceleme): `responds` varsayılan doğrulamayla bağlanıyordu; kendinden
    imzalı yerel https sunucusu launch.json'da hiç "ayakta" sayılmıyordu. Venv Python'u macOS
    Keychain'e bakmadığı için mkcert kökü de güvenilmez.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
    except ValueError:
        return None
    if parsed.scheme != "https":
        return None
    if (f"[{host}]" if ":" in host else host) not in LOCAL_HOSTS:
        return None
    return loopback_tls_context()


def responds(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5, context=tls_context_for(url)):
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
    def send_head(self) -> io.BytesIO | BinaryIO | None:
        reason = request_block_reason(self.path, self.headers.get("Host"))
        if reason is not None:
            self.send_error(403, "Forbidden", explain=reason)
            return None
        return super().send_head()

    def log_message(self, format: str, *args: object) -> None:
        del format, args


async def spawn_logged(
    command: list[str],
    root: Path,
    extra_env: dict[str, str] | None = None,
    *,
    env_base: dict[str, str] | None = None,
) -> tuple[asyncio.subprocess.Process, Path]:
    """Süreci başlat; stdout/stderr geçici bir günlüğe gider (hata anında kuyruğu okunur).

    `env_base` verilirse `php_env()` yerine o ortam kullanılır (süzülmüş ortam için).
    """
    handle, name = tempfile.mkstemp(prefix="fusion-preview-", suffix=".log")
    log_path = Path(name)
    try:
        with os.fdopen(handle, "wb") as log:
            process = await _spawn(command, root, extra_env, output=log, env_base=env_base)
    except BaseException:
        log_path.unlink(missing_ok=True)  # noqa: ASYNC240 - tek küçük unlink, hata yolunda
        raise
    return process, log_path


async def _spawn(
    command: list[str],
    root: Path,
    extra_env: dict[str, str] | None = None,
    output: BinaryIO | None = None,
    *,
    env_base: dict[str, str] | None = None,
) -> asyncio.subprocess.Process:
    env = {**(env_base if env_base is not None else php_env()), **(extra_env or {})}
    creation = asyncio.create_task(
        asyncio.create_subprocess_exec(
            *command,
            cwd=str(root),
            env=env,
            stdout=output if output is not None else asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.STDOUT if output is not None else asyncio.subprocess.DEVNULL,
            # Kendi süreç grubu: npm'in başlattığı alt süreçler de birlikte kapanır.
            start_new_session=sys.platform != "win32",
        )
    )
    try:
        return await asyncio.shield(creation)
    except asyncio.CancelledError:
        # Oluşturma await'i iptal olsa da başlamış süreç bize aittir.
        process = await creation
        await terminate_async_process_tree(process)
        raise


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
            await terminate_async_process_tree(install)
            raise PreviewError("`npm install` zaman aşımına uğradı.") from exc
        except BaseException:
            await terminate_async_process_tree(install)
            raise
        if install.returncode != 0:
            raise PreviewError("`npm install` başarısız oldu; kabukta çalıştırıp hataya bak.")
    return ["npm", "run", script, "--", "--port", str(port)]

"""`.claude/launch.json`: kullanıcının tanımladığı geliştirme sunucusu yapılandırmaları.

#440: Claude Code'un dosyası birincildir (yazılan da odur); `.fusion/launch.json` eski ad olarak
okunur. `program`/`args`, `port` varsayılanı 3000, `${workspaceFolder}`, `--port`/`-p` yeniden
yazımı, yorumlu JSON ve üst düzey `autoVerify` (varsayılan açık) `tools/launch_json.py`'dedir.

Ölçüldü (31 Ekim, P-041): önizleme sunucusu yalnız dosyalardan ANLAŞILAN türleri
(WordPress, PHP, Node `dev`/`start`, statik) başlatabiliyordu; monorepo, özel port, Vite
dışı betik ya da zaten çalışan bir sunucuya "bağlan" için yol yoktu. Claude Code
masaüstünün `.claude/launch.json` dosyasıyla aynı alanlar kullanılır (`name`,
`runtimeExecutable`, `runtimeArgs`, `port`, `url`, `cwd`, `env`); uyumluluk için
`.claude/launch.json` da OKUNUR ama yazılmaz. Örnek::

    {"version": "0.0.1", "configurations": [
      {"name": "web", "runtimeExecutable": "npm", "runtimeArgs": ["run", "dev"], "port": 5173},
      {"name": "api", "url": "http://localhost:8000"}
    ]}

- `runtimeExecutable` varsa komut KABUKSUZ (`exec`) başlatılır, `PORT` ortam değişkeni verilir.
- Port doluysa `autoPort` (yok/true) sıradaki boş portu seçer; `false` başlatmaz
  (`tools.preview_ports`). `runtimeArgs` içindeki `${port}` seçilen portla değişir.
- Yalnız `url` varsa hiçbir şey başlatılmaz; çalışan sunucuya bağlanılır.
- Adresler yerel (loopback) olmalıdır: önizleme paneli yalnız bunları gömer.
- Komutlu yapılandırma yalnız dosya GÜVENİLİRSE çalışır (`fusion trust` ya da panelden
  "Güven ve başlat"); indirilmiş bir deponun launch.json'u onaysız komut çalıştıramaz.
  Ölçüldü (31 Ekim): `.claude/launch.json` içindeki `/bin/sh -c …` komutu, ajan `start_preview
  name=` çağırınca `config/trust.py` denetiminden geçmeden tam ortamla başlıyordu.
- Geçersiz TEK kayıt dosyanın tamamını düşürmez: atlanır ve `warnings` ile bildirilir.

Sunucular `fusion app` süreci yaşadıkça açık kalır; süreç kapanırken hepsi kapatılır.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlparse

from ..config import trust
from ..core.errors import FusionError
from ..core.redaction import SECRET_ENV_NAME
from . import launch_json, preview_ports, preview_server
from .preview_server import LOCAL_HOSTS, PreviewError, PreviewKind, RunningPreview
from .wordpress_setup import php_env

#: Okunma sırası: Claude Code'un dosyası önce, Fusion'ın eski adı uyumluluk için.
LAUNCH_FILES: tuple[str, ...] = tuple(path.as_posix() for path in trust.PROJECT_LAUNCH_FILES)
#: Yazılan/örneklenen dosya (`.claude/launch.json`).
LAUNCH_FILE = LAUNCH_FILES[0]
#: Yapılandırma adı: menüde ve `start_preview name=` içinde kullanılır; kabuğa gitmez.
#: İç boşluğa izin verilir ("Web Server" Claude Code'da olağan); baş/son boşluk kırpılır.
_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:\- ]{0,63}$")
MAX_CONFIGURATIONS = 20
MAX_ARGS = 40
MAX_ENV = 40
#: Tanınan alanlar; diğerleri yok sayılır ve uyarı olarak bildirilir.
KNOWN_FIELDS = frozenset(
    {
        "name",
        "runtimeExecutable",
        "runtimeArgs",
        "port",
        "url",
        "cwd",
        "env",
        "type",
        "request",
        "autoPort",
        "program",
        "args",
    }
)
#: Alt sürece GEÇMEYEN ortam değişkenleri: sağlayıcı anahtarları ve sırlar. Dev sunucu
#: bunlara ihtiyaç duymaz; `env` alanıyla açıkça verilen değer yine geçer.
_SECRET_ENV = SECRET_ENV_NAME
_ALLOW_ENV = frozenset({"npm_config_", "NODE_", "PYTHON", "PATH", "HOME", "LANG", "LC_"})

UNTRUSTED_HINT = (
    "{source} içindeki '{name}' komutu ({command}) çalıştırılmadı: bu dosya güvenilir değil. "
    'Komutu okuduysan `fusion trust` (ya da panelde "Güven ve başlat") ile onayla; yalnız '
    "`url` ile çalışan sunucuya bağlanma onay gerektirmez."
)


#: Port kaydırıldı ama sunucu yeni portta açılmadı: büyük olasılıkla sabit porta bağlanıyor.
PORT_MOVED_HINT = (
    "İstenen port dolu olduğu için başka port seçildi; sunucu PORT ortam değişkenini okumuyorsa "
    '`runtimeArgs` içine `"--port", "${port}"` ekle ya da `"autoPort": false` yaz.'
)


class LaunchConfigError(FusionError):
    """`launch.json` okunamadı ya da bir yapılandırma geçersiz; mesaj kullanıcıya gider."""


class LaunchUntrustedError(LaunchConfigError):
    """Komutlu yapılandırma var ama dosya güven kaydında değil (`fusion trust`)."""


@dataclass(frozen=True, slots=True)
class LaunchConfig:
    """Tek bir sunucu yapılandırması (`configurations[]` öğesi)."""

    name: str
    #: Çalıştırılacak ikili (`npm`, `python`, `./bin/dev`); None ise yalnız bağlanılır.
    executable: str | None
    args: tuple[str, ...]
    port: int | None
    #: Açılacak adres; yoksa `http://127.0.0.1:<port>`.
    url: str | None
    #: Köke göreli çalışma klasörü ("" = kök).
    cwd: str = ""
    #: Komuta verilecek ek ortam değişkenleri (`env` alanı).
    env: tuple[tuple[str, str], ...] = ()
    #: Dosya karması güven kaydıyla eşleşiyor; False ise komut çalıştırılmaz (bağlanma serbest).
    trusted: bool = False
    #: Okunduğu dosya (hata metinleri için); elle kurulanda boş.
    source: str = ""
    #: Port doluysa davranış (`autoPort`): None/True sıradaki boş port, False hata.
    auto_port: bool | None = None

    @property
    def is_attach(self) -> bool:
        """Komut yok: zaten çalışan sunucuya bağlan."""
        return self.executable is None

    @property
    def command(self) -> tuple[str, ...]:
        return (self.executable, *self.args) if self.executable else ()

    @property
    def command_text(self) -> str:
        return " ".join(self.command)

    @property
    def address(self) -> str:
        if self.url:
            return self.url
        return f"http://127.0.0.1:{self.port}/"

    @property
    def needs_trust(self) -> bool:
        """Komutlu ama güvenilmeyen: başlatma `LaunchUntrustedError` verir."""
        return not self.is_attach and not self.trusted


@dataclass(frozen=True, slots=True)
class LaunchConfigs:
    configs: tuple[LaunchConfig, ...]
    #: Okunan dosyanın köke göreli yolu; dosya yoksa None.
    source: str | None
    #: Atlanan kayıtlar ve yok sayılan alanlar (kullanıcıya gösterilir, dosyayı düşürmez).
    warnings: tuple[str, ...] = ()
    #: Okunan dosya güven kaydında mı (komutlu yapılandırmalar için gerekir).
    trusted: bool = False
    #: Üst düzey `autoVerify` (Claude Code: varsayılan açık; `false` projede kapatır).
    auto_verify: bool = True

    def get(self, name: str) -> LaunchConfig | None:
        return next((config for config in self.configs if config.name == name), None)

    @property
    def needs_trust(self) -> bool:
        return any(config.needs_trust for config in self.configs)


def launch_file(root: Path) -> Path | None:
    """Varsa okunacak dosya (Fusion'ınki Claude Code'unkinden önce)."""
    for relative in LAUNCH_FILES:
        path = root / relative
        if path.is_file():
            return path
    return None


def load_launch_configs(root: Path) -> LaunchConfigs:
    """Dosyayı oku ve doğrula; dosya yoksa boş liste.

    Bozuk dosya `LaunchConfigError`; ama Fusion dosyası bozukken Claude Code dosyası
    sağlamsa ona düşülür (bozukluk uyarı olur). Tek geçersiz kayıt atlanır.
    """
    ilk_hata: LaunchConfigError | None = None
    for relative in LAUNCH_FILES:
        path = root / relative
        if not path.is_file():
            continue
        try:
            loaded = _load_file(root, path, relative)
        except LaunchConfigError as error:
            ilk_hata = ilk_hata or error
            continue
        if ilk_hata is not None:
            return replace(loaded, warnings=(str(ilk_hata), *loaded.warnings))
        return loaded
    if ilk_hata is not None:
        raise ilk_hata
    return LaunchConfigs((), None)


def auto_verify_enabled(root: Path) -> bool:
    """Projenin launch.json'ı `autoVerify: false` demiyorsa True (Claude: varsayılan açık, #440).

    Dosya yoksa ya da bozuksa açık kalır: doğrulamayı kapatmak açık bir karar ister.
    """
    try:
        return load_launch_configs(root).auto_verify
    except (LaunchConfigError, OSError):
        return True


def _load_file(root: Path, path: Path, source: str) -> LaunchConfigs:
    try:
        raw = json.loads(launch_json.strip_json_comments(path.read_text(encoding="utf-8")))
    except OSError as error:
        raise LaunchConfigError(f"{source} okunamadı: {error}") from error
    except ValueError as error:
        raise LaunchConfigError(f"{source} geçerli JSON değil: {error}") from error
    if not isinstance(raw, dict) or not isinstance(raw.get("configurations"), list):
        raise LaunchConfigError(f"{source}: üst düzeyde `configurations` listesi bekleniyor.")
    items = raw["configurations"]
    if len(items) > MAX_CONFIGURATIONS:
        raise LaunchConfigError(f"{source}: en fazla {MAX_CONFIGURATIONS} yapılandırma olabilir.")
    trusted = trust.is_file_trusted(root, path)
    configs: list[LaunchConfig] = []
    warnings: list[str] = []
    for item in items:
        try:
            config = _parse(source, item, trusted=trusted, warnings=warnings)
        except LaunchConfigError as error:
            warnings.append(f"{error} (kayıt atlandı)")
            continue
        if any(existing.name == config.name for existing in configs):
            warnings.append(f"{source}: '{config.name}' adı tekrar ediyor; ikinci kayıt atlandı.")
            continue
        configs.append(config)
    auto_verify = raw.get("autoVerify", True)
    if not isinstance(auto_verify, bool):
        warnings.append(f"{source}: `autoVerify` true ya da false olmalı; varsayılan (true).")
        auto_verify = True
    return LaunchConfigs(tuple(configs), source, tuple(warnings), trusted, auto_verify)


def find_launch_config(root: Path, name: str) -> LaunchConfig:
    """Adıyla yapılandırma; yoksa mevcut adları sayan `LaunchConfigError`."""
    loaded = load_launch_configs(root)
    config = loaded.get(name)
    if config is not None:
        return config
    if not loaded.configs:
        ek = " ".join(loaded.warnings)
        raise LaunchConfigError(
            (ek + " ")
            if ek
            else f'{LAUNCH_FILE} yok. Örnek: {{"configurations": [{{"name": "web", '
            '"runtimeExecutable": "npm", "runtimeArgs": ["run", "dev"], "port": 5173}]}'
        )
    adlar = ", ".join(config.name for config in loaded.configs)
    raise LaunchConfigError(
        f"'{name}' adlı yapılandırma {loaded.source} içinde yok. Mevcut: {adlar}"
    )


def is_local_url(value: object) -> bool:
    """Önizleme panelinin gömebileceği adres: http/https + loopback (P-041: https yerel)."""
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    host = parsed.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    return parsed.scheme in ("http", "https") and host in LOCAL_HOSTS


def join_local_page(base: str, page: object) -> str:
    """`page` yolunu önizleme adresine ekle; aynı yerel kökende kalmazsa `PreviewError`.

    Ölçüldü (31 Ekim): `urljoin(url, "http://169.254.169.254/…")` temel adresi tümüyle
    değiştiriyor, ölçüm iç ağa istek atıyordu. `page` yalnız yol/sorgu olabilir.
    """
    if not isinstance(page, str) or not page.strip():
        return base
    joined = urljoin(base, page.strip())
    joined_parts, base_parts = urlparse(joined), urlparse(base)
    if (joined_parts.scheme, joined_parts.netloc) != (base_parts.scheme, base_parts.netloc) or (
        not is_local_url(joined)
    ):
        raise PreviewError(
            f"`page` yalnız yol olabilir (ör. /shop/); başka bir adres verilemez: {page.strip()}"
        )
    return joined


def _parse(
    source: str, item: object, *, trusted: bool = False, warnings: list[str] | None = None
) -> LaunchConfig:
    if not isinstance(item, dict):
        raise LaunchConfigError(f"{source}: her yapılandırma bir nesne olmalı.")
    name = item.get("name")
    name = name.strip() if isinstance(name, str) else name
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise LaunchConfigError(
            f"{source}: `name` harf/rakam/alt çizgiyle başlayan, en çok 64 karakterlik ad olmalı."
        )
    executable = item.get("runtimeExecutable")
    if executable is not None and (not isinstance(executable, str) or not executable.strip()):
        raise LaunchConfigError(f"{source} [{name}]: `runtimeExecutable` boş olmayan metin olmalı.")
    raw_args = item.get("runtimeArgs", [])
    program = item.get("program")
    if executable is None and isinstance(program, str) and program.strip():
        # `program` + `args`: doğrudan `node` ile çalışan betik (#440).
        script_args = item.get("args", [])
        if not isinstance(script_args, list):
            raise LaunchConfigError(f"{source} [{name}]: `args` metin listesi olmalı.")
        executable, raw_args = launch_json.program_command(program.strip(), script_args)
        raw_args = list(raw_args)
    if (
        not isinstance(raw_args, list)
        or len(raw_args) > MAX_ARGS
        or not all(isinstance(arg, str) for arg in raw_args)
    ):
        raise LaunchConfigError(
            f"{source} [{name}]: `runtimeArgs` en çok {MAX_ARGS} metinden oluşan liste olmalı."
        )
    port = item.get("port")
    if port is not None and (
        isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536
    ):
        raise LaunchConfigError(f"{source} [{name}]: `port` 1-65535 arası tam sayı olmalı.")
    url = item.get("url")
    if url is not None and not is_local_url(url):
        raise LaunchConfigError(
            f"{source} [{name}]: `url` yerel bir http(s) adresi olmalı (localhost/127.0.0.1); "
            "uzak adresler uygulama içinde önizlenmez."
        )
    if executable is None and url is None:
        raise LaunchConfigError(f"{source} [{name}]: `runtimeExecutable` ya da `url` gerekir.")
    if executable is not None and port is None and url is None:
        port = launch_json.DEFAULT_PORT  # Claude Code: "Defaults to 3000" (#440)
    cwd = item.get("cwd", "")
    if isinstance(cwd, str):
        cwd = launch_json.workspace_relative(cwd)
    if (
        not isinstance(cwd, str)
        or PurePosixPath(cwd).is_absolute()
        or ".." in PurePosixPath(cwd).parts
        or ".." in cwd.replace("\\", "/").split("/")
    ):
        raise LaunchConfigError(f"{source} [{name}]: `cwd` köke göreli olmalı (`..` olmaz).")
    env = _parse_env(source, name, item.get("env"))
    auto_port = item.get("autoPort")
    if auto_port is not None and not isinstance(auto_port, bool):
        raise LaunchConfigError(f"{source} [{name}]: `autoPort` true ya da false olmalı.")
    if warnings is not None:
        bilinmeyen = sorted(key for key in item if key not in KNOWN_FIELDS)
        if bilinmeyen:
            warnings.append(
                f"{source} [{name}]: desteklenmeyen alan(lar) yok sayıldı: {', '.join(bilinmeyen)}."
            )
    return LaunchConfig(
        name=name,
        executable=executable.strip() if isinstance(executable, str) else None,
        args=tuple(raw_args),
        port=port,
        url=url,
        cwd=cwd.strip("/"),
        env=env,
        trusted=trusted,
        source=source,
        auto_port=auto_port,
    )


def _parse_env(source: str, name: str, raw: object) -> tuple[tuple[str, str], ...]:
    if raw is None:
        return ()
    if (
        not isinstance(raw, dict)
        or len(raw) > MAX_ENV
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in raw.items())
        or not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) for k in raw)
    ):
        raise LaunchConfigError(
            f"{source} [{name}]: `env` en çok {MAX_ENV} `AD: değer` metin çiftinden oluşmalı."
        )
    return tuple(sorted(raw.items()))


def launch_env(config: LaunchConfig, base: dict[str, str] | None = None) -> dict[str, str]:
    """Alt sürecin ortamı: PATH/Homebrew düzeltmeli temel, sırlar süzülmüş, `PORT` + `env`.

    Ölçüldü (31 Ekim): süreç `os.environ`'ın tamamıyla (sağlayıcı anahtarları dahil)
    başlıyordu. Dev sunucu bu anahtarlara ihtiyaç duymaz; kullanıcı gerekli olanı `env`
    alanıyla açıkça verir.
    """
    kaynak = php_env(base if base is not None else dict(os.environ))
    env = {
        name: value
        for name, value in kaynak.items()
        if not _SECRET_ENV.search(name) or any(name.startswith(ok) for ok in _ALLOW_ENV)
    }
    if config.port is not None:
        env["PORT"] = str(config.port)
    env.update(config.env)
    return env


#: Çalışan adlı önizlemeler: (kök, ad) → sunucu. `preview_server._RUNNING` kök başına TEK
#: sunucu tutar; launch.json aynı kökte birden çok sunucu tanımlayabilir.
_RUNNING: dict[tuple[Path, str], RunningPreview] = {}
#: (kök, ad) başına başlatma kilidi. Ölçüldü (31 Ekim): kontrol ile kayıt arasında 45 sn'ye
#: kadar await vardı; eşzamanlı ikinci çağrı birincinin kaydını ezip süreci sahipsiz bırakıyordu.
_STARTING: dict[tuple[Path, str], asyncio.Lock] = {}


def running_launch(root: Path, name: str) -> RunningPreview | None:
    """Çalışan adlı önizleme; bağlanılan (bizim olmayan) sunucu yanıt vermiyorsa düşürülür."""
    key = (root.resolve(), name)
    preview = _RUNNING.get(key)
    if preview is None or not preview.alive:
        return None
    if preview.attached and not preview_server.responds(preview.url):
        _RUNNING.pop(key, None)
        return None
    return preview


def running_launches(root: Path | None = None) -> tuple[tuple[str, RunningPreview], ...]:
    """Çalışan adlı önizlemeler `(ad, sunucu)`; `root` verilirse yalnız o kökünkiler."""
    resolved = root.resolve() if root is not None else None
    return tuple(
        (name, preview)
        for (preview_root, name), preview in _RUNNING.items()
        if preview.alive and (resolved is None or preview_root == resolved)
    )


async def start_launch(root: Path, config: LaunchConfig) -> RunningPreview:
    """Yapılandırmayı başlat (ya da çalışana bağlan) ve yanıt verene kadar bekle.

    Aynı (kök, ad) için eşzamanlı çağrılar sıraya girer; ikincisi birincinin sunucusunu alır.
    """
    root = await asyncio.to_thread(root.resolve)
    key = (root, config.name)
    lock = _STARTING.get(key)
    if lock is None:
        lock = _STARTING[key] = asyncio.Lock()
    async with lock:
        existing = running_launch(root, config.name)
        if existing is not None:
            return existing
        preview = await _start(root, config)
        _RUNNING[key] = preview
        return preview


async def _start(root: Path, config: LaunchConfig) -> RunningPreview:
    if config.needs_trust:
        raise LaunchUntrustedError(
            UNTRUSTED_HINT.format(
                source=config.source or LAUNCH_FILE, name=config.name, command=config.command_text
            )
        )
    cwd = root / config.cwd if config.cwd else root
    if not await asyncio.to_thread(cwd.is_dir):
        raise PreviewError(f"'{config.name}' çalışma klasörü yok: {config.cwd}")
    # Sembolik bağ kök dışına çıkaramaz (`cwd: "link"` → ~/...); yalnız sözdizimi denetimi yetmez.
    gercek = await asyncio.to_thread(cwd.resolve)
    if gercek != root and root not in gercek.parents:
        raise PreviewError(
            f"'{config.name}' çalışma klasörü proje kökü dışına çözülüyor: {config.cwd}"
        )
    if config.is_attach:
        url = config.address
        if not await preview_server.wait_until_serving(url, timeout_s=5.0):
            raise PreviewError(
                f"'{config.name}' için {url} yanıt vermiyor; sunucuyu başlat ya da yapılandırmaya "
                "`runtimeExecutable` ekle."
            )
        return RunningPreview(root, PreviewKind.LAUNCH, url, attached=True)
    requested = config
    config = await asyncio.to_thread(_with_free_port, config)
    url = config.address
    command = list(config.command)
    try:
        process, log_path = await preview_server.spawn_logged(
            command, gercek, env_base=launch_env(config)
        )
    except OSError as error:
        raise PreviewError(
            f"'{config.name}' başlatılamadı: {error} (komut: {config.command_text})"
        ) from error
    preview = RunningPreview(root, PreviewKind.LAUNCH, url, process=process, log_path=log_path)
    try:
        if not await preview_server.wait_until_serving(url, process=process):
            tail = _log_tail(preview)
            raise PreviewError(
                f"'{config.name}' {preview_server.SERVER_READY_S:.0f} sn içinde {url} adresinde "
                f"yanıt vermedi. Komut: {config.command_text}"
                + (f"\n[sürecin son çıktısı]\n{tail}" if tail else "")
                + (f"\n{PORT_MOVED_HINT}" if config.port != requested.port else "")
            )
        return preview
    except BaseException:
        await preview_server.dispose(preview)
        raise


def _with_free_port(config: LaunchConfig) -> LaunchConfig:
    """Port doluysa `autoPort`'a göre kaydır ya da `PreviewError`; `${port}` yerleştir."""
    requested = config.port if config.port is not None else preview_ports.url_port(config.url)
    if requested is None:
        return config
    choice = preview_ports.choose_port(requested, auto_port=config.auto_port)
    if choice is None:
        raise PreviewError(
            f"'{config.name}' başlatılmadı: {requested} portu kullanımda"
            + (
                " (autoPort: false). Portu kullanan süreci durdur ya da `autoPort` alanını kaldır."
                if config.auto_port is False
                else f"; sonraki {preview_ports.PORT_SCAN_SPAN} port da dolu (autoPort)."
            )
        )
    return replace(
        config,
        port=choice.port,
        url=preview_ports.with_port(config.url, choice.port) if config.url else None,
        args=launch_json.rewrite_port_flags(
            preview_ports.expand_port(config.args, choice.port), choice.port
        )
        if choice.port != requested
        else preview_ports.expand_port(config.args, choice.port),
    )


def port_note(config: LaunchConfig, preview: RunningPreview) -> str:
    """Port dolu olduğu için kaydırıldıysa kullanıcıya gösterilecek tek satır; yoksa boş."""
    requested = config.port if config.port is not None else preview_ports.url_port(config.url)
    actual = preview_ports.url_port(preview.url)
    if config.is_attach or requested is None or actual is None or actual == requested:
        return ""
    return f"{requested} portu doluydu; '{config.name}' {actual} portunda başlatıldı (autoPort)."


def _log_tail(preview: RunningPreview, chars: int = 1_500) -> str:
    if preview.log_path is None:
        return ""
    try:
        return preview.log_path.read_text(encoding="utf-8", errors="replace")[-chars:].strip()
    except OSError:
        return ""


def stop_launch(root: Path, name: str) -> bool:
    """Adlı önizlemeyi kapat; çalışmıyorsa False."""
    key = (root.resolve(), name)
    preview = _RUNNING.pop(key, None)
    if preview is None:
        return False
    preview_server.terminate(preview)
    return True


@atexit.register
def stop_all_launches() -> None:
    for key in list(_RUNNING):
        preview = _RUNNING.pop(key)
        preview_server.terminate(preview)
    _STARTING.clear()


def trust_launch_file(root: Path) -> str | None:
    """Okunan launch.json'un ŞU ANKİ içeriğini güvenilir kaydet; dosya yoksa None.

    Panelden "Güven ve başlat" bunu çağırır: kullanıcı komut metnini görüp onaylamıştır.
    Dosya sonradan değişirse güven kendiliğinden düşer (karma eşleşmez).
    """
    path = launch_file(root)
    if path is None:
        return None
    trust.approve_file(root, path)
    return path.relative_to(root).as_posix()


def default_preview_url(root: Path) -> str | None:
    """Ajan/arayüz adres vermezse bakılacak sayfa: EN SON başlatılan çalışan önizleme.

    Kök ve alt klasörleri sayılır (`start_preview path=sub name=…` alt kökle kaydedilir).
    Ölçüldü (31 Ekim): `[*detected, *named]` sırası adlı sunucuyu her zaman kazandırıyordu.
    """
    resolved = root.resolve()
    candidates = [
        preview
        for preview in (
            *(preview for _, preview in running_launches()),
            *preview_server.all_running(),
        )
        if preview.root == resolved or resolved in preview.root.parents
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda preview: preview.started_at).url

"""WordPress'i projenin içinde, MySQL'siz (SQLite) ve kullanıcıya iş bırakmadan kur.

Ölçüldü (2 Ekim 2026, "sneaksup" sohbeti): Fusion yalnız `wp-content/themes/...`
dosyalarını yazdı; WordPress çekirdeği yoktu, site hiç açılmadı. Kullanıcı "nasıl
önizlerim" deyince MySQL + WP-CLI + Docker kurulum rehberi verdi — oysa bilgisayarda
`php` ve `wp` zaten kuruluydu. Claude bu durumda kurar ve çalışan adres verir.

Kurulum (elle denenip ölçüldü, ~25 sn, 2 Ekim):

1. `wp core download --skip-content` — kullanıcının `wp-content`'ine dokunmaz.
2. SQLite Database Integration eklentisi + `wp-content/db.php` — MySQL gerekmez.
3. `wp config create --skip-check`, `wp core install` (rastgele yönetici parolası,
   yalnız `.fusion/onizleme-giris.txt` dosyasına yazılır, modele/sohbete gitmez).
4. Projenin kendi teması ve eklentileri etkinleştirilir; tema WooCommerce
   kullanıyorsa WooCommerce kurulur.

Her adım zaten yapılmışsa atlanır: ikinci çağrı yalnız eksik olanı tamamlar.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import secrets
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

#: SQLite sürücüsünün resmi dağıtım adresi (WordPress.org eklenti dizini).
SQLITE_PLUGIN_ZIP_URL = (
    "https://downloads.wordpress.org/plugin/sqlite-database-integration.latest-stable.zip"
)
SQLITE_PLUGIN = "sqlite-database-integration"
#: Tek bir WP-CLI adımına tanınan süre. Ölçüldü: çekirdek indirme 15 sn, WooCommerce
#: kurulumu 5 sn (iyi bağlantıda). Yavaş bağlantı için cömert, sonsuz değil.
WP_STEP_TIMEOUT_S = 180.0
#: İndirilen eklenti arşivinin üst sınırı (SQLite eklentisi ~0,5 MB).
MAX_PLUGIN_ZIP_BYTES = 20 * 1024 * 1024
#: Yönetici giriş bilgisinin yazıldığı dosya (proje içinde, yalnız kullanıcı okur).
CREDENTIALS_FILE = Path(".fusion") / "onizleme-giris.txt"
#: Fusion'ın çalıştırdığı PHP'ye eklenen ayarlar (`PHP_INI_SCAN_DIR`). Ölçüldü (2 Ekim,
#: PHP 8.5 + WP-CLI 2.12): `wp core download` WordPress 7.1 arşivini açarken 128 MB
#: sınırında "Allowed memory size exhausted" ile çöktü; her komut onlarca "Deprecated"
#: basıp gerçek hatayı gömdü. Homebrew'un `wp`'si phar olduğu için `WP_CLI_PHP_ARGS`
#: hiç okunmuyordu — PHP'nin ek ayar dizini her çağrıda okunur.
PHP_INI = "memory_limit = 512M\nerror_reporting = E_ALL & ~E_DEPRECATED\n"
#: Komut satırından WP-CLI'ye geçirilen eşdeğeri (sarmalayıcıyla kurulmuş wp için).
WP_CLI_PHP_ARGS = "-d memory_limit=512M -d error_reporting=24575"
#: Varsayılan WordPress temaları; projenin kendi teması bunlar değildir.
_DEFAULT_THEME_PREFIX = "twenty"


class WordPressSetupError(RuntimeError):
    """Kurulum tamamlanamadı; mesaj modele olduğu gibi gösterilir."""


@dataclass(frozen=True, slots=True)
class WordPressSetup:
    """Kurulumun sonucu: yapılan adımlar ve etkin tema."""

    steps: tuple[str, ...]
    theme: str | None
    credentials: Path | None
    #: Kurulumu durdurmayan ama sitenin doğru görünmesini engelleyen sorunlar.
    problems: tuple[str, ...] = ()


def is_wordpress_project(root: Path) -> bool:
    """Kök bir WordPress sitesi (ya da yalnız tema/eklenti içeren `wp-content`) mi?"""
    return (root / "wp-content").is_dir() or (root / "wp-config.php").is_file()


def has_core(root: Path) -> bool:
    return (root / "wp-includes").is_dir() and (root / "wp-admin").is_dir()


def project_theme(root: Path) -> str | None:
    """Projenin kendi teması: varsayılan olmayan, `style.css`'i olan; birden çoksa en yenisi."""
    themes = root / "wp-content" / "themes"
    if not themes.is_dir():
        return None
    candidates = [
        path
        for path in themes.iterdir()
        if path.is_dir()
        and not path.name.startswith(_DEFAULT_THEME_PREFIX)
        and (path / "style.css").is_file()
    ]
    if not candidates:
        return None
    return max(candidates, key=_latest_mtime).name


def uses_woocommerce(root: Path, theme: str | None) -> bool:
    """Tema WooCommerce'e dayanıyor mu? (şablon klasörü ya da kodda adı geçiyor)"""
    if theme is None:
        return False
    folder = root / "wp-content" / "themes" / theme
    if (folder / "woocommerce").is_dir():
        return True
    for path in folder.rglob("*.php"):
        try:
            if "woocommerce" in path.read_text(encoding="utf-8", errors="replace").lower():
                return True
        except OSError:
            continue
    return False


async def setup_wordpress(
    root: Path, url: str, *, wp_cli: str | None, plugins: tuple[str, ...] = ()
) -> WordPressSetup:
    """Eksik olan her şeyi kur; zaten kuruluysa yalnız eksiği tamamla."""
    if wp_cli is None:
        raise WordPressSetupError(
            "WP-CLI bulunamadı. Kurmak için: `brew install wp-cli` (macOS). "
            "Sonra start_preview'ı tekrar çağır."
        )
    steps: list[str] = []
    if not has_core(root):
        await _wp(wp_cli, root, "core", "download", "--skip-content", "--locale=tr_TR")
        steps.append("WordPress çekirdeği indirildi (wp-content'e dokunulmadı)")
    if not (root / "wp-config.php").is_file():
        await _wp(
            wp_cli, root, "config", "create", "--dbname=wordpress", "--dbuser=wordpress",
            "--dbpass=wordpress", "--dbhost=localhost", "--skip-check",
        )  # fmt: skip
        steps.append("wp-config.php oluşturuldu")
    credentials: Path | None = None
    if not await _wp_ok(wp_cli, root, "core", "is-installed"):
        # Kurulu ve çalışan bir siteye dokunulmaz. Kurulu değilse (ya da wp-config
        # ulaşılamayan bir MySQL'i gösteriyorsa — ölçüldü: model örnek dosyayı
        # kopyaladı) SQLite sürücüsü eklenir; MySQL gerekmez.
        if not (root / "wp-content" / "db.php").is_file():
            await asyncio.to_thread(_install_sqlite_dropin, root)
            steps.append("SQLite veritabanı sürücüsü kuruldu (MySQL gerekmez)")
        credentials = await _install_core(wp_cli, root, url)
        steps.append("WordPress kuruldu")
    else:
        await _wp(wp_cli, root, "option", "update", "home", url)
        await _wp(wp_cli, root, "option", "update", "siteurl", url)
    theme = project_theme(root)
    problems: list[str] = []
    if theme is not None:
        code, output = await run_wp(wp_cli, root, "theme", "activate", theme)
        if code == 0:
            steps.append(f"Tema etkinleştirildi: {theme}")
        else:
            # Ölçüldü (2 Ekim): Fusion'ın yazdığı temada zorunlu `index.php` yoktu ve
            # WordPress temayı reddetti. Kurulum durmaz; hata modele düzeltmesi için gider.
            problems.append(f"Tema '{theme}' etkinleştirilemedi: {_plain(output)[-400:]}")
    else:
        problems.append(
            "Henüz tema yok (site boş görünür): temayı wp-content/themes/<ad>/ altına yaz "
            "(style.css + index.php zorunlu) ve start_preview'ı tekrar çağır."
        )
    wanted = list(plugins)
    if uses_woocommerce(root, theme) and "woocommerce" not in wanted:
        wanted.append("woocommerce")
    steps.extend(await _plugins(wp_cli, root, wanted, problems))
    await _wp(wp_cli, root, "rewrite", "structure", "/%postname%/")
    existing = root / CREDENTIALS_FILE
    return WordPressSetup(
        steps=tuple(steps),
        theme=theme,
        credentials=credentials or (existing if existing.is_file() else None),
        problems=tuple(problems),
    )


async def _plugins(wp_cli: str, root: Path, wanted: list[str], problems: list[str]) -> list[str]:
    steps: list[str] = []
    for slug in wanted:
        if (root / "wp-content" / "plugins" / slug).is_dir():
            continue
        code, output = await run_wp(wp_cli, root, "plugin", "install", slug, "--activate")
        if code == 0:
            steps.append(f"Eklenti kuruldu: {slug}")
        else:
            problems.append(f"Eklenti '{slug}' kurulamadı: {_plain(output)[-300:]}")
    # Projenin kendi eklentileri (tek dosyalık olanlar dahil) etkinleşir; kurulum
    # sırasında etkinleşmeyen eklenti "yazıldı ama çalışmıyor" demektir.
    await _wp(wp_cli, root, "plugin", "activate", "--all")
    if (root / "wp-content" / "plugins" / "woocommerce").is_dir():
        # Yeni WooCommerce mağazası ziyaretçiye "Yakında" sayfası gösterir. Ölçüldü (2 Ekim
        # 2026, 8. kabul koşusu): ürünler eklendiği halde /shop/ boş "coming-soon" sayfası
        # döndü; model nedenini curl çıktısında aradı. Yerel önizlemede mağaza açık olmalı.
        await run_wp(wp_cli, root, "option", "update", "woocommerce_coming_soon", "no")
        birim = catalog_currency(root)
        if birim:
            # Kaynak sitenin para birimi mağazaya uygulanır. Ölçüldü (13. kabul koşusu):
            # özet "para birimini TRY yap" dediği halde model mağazayı dolar bıraktı.
            await run_wp(wp_cli, root, "option", "update", "woocommerce_currency", birim)
            steps.append(f"Mağaza para birimi: {birim} (kaynak siteden)")
    return steps


#: `site_design`'ın yazdığı ürün kataloğu (proje kökünde).
CATALOG_FILE = Path("tasarim-kaynak") / "urunler.json"
_CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")


def catalog_currency(root: Path) -> str:
    """Ölçülen kataloğun para birimi (ISO kodu); katalog yoksa boş."""
    try:
        items = json.loads((root / CATALOG_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(items, list):
        return ""
    for item in items:
        birim = item.get("para_birimi") if isinstance(item, dict) else None
        if isinstance(birim, str) and _CURRENCY_CODE.fullmatch(birim):
            return birim
    return ""


async def _install_core(wp_cli: str, root: Path, url: str) -> Path:
    password = secrets.token_urlsafe(12)
    await _wp(
        wp_cli, root, "core", "install", f"--url={url}", "--title=Önizleme",
        "--admin_user=admin", f"--admin_password={password}",
        "--admin_email=admin@example.com", "--skip-email",
    )  # fmt: skip
    path = root / CREDENTIALS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"Yerel önizleme yönetici girişi\nAdres: {url}/wp-admin\nKullanıcı: admin\n"
        f"Parola: {password}\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def _install_sqlite_dropin(root: Path) -> None:
    """SQLite eklentisini indir ve `db.php` sürücüsünü yerleştir."""
    plugins = root / "wp-content" / "plugins"
    folder = plugins / SQLITE_PLUGIN
    if not (folder / "db.copy").is_file():
        with urllib.request.urlopen(SQLITE_PLUGIN_ZIP_URL, timeout=60) as response:
            data = response.read(MAX_PLUGIN_ZIP_BYTES + 1)
        if len(data) > MAX_PLUGIN_ZIP_BYTES:
            raise WordPressSetupError("SQLite eklenti arşivi beklenenden büyük; kurulmadı.")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            _safe_extract(archive, plugins)
    template = (folder / "db.copy").read_text(encoding="utf-8")
    dropin = template.replace("{SQLITE_IMPLEMENTATION_FOLDER_PATH}", str(folder)).replace(
        "{SQLITE_PLUGIN}", f"{SQLITE_PLUGIN}/load.php"
    )
    (root / "wp-content" / "db.php").write_text(dropin, encoding="utf-8")


def _safe_extract(archive: zipfile.ZipFile, target: Path) -> None:
    """Arşivi hedefin DIŞINA yazamayacak biçimde aç (zip slip)."""
    base = target.resolve()
    for member in archive.infolist():
        destination = (target / member.filename).resolve()
        if not destination.is_relative_to(base):
            raise WordPressSetupError(f"Arşivde güvensiz yol: {member.filename}")
    archive.extractall(target)


async def _wp(wp_cli: str, root: Path, *args: str) -> str:
    code, output = await run_wp(wp_cli, root, *args)
    if code != 0:
        raise WordPressSetupError(f"`wp {' '.join(args[:3])}` başarısız: {output[-600:]}")
    return output


async def _wp_ok(wp_cli: str, root: Path, *args: str) -> bool:
    code, _ = await run_wp(wp_cli, root, *args)
    return code == 0


async def run_wp(wp_cli: str, root: Path, *args: str) -> tuple[int, str]:
    env = php_env()
    process = await asyncio.create_subprocess_exec(
        wp_cli,
        *args,
        f"--path={root}",
        cwd=str(root),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        raw, _ = await asyncio.wait_for(process.communicate(), timeout=WP_STEP_TIMEOUT_S)
    except TimeoutError as exc:
        process.kill()
        # Ölçüldü (3 Ekim 2026, 12. kabul koşusu): model Wordfence/Autoptimize gibi ağır
        # eklentiler kurunca SQLite'lı sitede her `wp` komutu asılı kaldı; model nedenini
        # bilmeden aynı komutları yineledi. `--skip-plugins` WP-CLI'nin kaçış kapısıdır.
        raise WordPressSetupError(
            f"`wp {' '.join(args[:3])}` {WP_STEP_TIMEOUT_S:.0f} sn içinde bitmedi. Son kurulan "
            "bir eklenti siteyi kilitlemiş olabilir: `wp plugin list --skip-plugins` ile bak, "
            "şüpheli eklentiyi `wp plugin deactivate <ad> --skip-plugins` ile kapat ve "
            "start_preview'ı tekrar çağır."
        ) from exc
    text = raw.decode("utf-8", errors="replace")
    lines = [line for line in text.splitlines() if "Deprecated" not in line and line.strip()]
    return process.returncode or 0, "\n".join(lines)


#: Masaüstü uygulaması Finder'dan açılınca PATH Homebrew'u içermez; `wp` betiği
#: `#!/usr/bin/env php` ile başladığı için php'yi bulamazdı.
_EXTRA_BIN_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")


def php_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """PHP/WP-CLI için ortam: Homebrew PATH'i, ek ayar dizini, WP-CLI argümanları.

    Kullanıcının kendi `PHP_INI_SCAN_DIR` / `WP_CLI_PHP_ARGS` değeri korunur.
    """
    env = dict(os.environ if base is None else base)
    env["PATH"] = tool_path()
    env.setdefault("WP_CLI_PHP_ARGS", WP_CLI_PHP_ARGS)
    ini_dir = _php_ini_dir()
    if ini_dir is not None and "PHP_INI_SCAN_DIR" not in env:
        # Baştaki ':' PHP'nin varsayılan tarama dizinini KORUR, bizimkini ekler.
        env["PHP_INI_SCAN_DIR"] = f":{ini_dir}"
    return env


def _php_ini_dir() -> Path | None:
    folder = Path(tempfile.gettempdir()) / "fusion-php-ini"
    try:
        folder.mkdir(exist_ok=True)
        ini = folder / "fusion.ini"
        if not ini.is_file() or ini.read_text(encoding="utf-8") != PHP_INI:
            ini.write_text(PHP_INI, encoding="utf-8")
    except OSError:
        return None
    return folder


def tool_path() -> str:
    """Homebrew dizinleri eklenmiş PATH."""
    parts = os.environ.get("PATH", "").split(os.pathsep)
    return os.pathsep.join([*parts, *(d for d in _EXTRA_BIN_DIRS if d not in parts)])


def _plain(text: str) -> str:
    """WP-CLI hata metnindeki HTML etiketlerini at (model düz metin okusun)."""
    return re.sub(r"<[^>]+>", "", text).strip()


def find_wp_cli() -> str | None:
    """WP-CLI yolu; GUI uygulamasının PATH'i Homebrew'u içermeyebilir."""
    return shutil.which("wp", path=tool_path())


def _latest_mtime(folder: Path) -> float:
    try:
        return max((path.stat().st_mtime for path in folder.rglob("*")), default=0.0)
    except OSError:
        return 0.0

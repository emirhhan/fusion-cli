"""Site kopyası alanı: bir mağazanın çalışan WordPress/WooCommerce kopyası.

Denetçi ajanın sözüne değil sitenin kendisine bakar: WordPress'i ajanın kurduğu
adreste ayağa kaldırır, WP-CLI ile veritabanını, Playwright ile sayfaları ölçer ve
gerçek bir alışveriş akışı (sepete ekle → sepet → ödeme) dener. Maddeler tek bir
siteye özel değildir; kaynak adres yalnız görsel benzerlik ve hotlink ölçümünde
kullanılır. Eşikler başlangıç değeridir, taban ölçümüyle sabitlenecek.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from evals.kabul.areas import site_clone_probe as probe
from evals.kabul.model import Area, Check, Inspection

SOURCE_URL = "https://www.sneaksup.com"
#: Kaynak mağazada ölçülen ürün kartı sayısı 24+ idi (site_design, 17. koşu);
#: kopyanın en az bu kadar ürünü olmalı.
MIN_PRODUCTS = 24
#: Masaüstü genişliğinde mağaza ızgarasının en az bu kadar sütunu olmalı
#: (kaynakta 4; 3 tabletteki dar düzenlere pay bırakır).
MIN_GRID_COLUMNS = 3
#: Gri tonlu, küçültülmüş ekran görüntülerinin ortalama piksel benzerliği (0-1).
#: Başlangıç eşiği; taban koşularındaki dağılıma göre sabitlenecek.
MIN_VISUAL_SIMILARITY = 0.75
WP_CLI_TIMEOUT_S = 90
SERVER_READY_S = 30

TASK = (
    "wordpress tabanlı bir website yapmanı istiyorum bu website birebir olarak "
    f"{SOURCE_URL} sitesine benzeyecek görsellerine kadar istediğin her yerden "
    "alabilirsin istersen html görseller üretebilirsin siteyi görüntüleyemiyorsan "
    "fusion browser eklentisini kullanabilirsin bu siteyi her sayfalarıyla birlikte "
    "gerçek çalışan bir e ticaret sitesi yapmanı istiyorum ürün sayfası, sepet ve "
    "kapıda ödeme ile sipariş verilebilen ödeme sayfası çalışmalı. ben ilerleyen "
    "zamanda bu siteyi bir hostinge ve domaine bağlayacağım."
)


def _wp(root: Path, *args: str) -> str:
    """WP-CLI komutu; hata metni değil çıktı döner, başarısızlıkta boş metin."""
    sonuc = subprocess.run(
        ["wp", f"--path={root}", *args],
        capture_output=True,
        text=True,
        timeout=WP_CLI_TIMEOUT_S,
        check=False,
    )
    if sonuc.returncode != 0:
        return ""
    # Homebrew wp-cli PHP 8.x altında "Deprecated: …" satırlarını stdout'a basıyor;
    # ölçüldü: siteurl bu metinle birleşip adres bozuluyordu.
    satirlar = [s for s in sonuc.stdout.splitlines() if s.strip() and "eprecated" not in s]
    return "\n".join(satirlar).strip()


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


@contextmanager
def _serve(root: Path, site_url: str) -> Iterator[str]:
    """Siteyi veritabanındaki adresin portunda aç (WordPress başka porta yönlendirir)."""
    port = urlparse(site_url).port or 80
    bitis = time.monotonic() + SERVER_READY_S
    while not _port_is_free(port) and time.monotonic() < bitis:
        time.sleep(1)
    if not _port_is_free(port):
        raise RuntimeError(f"{port} portu dolu; site açılamadı")
    php = shutil.which("php") or "php"
    surec = subprocess.Popen(
        [php, "-S", f"127.0.0.1:{port}", "-t", str(root)],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        while _port_is_free(port) and time.monotonic() < bitis + SERVER_READY_S:
            time.sleep(0.5)
        yield site_url.rstrip("/")
    finally:
        surec.terminate()
        surec.wait(timeout=10)


def _site_root(workdir: Path) -> Path | None:
    """WordPress kökü: çalışma klasörü ya da içindeki ilk wp-config.php'nin klasörü."""
    if (workdir / "wp-config.php").is_file():
        return workdir
    adaylar = sorted(workdir.glob("*/wp-config.php")) + sorted(workdir.glob("*/*/wp-config.php"))
    return adaylar[0].parent if adaylar else None


def _database_checks(root: Path) -> tuple[Check, ...]:
    urun = _wp(
        root, "post", "list", "--post_type=product", "--post_status=publish", "--format=count"
    )
    urun_sayisi = int(urun) if urun.isdigit() else 0
    woo = _wp(root, "eval", "echo function_exists('WC') ? 'evet' : 'hayir';") == "evet"
    odeme = _wp(
        root,
        "eval",
        "echo implode(',', array_keys(WC()->payment_gateways->get_available_payment_gateways()));",
    )
    return (
        Check("woocommerce_etkin", woo, f"WC yüklü: {woo}"),
        Check(
            "urun_sayisi",
            urun_sayisi >= MIN_PRODUCTS,
            f"yayında {urun_sayisi} ürün (en az {MIN_PRODUCTS})",
        ),
        Check("odeme_yontemi_var", bool(odeme), f"etkin ödeme yöntemleri: {odeme or 'yok'}"),
    )


def _order_count(root: Path) -> int:
    # Blok ödeme sayfası açılınca "checkout-draft" taslak siparişi oluşur; o sayılmaz.
    sayi = _wp(
        root,
        "eval",
        "echo count(wc_get_orders(['limit' => -1, 'return' => 'ids', 'status' => "
        "['pending', 'processing', 'on-hold', 'completed']]));",
    )
    return int(sayi) if sayi.isdigit() else 0


def _inspect_site(root: Path) -> Inspection:
    site_url = _wp(root, "option", "get", "siteurl")
    if not site_url:
        return Inspection(checks=(Check("wordpress_calisiyor", False, "WP-CLI siteurl okuyamadı"),))
    sayfa_adresleri = probe.WooPages(
        shop=_wp(root, "eval", "echo get_permalink(wc_get_page_id('shop'));"),
        cart=_wp(root, "eval", "echo wc_get_cart_url();"),
        checkout=_wp(root, "eval", "echo wc_get_checkout_url();"),
        product=_wp(
            root,
            "post",
            "list",
            "--post_type=product",
            "--post_status=publish",
            "--field=url",
            "--posts_per_page=1",
        ),
    )
    once = _order_count(root)
    with _serve(root, site_url) as adres:
        tarayici = probe.probe_store(adres, sayfa_adresleri, SOURCE_URL)
    sonra = _order_count(root)
    siparis = Check(
        "test_siparisi_olustu",
        sonra > once,
        f"sipariş sayısı {once} → {sonra}; {tarayici.checkout_note}",
    )
    benzerlik = Check(
        "gorsel_benzerlik",
        tarayici.similarity >= MIN_VISUAL_SIMILARITY,
        f"ana sayfa benzerliği {tarayici.similarity:.2f} (eşik {MIN_VISUAL_SIMILARITY})",
    )
    sutun = Check(
        "magaza_izgarasi",
        tarayici.grid_columns >= MIN_GRID_COLUMNS,
        f"ilk satırda {tarayici.grid_columns} sütun (en az {MIN_GRID_COLUMNS})",
    )
    return Inspection(checks=(*_database_checks(root), *tarayici.checks, sutun, siparis, benzerlik))


def inspect(workdir: Path, values: Mapping[str, str]) -> Inspection:
    """Ajanın kurduğu mağazayı ölç."""
    if shutil.which("wp") is None or shutil.which("php") is None:
        return Inspection(invalid_reason="wp-cli ya da php bulunamadı")
    root = _site_root(workdir)
    if root is None:
        return Inspection(checks=(Check("wordpress_kuruldu", False, "wp-config.php yok"),))
    try:
        return _inspect_site(root)
    except probe.ProbeUnavailableError as hata:
        return Inspection(invalid_reason=str(hata))
    except (RuntimeError, subprocess.TimeoutExpired) as hata:
        return Inspection(checks=(Check("site_acildi", False, str(hata)[:300]),))


AREA = Area(
    name="site_kopyasi",
    task=TASK,
    timeout_s=5400,
    inspect=inspect,
    required_executables=("php", "wp"),
)

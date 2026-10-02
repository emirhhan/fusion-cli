"""Site gerçekten çalışıyor mu: WordPress kurulumu, site kapısı ve rapor dili.

Ölçüldü (2 Ekim 2026): rapor "✓ Doğrulandı: php -l 12 dosyada temiz" dedi; tema
zorunlu `index.php` içermediği için WordPress'te hiç açılmıyordu ve site hiç
çalıştırılmamıştı.
"""

from __future__ import annotations

import io
import shutil
import stat
import zipfile
from pathlib import Path

import pytest

from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
from fusion_cli.core.execution_plan import VerificationCheckKind
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent.php_verify import missing_required_theme_files
from fusion_cli.engines.agent.site_verify import NOT_RUNNABLE_NOTE, SiteVerifier
from fusion_cli.engines.agent.turn_report import TurnReport
from fusion_cli.tools import preview_server, wordpress_setup
from fusion_cli.tools.wordpress_setup import (
    CREDENTIALS_FILE,
    WordPressSetupError,
    project_theme,
    setup_wordpress,
    uses_woocommerce,
)

PHP = shutil.which("php") or next(
    (p for p in ("/opt/homebrew/bin/php", "/usr/local/bin/php") if Path(p).is_file()), None
)


@pytest.fixture(autouse=True)
def _sunuculari_kapat():
    yield
    preview_server.stop_all()


def _tema(root: Path, ad: str = "sneaksup", *, index: bool = True) -> Path:
    tema = root / "wp-content" / "themes" / ad
    tema.mkdir(parents=True)
    (tema / "style.css").write_text(f"/*\nTheme Name: {ad}\n*/\n", encoding="utf-8")
    (tema / "functions.php").write_text("<?php add_theme_support('woocommerce');", encoding="utf-8")
    if index:
        (tema / "index.php").write_text("<?php get_header();", encoding="utf-8")
    return tema


# --- Zorunlu tema dosyası ------------------------------------------------------------ #


def test_index_php_olmayan_tema_etkinlesemez_diye_bulgu_verir(tmp_path):
    tema = _tema(tmp_path, index=False)

    bulgular = missing_required_theme_files([tema / "functions.php"])

    assert len(bulgular) == 1 and "zorunlu `index.php`" in bulgular[0]


def test_index_php_olan_tema_temiz(tmp_path):
    tema = _tema(tmp_path)
    assert missing_required_theme_files([tema / "functions.php"]) == []


# --- WordPress kurulumu (sahte WP-CLI, ağsız) ---------------------------------------- #


def _sahte_wp(tmp_path: Path, *, kurulu: bool) -> tuple[str, Path]:
    """Çağrıları kaydeden sahte `wp`; `core download` gerçek klasörleri oluşturur."""
    kayit = tmp_path / "wp-cagrilari.txt"
    betik = tmp_path / "wp"
    betik.write_text(
        "#!/bin/sh\n"
        f'echo "$*" >> "{kayit}"\n'
        'for a in "$@"; do case "$a" in --path=*) KOK="${a#--path=}";; esac; done\n'
        'if [ "$1 $2" = "core download" ]; then mkdir -p "$KOK/wp-includes" "$KOK/wp-admin"; fi\n'
        'if [ "$1 $2" = "config create" ]; then echo "<?php" > "$KOK/wp-config.php"; fi\n'
        f'if [ "$1 $2" = "core is-installed" ]; then exit {0 if kurulu else 1}; fi\n'
        "exit 0\n",
        encoding="utf-8",
    )
    betik.chmod(betik.stat().st_mode | stat.S_IEXEC)
    return str(betik), kayit


async def test_yalniz_tema_olan_projeye_wordpress_sqliteyla_kurulur(tmp_path, monkeypatch):
    kok = tmp_path / "site"
    _tema(kok)
    wp, kayit = _sahte_wp(tmp_path, kurulu=False)
    monkeypatch.setattr(
        wordpress_setup,
        "_install_sqlite_dropin",
        lambda root: (root / "wp-content" / "db.php").write_text("<?php", encoding="utf-8"),
    )

    sonuc = await setup_wordpress(kok, "http://127.0.0.1:8770", wp_cli=wp)

    cagrilar = kayit.read_text(encoding="utf-8")
    assert "core download --skip-content" in cagrilar
    assert "theme activate sneaksup" in cagrilar
    # Tema WooCommerce'i kullanıyor: eklenti de kurulur.
    assert "plugin install woocommerce --activate" in cagrilar
    assert sonuc.theme == "sneaksup" and sonuc.problems == ()
    # Parola yalnız proje içindeki, yalnız sahibinin okuyabildiği dosyadadır.
    giris = kok / CREDENTIALS_FILE
    assert sonuc.credentials == giris and stat.S_IMODE(giris.stat().st_mode) == 0o600
    parola = giris.read_text(encoding="utf-8").split("Parola: ")[1].strip()
    assert parola and parola not in " ".join(sonuc.steps)


async def test_temasiz_kurulumda_istenen_eklenti_kurulur_ve_tema_eksigi_soylenir(
    tmp_path, monkeypatch
):
    kok = tmp_path / "site"
    (kok / "wp-content" / "themes").mkdir(parents=True)
    wp, kayit = _sahte_wp(tmp_path, kurulu=False)
    monkeypatch.setattr(
        wordpress_setup,
        "_install_sqlite_dropin",
        lambda root: (root / "wp-content" / "db.php").write_text("<?php", encoding="utf-8"),
    )

    sonuc = await setup_wordpress(kok, "http://127.0.0.1:8772", wp_cli=wp, plugins=("woocommerce",))

    cagrilar = kayit.read_text(encoding="utf-8")
    assert "plugin install woocommerce --activate" in cagrilar
    assert "theme activate" not in cagrilar
    # Sahte wp eklenti klasörü oluşturmaz: mağaza ayarı yalnız WooCommerce kuruluyken yazılır.
    assert "woocommerce_coming_soon" not in cagrilar
    assert sonuc.theme is None and "Henüz tema yok" in sonuc.problems[0]


async def test_woocommerce_kuruluysa_magaza_yakinda_sayfasi_kapatilir(tmp_path):
    """Ölçüldü (8. kabul koşusu): ürünler eklendiği halde /shop/ "coming-soon" döndü."""
    kok = tmp_path / "site"
    _tema(kok)
    for klasor in ("wp-includes", "wp-admin", "wp-content/plugins/woocommerce"):
        (kok / klasor).mkdir(parents=True)
    (kok / "wp-config.php").write_text("<?php", encoding="utf-8")
    wp, kayit = _sahte_wp(tmp_path, kurulu=True)

    await setup_wordpress(kok, "http://127.0.0.1:8773", wp_cli=wp)

    assert "option update woocommerce_coming_soon no" in kayit.read_text(encoding="utf-8")


async def test_kurulu_siteye_ikinci_kez_kurulum_yapilmaz(tmp_path):
    kok = tmp_path / "site"
    _tema(kok)
    (kok / "wp-includes").mkdir()
    (kok / "wp-admin").mkdir()
    (kok / "wp-config.php").write_text("<?php", encoding="utf-8")
    wp, kayit = _sahte_wp(tmp_path, kurulu=True)

    await setup_wordpress(kok, "http://127.0.0.1:8771", wp_cli=wp)

    cagrilar = kayit.read_text(encoding="utf-8")
    assert "core download" not in cagrilar and "core install" not in cagrilar
    assert "option update home http://127.0.0.1:8771" in cagrilar


async def test_wp_cli_yoksa_nasil_kurulacagini_soyler(tmp_path):
    _tema(tmp_path)
    with pytest.raises(WordPressSetupError, match="brew install wp-cli"):
        await setup_wordpress(tmp_path, "http://127.0.0.1:1", wp_cli=None)


def test_proje_temasi_varsayilan_temalardan_ayrilir(tmp_path):
    _tema(tmp_path, "twentytwentyfive")
    _tema(tmp_path, "magaza")
    assert project_theme(tmp_path) == "magaza"
    assert uses_woocommerce(tmp_path, "magaza")


def test_arsiv_hedef_disina_yazamaz(tmp_path):
    veri = io.BytesIO()
    with zipfile.ZipFile(veri, "w") as arsiv:
        arsiv.writestr("../kacak.php", "<?php")
    with zipfile.ZipFile(veri) as arsiv, pytest.raises(WordPressSetupError, match="güvensiz"):
        wordpress_setup._safe_extract(arsiv, tmp_path / "plugins")
    assert not (tmp_path / "kacak.php").exists()


# --- Site kapısı -------------------------------------------------------------------- #


async def test_yalniz_tema_varken_kapi_dogrulandi_demez(tmp_path):
    tema = _tema(tmp_path)
    context = ToolContext(root=tmp_path, touched={tema / "functions.php"})

    sonuc = await SiteVerifier(context, PHP).verify()

    assert sonuc.ok and sonuc.warnings == (NOT_RUNNABLE_NOTE,) and not sonuc.evidence


@pytest.mark.skipif(PHP is None, reason="php kurulu değil")
async def test_php_sitesi_calistirilip_acildiginda_kanit_uretilir(tmp_path):
    sayfa = tmp_path / "index.php"
    sayfa.write_text(
        "<html><head><title>Mağaza</title></head><body><p>"
        "<?= 'Bu sayfa gerçekten PHP ile çalışıp üretildi.' ?></p></body></html>",
        encoding="utf-8",
    )

    sonuc = await SiteVerifier(ToolContext(root=tmp_path, touched={sayfa}), PHP).verify()

    assert sonuc.ok
    assert sonuc.evidence[0].status is EvidenceStatus.PASSED and sonuc.evidence[0].behavioral
    assert "site çalıştırılıp açıldı" in sonuc.evidence[0].summary
    # Geçici sunucu kapatıldı: kapı arkasında süreç kalmaz.
    assert preview_server.running(tmp_path) is None


@pytest.mark.skipif(PHP is None, reason="php kurulu değil")
async def test_fatal_error_veren_site_kapidan_gecmez(tmp_path):
    sayfa = tmp_path / "index.php"
    sayfa.write_text("<?php olmayan_fonksiyon();", encoding="utf-8")

    sonuc = await SiteVerifier(ToolContext(root=tmp_path, touched={sayfa}), PHP).verify()

    assert not sonuc.ok and any("Fatal error" in bulgu for bulgu in sonuc.findings)


# --- Rapor dili --------------------------------------------------------------------- #


def _kapi(behavioral: bool) -> VerificationResult:
    return VerificationResult(
        ok=True,
        evidence=(
            CriterionEvidence(
                criterion_id="x",
                kind=VerificationCheckKind.COMMAND,
                status=EvidenceStatus.PASSED,
                summary="php -l 12 dosyada temiz",
                behavioral=behavioral,
            ),
        ),
    )


def test_yalniz_sozdizimi_kaniti_dogrulandi_saydirmaz():
    rapor = TurnReport(changed_paths=("functions.php",), gate=_kapi(behavioral=False))

    assert rapor.is_verified is False
    metin = rapor.render()
    assert "✓ Doğrulandı" not in metin and "Yalnız sözdizimi denetlendi" in metin


def test_calisma_kaniti_dogrulandi_saydirir():
    rapor = TurnReport(changed_paths=("functions.php",), gate=_kapi(behavioral=True))

    assert rapor.is_verified is True and "✓ Doğrulandı" in rapor.render()


# --- Kabuk ortamı ve ipucu (kabul koşusu bulguları) --------------------------------- #


def test_php_ortami_bellegi_artirir_ve_kullanici_ayarini_ezmez(tmp_path):
    from fusion_cli.tools.wordpress_setup import php_env

    env = php_env({"PATH": "/usr/bin"})
    ini_dir = env["PHP_INI_SCAN_DIR"].lstrip(":")
    assert env["PHP_INI_SCAN_DIR"].startswith(":")  # PHP'nin varsayılan dizini korunur
    assert "memory_limit = 512M" in (Path(ini_dir) / "fusion.ini").read_text(encoding="utf-8")
    assert "/opt/homebrew/bin" in env["PATH"]

    kendi = php_env({"PATH": "/usr/bin", "PHP_INI_SCAN_DIR": "/benim"})
    assert kendi["PHP_INI_SCAN_DIR"] == "/benim"

"""Dev sunucusuyla çalışan projelerde de düzen ÖLÇÜLÜR.

Ölçüldü (canlı koşu, GATE HOLDING): model `app/globals.css` dosyasını değiştirip
"Lütfen uygulamayı geniş ekranda açıp kontrol et" diyerek turu kapattı. Tarayıcı
kapısı (`browser_verification`) varsayılan olarak AÇIKTI ve tam da yatay taşmayı
375/768/1440'ta ölçüyordu — ama hiç konuşmadı.

Sebep: kapı yalnızca `tool_context.touched` içindeki `.html` dosyalarını açıyor.
Next.js/Vite gibi dev sunucusuyla çalışan projelerde ortada `.html` dosyası
YOKTUR; sayfa çalışma anında üretilir. Yani en çok düzen hatası üreten proje
türünde kapı yapısal olarak kör.

Düzeltmenin ölçülmüş bedeli: ben aynı sayfayı elle ölçtüğümde taban 11 ihlal,
koşu sonrası 8 ihlal çıktı — kapı bunların hiçbirini görmemişti.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.engines.agent.browser_verify import (
    LAYOUT_SUFFIXES,
    dev_server_command,
    touches_layout,
)


def test_duzen_dosyalari_taniir() -> None:
    assert touches_layout([Path("app/globals.css")]) is True
    assert touches_layout([Path("components/Sidebar.tsx")]) is True
    assert touches_layout([Path("app/page.jsx")]) is True


def test_duzenle_ilgisiz_dosya_kapiyi_acmaz() -> None:
    """Sunucu başlatmak pahalıdır; yalnızca düzen değiştiyse yapılır."""
    assert touches_layout([Path("README.md")]) is False
    assert touches_layout([Path("lib/utils.ts")]) is False
    assert touches_layout([]) is False


def test_butun_duzen_uzantilari_kapsanir() -> None:
    for uzanti in LAYOUT_SUFFIXES:
        assert touches_layout([Path(f"a{uzanti}")]) is True


def test_dev_komutu_package_json_dan_okunur() -> None:
    komut = dev_server_command({"scripts": {"dev": "next dev"}})

    assert komut == ["npm", "run", "dev"]


def test_dev_betigi_yoksa_komut_uretilmez() -> None:
    """Komut UYDURULMAZ: projede kanıtı yoksa kapı hiç kurulmaz."""
    assert dev_server_command({"scripts": {"build": "next build"}}) is None
    assert dev_server_command({}) is None


def test_bozuk_package_json_cokmez() -> None:
    """Doğrulama bir iyileştirmedir; turu düşürmesi kabul edilemez."""
    assert dev_server_command({"scripts": "bozuk"}) is None
    assert dev_server_command({"scripts": {"dev": 42}}) is None


async def test_package_json_yoksa_sunucu_hic_baslatilmaz(tmp_path, monkeypatch) -> None:
    """Ucuz kontroller ÖNCE: Playwright'ı boşuna içeri almayız."""
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import browser_verify

    def _patlat():
        raise AssertionError("koşullar tutmazken tarayıcı yoklanmamalı")

    monkeypatch.setattr(browser_verify, "_playwright_available", _patlat)
    context = ToolContext(root=tmp_path)
    context.touched.add(tmp_path / "app/globals.css")

    sonuc = await browser_verify.BrowserVerifier(context).verify()

    assert sonuc.ok


async def test_dev_betigi_yoksa_sunucu_hic_baslatilmaz(tmp_path, monkeypatch) -> None:
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import browser_verify

    def _patlat():
        raise AssertionError("dev betiği yokken tarayıcı yoklanmamalı")

    monkeypatch.setattr(browser_verify, "_playwright_available", _patlat)
    (tmp_path / "package.json").write_text('{"scripts": {"build": "x"}}', encoding="utf-8")
    context = ToolContext(root=tmp_path)
    context.touched.add(tmp_path / "app/globals.css")

    assert (await browser_verify.BrowserVerifier(context).verify()).ok


async def test_duzen_disi_degisiklikte_sunucu_baslatilmaz(tmp_path, monkeypatch) -> None:
    """Sunucu başlatmak saniyeler sürer; README değişikliği bunu hak etmez."""
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import browser_verify

    def _patlat():
        raise AssertionError("düzen değişmemişken tarayıcı yoklanmamalı")

    monkeypatch.setattr(browser_verify, "_playwright_available", _patlat)
    (tmp_path / "package.json").write_text('{"scripts": {"dev": "next dev"}}', encoding="utf-8")
    context = ToolContext(root=tmp_path)
    context.touched.add(tmp_path / "README.md")

    assert (await browser_verify.BrowserVerifier(context).verify()).ok

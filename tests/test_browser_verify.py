"""Tarayıcı doğrulayıcı — gözlemden bulguya çeviren saf karar ve zarif atlama.

Tarayıcıyı süren yapıştırıcı kod ince tutulur; karar mantığı saf ve doğrudan test
edilir. Playwright kurulu olmayan makinede testler yine çalışır.
"""

from __future__ import annotations

from fusion_cli.engines.agent.browser_verify import (
    BrowserVerifier,
    PageObservation,
    page_findings,
)


def _gozlem(**overrides) -> PageObservation:
    defaults: dict[str, object] = {
        "name": "index.html",
        "console_errors": (),
        "failed_requests": (),
        "overflowing": (),
    }
    defaults.update(overrides)
    return PageObservation(**defaults)  # type: ignore[arg-type]


def test_temiz_sayfa_bulgu_uretmez():
    assert page_findings((_gozlem(),)) == ()


def test_konsol_hatasi_bildirilir():
    bulgular = page_findings((_gozlem(console_errors=("TypeError: x is not a function",)),))

    assert any("konsol" in b.lower() for b in bulgular)
    assert any("TypeError" in b for b in bulgular)


def test_yuklenemeyen_kaynak_bildirilir():
    bulgular = page_findings(
        (_gozlem(failed_requests=("https://via.placeholder.com/80", "./yok.png")),)
    )

    assert any("yüklenemedi" in b.lower() for b in bulgular)
    assert any("via.placeholder.com" in b for b in bulgular)


def test_ayni_kaynak_tekrar_tekrar_bildirilmez():
    """12 kırık görsel 12 satır bulgu üretmemeli; talimat okunabilir kalmalı."""
    ayni = ("https://via.placeholder.com/80",) * 12
    bulgular = page_findings((_gozlem(failed_requests=ayni),))

    assert len(bulgular) == 1


def test_bildirilen_sayi_farkli_kaynak_sayisidir():
    """Sayfa her genişlik için yeniden yükleniyor; ham sayım şişik olur.

    Aynı görsel 3 kez denenip 3 kez düşerse bu 3 ayrı sorun değildir.
    """
    gozlem = _gozlem(failed_requests=("a.png", "a.png", "a.png", "b.png", "b.png", "b.png"))

    bulgular = page_findings((gozlem,))

    assert "2 kaynak" in bulgular[0], bulgular[0]


def test_yatay_tasma_bildirilir():
    bulgular = page_findings((_gozlem(overflowing=((375, 412),)),))

    assert any("375" in b for b in bulgular)
    assert any("taşma" in b.lower() for b in bulgular)


def test_birden_cok_sayfa_ayri_ayri_bildirilir():
    bulgular = page_findings(
        (
            _gozlem(name="a.html", console_errors=("hata A",)),
            _gozlem(name="b.html", console_errors=("hata B",)),
        )
    )

    assert any("a.html" in b for b in bulgular)
    assert any("b.html" in b for b in bulgular)


async def test_playwright_yoksa_kapi_sessizce_gecer(tmp_path, monkeypatch):
    """Opsiyonel ekstra kurulmamışsa doğrulama turu DÜŞÜRMEZ."""
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import browser_verify

    monkeypatch.setattr(browser_verify, "_playwright_available", lambda: False)
    sayfa = tmp_path / "a.html"
    sayfa.write_text("<main>x</main>", encoding="utf-8")
    context = ToolContext(root=tmp_path)
    context.touched.add(sayfa)

    sonuc = await BrowserVerifier(context).verify()

    assert sonuc.ok
    assert sonuc.findings == ()


async def test_html_yoksa_tarayici_hic_acilmaz(tmp_path, monkeypatch):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import browser_verify

    def _patlat():
        raise AssertionError("HTML yokken tarayıcı yoklanmamalı")

    monkeypatch.setattr(browser_verify, "_playwright_available", _patlat)
    context = ToolContext(root=tmp_path)
    context.touched.add(tmp_path / "script.js")

    assert (await BrowserVerifier(context).verify()).ok

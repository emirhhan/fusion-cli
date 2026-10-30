"""Site tarama: aynı alan adı, robots.txt, derinlik sınırı, görsel listesi, nazik hız."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import crawl

_SITE = {
    "https://kafe.example/robots.txt": "User-agent: *\nDisallow: /gizli\n",
    "https://kafe.example/": """
        <html><head><title>Kafe</title>
        <meta name="description" content="Üçüncü dalga kahve">
        <meta property="og:image" content="/og.jpg"></head>
        <body><h1>Hoş geldiniz</h1>
        <img src="/hero.jpg" alt="Kafe içi" width="1920" height="1080">
        <img src="data:image/png;base64,AAAA" alt="satır içi">
        <a href="/menu">Menü</a><a href="/gizli/panel">Panel</a>
        <a href="https://baska.example/">Dış</a><a href="/menu#icecek">Menü tekrar</a>
        <a href="/katalog.pdf">PDF</a></body></html>""",
    "https://kafe.example/menu": """
        <html><title>Menü</title><h2>İçecekler</h2>
        <img srcset="/latte-640.webp 640w, /latte-1280.webp 1280w" src="/latte.jpg" alt="Latte">
        <a href="/derin">Derin</a></html>""",
    "https://kafe.example/derin": "<html><title>Derin</title><a href='/en-derin'>x</a></html>",
}


@pytest.fixture
def site(monkeypatch):
    istenen: list[str] = []
    beklemeler: list[float] = []

    def _fetch(url):
        istenen.append(url)
        if url not in _SITE:
            import httpx

            raise httpx.HTTPStatusError("404", request=httpx.Request("GET", url), response=None)
        tur = "text/plain" if url.endswith("robots.txt") else "text/html"
        return tur, _SITE[url], url

    monkeypatch.setattr(crawl, "fetch_following_redirects", _fetch)
    monkeypatch.setattr(crawl, "url_block_reason", lambda _url: None)
    monkeypatch.setattr(crawl, "_sleep", beklemeler.append)
    return istenen, beklemeler


def test_tarama_alan_adinda_kalir_robotsa_uyar_ve_gorselleri_listeler(site, tmp_path):
    istenen, beklemeler = site

    sonuc = crawl.site_crawl({"url": "kafe.example/", "max_depth": 1}, ToolContext(root=tmp_path))

    assert "https://kafe.example/menu" in istenen
    assert not any("baska.example" in url for url in istenen)
    assert not any("/gizli" in url for url in istenen if not url.endswith("robots.txt"))
    assert not any(url.endswith(".pdf") for url in istenen)
    assert istenen.count("https://kafe.example/menu") == 1
    # Derinlik 1: /menu'den bulunan /derin gezilmez.
    assert "https://kafe.example/derin" not in istenen
    assert "https://kafe.example/hero.jpg | alt: Kafe içi | 1920×1080" in sonuc.output
    assert "https://kafe.example/latte-1280.webp" in sonuc.output
    assert "og.jpg" in sonuc.output
    assert "base64" not in sonuc.output
    assert "robots.txt yasaklıyor" in sonuc.output
    assert beklemeler and all(sure >= 1.0 for sure in beklemeler)


def test_sayfa_siniri_asilmaz(site, tmp_path):
    istenen, _ = site

    crawl.site_crawl({"url": "https://kafe.example/", "max_pages": 1}, ToolContext(root=tmp_path))

    sayfalar = [url for url in istenen if not url.endswith("robots.txt")]
    assert sayfalar == ["https://kafe.example/"]


def test_yerel_ag_adresi_taranmaz(tmp_path):
    sonuc = crawl.site_crawl({"url": "http://127.0.0.1:8080/"}, ToolContext(root=tmp_path))

    assert sonuc.output.startswith("HATA") or "Taranamaz" in sonuc.output
    assert "yerel ağ" in sonuc.output


def test_sayfa_ayristirici_basligi_ve_aciklamayi_okur():
    sayfa = crawl.parse_page("https://kafe.example/", _SITE["https://kafe.example/"])

    assert sayfa.title == "Kafe"
    assert sayfa.description == "Üçüncü dalga kahve"
    assert sayfa.headings == ["h1: Hoş geldiniz"]
    assert sayfa.og_image == "https://kafe.example/og.jpg"


# --- Dalga 4 (T1-46) -----------------------------------------------------------------


def test_www_yonlendirmesi_taramayi_tek_sayfada_birakmaz(monkeypatch, tmp_path):
    """`example.com` -> `www.example.com` yönlenince sayfa bağlantıları "başka site" sayılıyordu."""
    istenen: list[str] = []
    sayfalar = {
        "https://ornek.example/": (
            "https://www.ornek.example/",
            '<html><title>Ana</title><a href="https://www.ornek.example/menu">m</a></html>',
        ),
        "https://www.ornek.example/menu": (
            "https://www.ornek.example/menu",
            "<html><title>Menü</title></html>",
        ),
    }

    def _fetch(url):
        istenen.append(url)
        if url.endswith("robots.txt") or url not in sayfalar:
            import httpx

            raise httpx.HTTPStatusError("404", request=httpx.Request("GET", url), response=None)
        son, govde = sayfalar[url]
        return "text/html", govde, son

    monkeypatch.setattr(crawl, "fetch_following_redirects", _fetch)
    monkeypatch.setattr(crawl, "url_block_reason", lambda _u: None)
    monkeypatch.setattr(crawl, "_sleep", lambda _s: None)

    sonuc = crawl.site_crawl({"url": "https://ornek.example/"}, ToolContext(root=tmp_path))

    assert "https://www.ornek.example/menu" in istenen
    assert "2 sayfa okundu" in sonuc.output


def test_robots_5xx_tum_siteyi_yasak_sayar(monkeypatch, tmp_path):
    """RFC 9309: robots.txt 5xx ise tamamen yasak varsay (eskiden "kısıt yok")."""
    import httpx

    istenen: list[str] = []

    def _fetch(url):
        istenen.append(url)
        if url.endswith("robots.txt"):
            yanit = httpx.Response(503, request=httpx.Request("GET", url))
            raise httpx.HTTPStatusError("503", request=yanit.request, response=yanit)
        return "text/html", "<html><title>x</title></html>", url

    monkeypatch.setattr(crawl, "fetch_following_redirects", _fetch)
    monkeypatch.setattr(crawl, "url_block_reason", lambda _u: None)
    monkeypatch.setattr(crawl, "_sleep", lambda _s: None)

    sonuc = crawl.site_crawl({"url": "https://ornek.example/"}, ToolContext(root=tmp_path))

    assert not sonuc.ok
    assert [u for u in istenen if not u.endswith("robots.txt")] == []


def test_robots_404_kisit_yok_sayilir(monkeypatch, tmp_path):
    import httpx

    def _fetch(url):
        if url.endswith("robots.txt"):
            yanit = httpx.Response(404, request=httpx.Request("GET", url))
            raise httpx.HTTPStatusError("404", request=yanit.request, response=yanit)
        return "text/html", "<html><title>x</title></html>", url

    monkeypatch.setattr(crawl, "fetch_following_redirects", _fetch)
    monkeypatch.setattr(crawl, "url_block_reason", lambda _u: None)
    monkeypatch.setattr(crawl, "_sleep", lambda _s: None)

    assert crawl.site_crawl({"url": "https://ornek.example/"}, ToolContext(root=tmp_path)).ok

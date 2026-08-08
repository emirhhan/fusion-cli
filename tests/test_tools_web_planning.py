"""Web araçları (ağsız) ve görev listesi."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import TodoStatus, ToolContext
from fusion_cli.tools import build_registry, web
from fusion_cli.tools.planning import parse_todos
from fusion_cli.tools.web import (
    _DDG_RESULT,
    access_wall_notice,
    clean_result_url,
    parse_bing_rss,
    parse_results,
    strip_html,
    url_block_reason,
)


@pytest.fixture
def context(tmp_path):
    return ToolContext(root=tmp_path)


@pytest.fixture
def registry():
    return build_registry()


# --- HTML işleme (saf) ------------------------------------------------------ #


def test_script_ve_style_bloklari_atilir():
    html = "<p>metin</p><script>kotu()</script><style>.x{}</style>"

    assert "kotu" not in strip_html(html) and "metin" in strip_html(html)


def test_blok_etiketleri_satir_sonuna_cevrilir():
    satirlar = [satir.strip() for satir in strip_html("<p>bir</p><p>iki</p>").splitlines()]

    assert satirlar == ["bir", "iki"]


def test_html_varliklari_cozulur():
    assert strip_html("<p>Tom&#x27;s &amp; Jerry</p>") == "Tom's & Jerry"


def test_yonlendirme_sarmali_cozulur():
    href = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fornek.com%2Fsayfa&rut=x"

    assert clean_result_url(href) == "https://ornek.com/sayfa"


def test_protokolsuz_adres_tamamlanir():
    assert clean_result_url("//ornek.com") == "https://ornek.com"


def test_sonuc_sayfasi_ayristirilir():
    html = (
        '<a class="result__a" href="https://a.com">Baslik A</a>'
        '<a class="result__a" href="https://b.com">Baslik B</a>'
    )

    sonuclar = parse_results(html, _DDG_RESULT)

    assert sonuclar == ["• Baslik A\n  https://a.com", "• Baslik B\n  https://b.com"]


def test_tekrar_eden_adresler_atilir():
    html = (
        '<a class="result__a" href="https://a.com">Bir</a>'
        '<a class="result__a" href="https://a.com">Iki</a>'
    )

    assert len(parse_results(html, _DDG_RESULT)) == 1


def test_gecersiz_adresler_atlanir():
    html = '<a class="result__a" href="javascript:void(0)">Kotu</a>'

    assert parse_results(html, _DDG_RESULT) == []


def test_bing_rss_ayristirilir():
    xml = (
        "<rss><channel>"
        "<item><title>Baslik A</title><link>https://a.com</link></item>"
        "<item><title>Baslik B</title><link>https://b.com</link></item>"
        "</channel></rss>"
    )

    assert parse_bing_rss(xml) == ["• Baslik A\n  https://a.com", "• Baslik B\n  https://b.com"]


def test_bing_rss_tekrar_ve_http_disi_atlanir():
    xml = (
        "<rss><channel>"
        "<item><title>Bir</title><link>https://a.com</link></item>"
        "<item><title>Kopya</title><link>https://a.com</link></item>"
        "<item><title>Kotu</title><link>ftp://x</link></item>"
        "</channel></rss>"
    )

    assert parse_bing_rss(xml) == ["• Bir\n  https://a.com"]


def test_bing_rss_gecersiz_xml_bos_doner():
    assert parse_bing_rss("<rss><channel><item>bozuk") == []


# --- SSRF doğrulama (saf) --------------------------------------------------- #


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://127.0.0.1:8080/admin",
        "http://169.254.169.254/latest/meta-data/",  # bulut metadata ucu
        "http://[::1]/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://0.0.0.0/",
        "file:///etc/passwd",
        "gopher://x/",
        "ftp://host/dosya",
    ],
)
def test_ssrf_tehlikeli_adresler_engellenir(url):
    assert url_block_reason(url) is not None, url


@pytest.mark.parametrize(
    "url",
    [
        "http://8.8.8.8/",  # genel IP, çözülmeye gerek yok
        "https://93.184.216.34/sayfa",  # example.com'un genel IP'si
    ],
)
def test_ssrf_genel_adresler_gecer(url):
    assert url_block_reason(url) is None, url


def test_ssrf_alan_adi_ozel_ip_ye_cozulurse_engellenir(monkeypatch):
    def sahte_getaddrinfo(host, port, **kwargs):
        return [(0, 0, 0, "", ("127.0.0.1", port))]

    monkeypatch.setattr(web.socket, "getaddrinfo", sahte_getaddrinfo)

    assert url_block_reason("http://kotu-alan-adi.example/") is not None


def test_ssrf_cozulemeyen_alan_adi_engellenir(monkeypatch):
    def patlat(host, port, **kwargs):
        raise web.socket.gaierror("çözülemedi")

    monkeypatch.setattr(web.socket, "getaddrinfo", patlat)

    assert "çözülemedi" in url_block_reason("http://yok.example/")


async def test_web_fetch_ozel_adresi_reddeder(registry, context):
    sonuc = await registry.execute("web_fetch", {"url": "http://169.254.169.254/"}, context)

    assert not sonuc.ok and "erişilemez" in sonuc.output


# --- Görev listesi ---------------------------------------------------------- #


async def test_gorev_listesi_yazilir_ve_render_edilir(registry, context):
    sonuc = await registry.execute(
        "todo_write",
        {
            "todos": [
                {"content": "planla", "status": "completed"},
                {"content": "yaz", "status": "in_progress"},
                {"content": "test et", "status": "pending"},
            ]
        },
        context,
    )

    assert sonuc.ok
    assert sonuc.output.splitlines() == ["☒ planla", "▶ yaz", "☐ test et"]


async def test_gorev_listesi_baglamda_saklanir(registry, context):
    await registry.execute(
        "todo_write", {"todos": [{"content": "a", "status": "pending"}]}, context
    )

    assert context.todos.items[0].content == "a"
    assert context.todos.has_pending


async def test_hepsi_tamamlaninca_bekleyen_kalmaz(registry, context):
    await registry.execute(
        "todo_write", {"todos": [{"content": "a", "status": "completed"}]}, context
    )

    assert not context.todos.has_pending


async def test_iki_baglam_ayri_liste_tutar(registry, tmp_path):
    ana = ToolContext(root=tmp_path)
    alt = ToolContext(root=tmp_path)

    await registry.execute(
        "todo_write", {"todos": [{"content": "ana is", "status": "pending"}]}, ana
    )
    await registry.execute(
        "todo_write", {"todos": [{"content": "alt is", "status": "pending"}]}, alt
    )

    assert ana.todos.items[0].content == "ana is"
    assert alt.todos.items[0].content == "alt is"


def test_bilinmeyen_durum_beklemede_sayilir():
    assert parse_todos([{"content": "a", "status": "uydurma"}])[0].status is TodoStatus.PENDING


async def test_bos_icerikli_madde_reddedilir(registry, context):
    sonuc = await registry.execute(
        "todo_write", {"todos": [{"content": "  ", "status": "pending"}]}, context
    )

    assert not sonuc.ok and "content" in sonuc.output


# --------------------------------------------------------------------------- #
# Erişim duvarı — 200 dönen şifre/oturum sayfası başarı sayılmamalı
# --------------------------------------------------------------------------- #


def test_shopify_sifre_duvari_tespit_edilir():
    """Ölçülen gerçek koşu: demo mağaza 200 döndü, model kısıtı hiç fark etmedi."""
    sayfa = (
        "Kalles shopify theme 2 (password: 4)\n\n"
        "This store is password protected. Use the password to enter the store.\n"
        "Enter store password"
    )
    uyari = access_wall_notice(sayfa)

    assert "ERİŞİM DUVARI" in uyari
    assert "UYDURMA" in uyari


def test_normal_sayfada_uyari_cikmaz():
    assert access_wall_notice("<h1>Ürünler</h1> Spor ayakkabı 1.499 TL") == ""


def test_bot_dogrulamasi_da_duvar_sayilir():
    assert access_wall_notice("Checking your browser before accessing the site")


def test_giris_sayfasi_da_duvar_sayilir():
    assert access_wall_notice("Please sign in to continue to your dashboard")


def test_duvar_isareti_sayfanin_derinlerinde_aranmaz():
    """Uzun bir makalede geçen 'sign in to continue' cümlesi duvar değildir."""
    uzun = "içerik " * 3000 + "sign in to continue"
    assert access_wall_notice(uzun) == ""

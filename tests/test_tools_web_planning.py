"""Web araçları (ağsız) ve görev listesi."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import TodoStatus, ToolContext
from fusion_cli.tools import build_registry
from fusion_cli.tools.planning import parse_todos
from fusion_cli.tools.web import _DDG_RESULT, clean_result_url, parse_results, strip_html


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


# --- Görev listesi ---------------------------------------------------------- #


def test_gorev_listesi_yazilir_ve_render_edilir(registry, context):
    sonuc = registry.execute(
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


def test_gorev_listesi_baglamda_saklanir(registry, context):
    registry.execute("todo_write", {"todos": [{"content": "a", "status": "pending"}]}, context)

    assert context.todos.items[0].content == "a"
    assert context.todos.has_pending


def test_hepsi_tamamlaninca_bekleyen_kalmaz(registry, context):
    registry.execute("todo_write", {"todos": [{"content": "a", "status": "completed"}]}, context)

    assert not context.todos.has_pending


def test_iki_baglam_ayri_liste_tutar(registry, tmp_path):
    ana = ToolContext(root=tmp_path)
    alt = ToolContext(root=tmp_path)

    registry.execute("todo_write", {"todos": [{"content": "ana is", "status": "pending"}]}, ana)
    registry.execute("todo_write", {"todos": [{"content": "alt is", "status": "pending"}]}, alt)

    assert ana.todos.items[0].content == "ana is"
    assert alt.todos.items[0].content == "alt is"


def test_bilinmeyen_durum_beklemede_sayilir():
    assert parse_todos([{"content": "a", "status": "uydurma"}])[0].status is TodoStatus.PENDING


def test_bos_icerikli_madde_reddedilir(registry, context):
    sonuc = registry.execute(
        "todo_write", {"todos": [{"content": "  ", "status": "pending"}]}, context
    )

    assert not sonuc.ok and "content" in sonuc.output

"""Araç çağrısı gövdesi kod bloğunda gider; markdown onu bozamaz.

Ölçüldü (6 Eylül canlı koşusu, `cok-dosyali-modul-kur`): model
`{"path":"hesap/__init__.py"}` üretti, web arayüzü `__init__` dizisini kalın metin
olarak çizdi ve sayfadan geri okunan metinde alt çizgiler yoktu. Fusion
`hesap/init.py` yazdı; paket import edilemedi ve görev üst üste düştü.

Payload GÖVDESİ zaten kod bloğundaydı ve bu yüzden hiç bozulmuyordu — bozulan,
çitin dışında kalan çağrı gövdesiydi.
"""

from __future__ import annotations

from fusion_cli.core.tool_emulation import (
    parse_tool_calls,
    render_call,
    render_tool_instructions,
    strip_call_fence,
)


def test_uretilen_cagri_kod_blogunda_gider():
    blok = render_call({"name": "write_file", "arguments": {"path": "hesap/__init__.py"}})

    assert "```json" in blok
    assert "__init__.py" in blok


def test_citli_govde_ayristirilir():
    blok = render_call({"name": "read_file", "arguments": {"path": "hesap/__init__.py"}})

    sonuc = parse_tool_calls(blok)

    assert [c.name for c in sonuc.calls] == ["read_file"]
    assert "hesap/__init__.py" in sonuc.calls[0].arguments


def test_citsiz_govde_de_ayristirilir():
    """Geriye uyum: çiti atlayan model ve eski yanıtlar çalışmaya devam eder."""
    ham = 'FUSION_TOOL_CALL\n{"name":"read_file","arguments":{"path":"a.py"}}\nFUSION_TOOL_CALL_END'

    sonuc = parse_tool_calls(ham)

    assert [c.name for c in sonuc.calls] == ["read_file"]


def test_talimat_metni_citi_gerekce_ile_ister():
    metin = render_tool_instructions([])

    assert "```json" in metin
    assert "alt" in metin and "çizgi" in metin, "kuralın GEREKÇESİ yazılmalı"


def test_strip_call_fence_citsiz_govdeye_dokunmaz():
    assert strip_call_fence('{"a":1}') == '{"a":1}'


# --------------------------------------------------------------------------- #
# Sayfadan geri okuma: backtick METİNDE YOKTUR.
# --------------------------------------------------------------------------- #


def _sayfadan(*satirlar: str) -> str:
    """Tarayıcının çizdiği kod bloğunun `innerText` hâlini kur.

    Çit backtick'leri `<pre>` elemanına dönüştüğü için metinde bulunmaz; yerine
    dil rozeti ve "Kopyala" düğmesinin metni satır olarak düşer.
    """
    return "FUSION_TOOL_CALL\n" + "\n".join(satirlar) + "\nFUSION_TOOL_CALL_END"


def test_rozet_json_a_bitisik_gelirse_de_dusurulur():
    """Ölçüldü: sayfa rozeti JSON'a BİTİŞİK yazıyor — `JSON{"plan_id": …`.

    Satır bazlı temizlik bunu göremiyordu ve tur `geçersiz JSON` ile ölüyordu;
    çit, çözdüğü bozulmanın yerine yenisini koymuş oluyordu.
    """
    ham = "FUSION_TOOL_CALL\nJSON" + '{"name":"read_file","arguments":{"path":"a.py"}}'
    ham += "\nFUSION_TOOL_CALL_END"

    sonuc = parse_tool_calls(ham)

    assert not sonuc.errors
    assert [c.name for c in sonuc.calls] == ["read_file"]


def test_dil_rozeti_json_dan_once_gelirse_dusurulur():
    ham = _sayfadan("json", '{"name":"read_file","arguments":{"path":"hesap/__init__.py"}}')

    sonuc = parse_tool_calls(ham)

    assert not sonuc.errors
    assert "hesap/__init__.py" in sonuc.calls[0].arguments


def test_kopyala_dugmesi_metni_de_dusurulur():
    ham = _sayfadan("json", "Kopyala", '{"name":"read_file","arguments":{"path":"a.py"}}')

    assert [c.name for c in parse_tool_calls(ham).calls] == ["read_file"]


def test_uzun_metin_sus_sayilmaz():
    """Kısa rozet atılır, modelin gerçek cümlesi atılmaz — aksi hâlde sessiz kayıp."""
    from fusion_cli.core.tool_emulation import strip_call_fence

    uzun = "Bu satır modelin kendi açıklamasıdır ve kırk karakterden uzundur."
    govde = f'{uzun}\n{{"name":"read_file"}}'

    assert strip_call_fence(govde) == govde

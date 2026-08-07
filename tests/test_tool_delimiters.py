"""Sınırlayıcılar HTML render eden bir kanalda hayatta kalmalı.

Canlı ölçüm (Gemini web, 5 senaryo): araç isteyen dört senaryonun DÖRDÜ de tamamen
BOŞ yanıt döndürdü; araç istemeyen beşinci senaryo kusursuz cevapladı. Aradaki tek
fark, modelin `<tool_call>` bloğu üretmeye çalışmasıydı.

Sebep: HTML'e benzeyen bir sınırlayıcı, HTML render eden bir kanalda kullanılıyordu.
Sıkı bir temizleyici bilinmeyen elemanı ÇOCUKLARIYLA BİRLİKTE atar; mesaj boşalır.
Model bloğu üretti, arayüz sildi, Fusion "boş cevap" sandı ve tur iş yapmadan bitti.
"""

from __future__ import annotations

import json
import re

from fusion_cli.core.tool_emulation import (
    CALL_CLOSE,
    CALL_OPEN,
    PAYLOAD_CLOSE,
    PAYLOAD_OPEN,
    PAYLOAD_SENTINEL,
    parse_tool_calls,
    render_call,
    render_tool_instructions,
)
from fusion_cli.engines.agent.reflexion import tool_contract_repair_note
from fusion_cli.tools import build_registry

#: Sıkı bir HTML temizleyicinin yaptığı iş: tanımadığı elemanı İÇERİĞİYLE siler.
_UNKNOWN_ELEMENT = re.compile(r"<(?P<tag>[a-z_][a-z0-9_-]*)\b[^>]*>.*?</(?P=tag)>", re.DOTALL)


def _sanitize_like_browser(text: str) -> str:
    """Gözlenen bozulmayı taklit et: bilinmeyen etiket ve içeriği yok olur."""
    return _UNKNOWN_ELEMENT.sub("", text)


def test_kanonik_cagri_html_temizleyicisinden_saglam_cikar():
    """Asıl regresyon: blok temizleyiciden geçtikten SONRA da ayrıştırılabilmeli."""
    cikti = "Şunu yapıyorum.\n" + render_call(
        {"name": "read_file", "arguments": {"path": "src/app.py"}}
    )

    temizlenmis = _sanitize_like_browser(cikti)

    assert temizlenmis == cikti, "kanonik biçim HTML temizleyicisinden etkilenmemeli"
    parse = parse_tool_calls(temizlenmis)
    assert [call.name for call in parse.calls] == ["read_file"]
    assert not parse.errors


def test_eski_html_bicimi_temizleyicide_yok_oluyordu():
    """Kusurun kendisi: eski biçim temizlendiğinde geriye hiçbir şey kalmıyordu."""
    eski = '<tool_call>{"name":"read_file","arguments":{"path":"src/app.py"}}</tool_call>'

    temizlenmis = _sanitize_like_browser(eski)

    assert temizlenmis.strip() == ""
    assert parse_tool_calls(temizlenmis).calls == ()


def test_payload_blogu_da_html_temizleyicisinden_saglam_cikar():
    govde = 'def greet(name):\n    return "Hello!"'
    cikti = "\n".join(
        [
            f'{PAYLOAD_OPEN} id="f1" lines="2"',
            "```python",
            PAYLOAD_SENTINEL,
            govde,
            "```",
            PAYLOAD_CLOSE,
            render_call(
                {
                    "name": "write_file",
                    "arguments": {"path": "greet.py", "content": {"$ref": "f1"}},
                }
            ),
        ]
    )

    parse = parse_tool_calls(_sanitize_like_browser(cikti))

    assert not parse.errors
    assert json.loads(parse.calls[0].arguments)["content"] == govde


def test_sinirlayicilar_html_ya_da_markdown_anlami_tasimaz():
    for isaret in (CALL_OPEN, CALL_CLOSE, PAYLOAD_OPEN, PAYLOAD_CLOSE):
        assert "<" not in isaret and ">" not in isaret
        assert not isaret.startswith(("#", "-", "*", "`", "[", "|", ">"))


def test_talimat_ve_onarim_notu_yalnizca_yeni_bicimi_ogretir():
    """Model iki farklı sözleşme görmemeli."""
    talimat = render_tool_instructions(build_registry().schemas())
    onarim = tool_contract_repair_note("test").content

    for metin in (talimat, onarim):
        assert CALL_OPEN in metin
        assert "<tool_call>" not in metin
        assert "<tool_payload" not in metin


def test_eski_bicim_okumada_hala_desteklenir():
    """Sözleşme değişse de yarıda kalmış konuşmadaki blok ayrıştırılabilmeli."""
    eski = '<tool_call>{"name":"list_dir","arguments":{"path":"."}}</tool_call>'

    parse = parse_tool_calls(eski)

    assert [call.name for call in parse.calls] == ["list_dir"]
    assert not parse.errors


def test_metin_icinde_baslayan_blok_kacirilmaz():
    """Model çoğu zaman bloğu bir cümlenin ardından aynı satırda açıyor."""
    govde = '{"name":"git","arguments":{"subcommand":"status"}}'
    cikti = f"Şunu yapıyorum. {CALL_OPEN} {govde} {CALL_CLOSE}"

    parse = parse_tool_calls(cikti)

    assert [call.name for call in parse.calls] == ["git"]
    assert "Şunu yapıyorum." in parse.text

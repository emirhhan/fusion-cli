"""Payload bütünlüğü — taşıma sırasında bozulan içerik dosyaya YAZILMAZ.

Web arayüzü payload gövdesine dokunabiliyor: dil rozeti ekliyor, kod bloğu sınırı
koyuyor, satır kırıyor. Bozulmayı önleyemeyiz; fark etmek zorundayız. Fark edilmeyen
bozulma, kullanıcının dosyasına bozuk içerik yazmak demektir ve güveni bitiren şey
tam olarak budur.

Bütünlük sinyali `lines="N"`: modelin GÜVENİLİR üretebileceği tek şey. Checksum ya da
base64 istemek, modelin kendi ürettiği metni kodlamasını gerektirirdi; modeller bunu
uydurur ve "doğrulandı" sanılan ama hiç doğrulanmamış bir taşıma elde ederdik.
"""

from __future__ import annotations

import json

from fusion_cli.core.tool_emulation import PAYLOAD_SENTINEL, parse_tool_calls


def _call(path: str = "example.py") -> str:
    payload = {
        "name": "write_file",
        "arguments": {"path": path, "content": {"$ref": "source-1"}},
    }
    return f"<tool_call>{json.dumps(payload)}</tool_call>"


def _payload(body: str, *, declared: int | str) -> str:
    return (
        f'<tool_payload id="source-1" lines="{declared}">\n'
        "```python\n"
        f"{PAYLOAD_SENTINEL}\n"
        f"{body}\n"
        "```\n"
        "</tool_payload>\n"
        f"{_call()}"
    )


def test_dogru_satir_sayisi_iceriği_gecirir() -> None:
    source = "def f():\n    return 1"

    parsed = parse_tool_calls(_payload(source, declared=2))

    assert not parsed.errors
    assert json.loads(parsed.calls[0].arguments)["content"] == source


def test_eksik_satir_bildirimi_icerigi_reddeder() -> None:
    """Taşıma bir satır yutmuşsa çağrı hiç oluşmaz."""
    source = "def f():\n    return 1\n# üçüncü satır"

    parsed = parse_tool_calls(_payload(source, declared=2))

    assert not parsed.calls, "bozuk payload'dan çağrı üretilmemeli"
    assert any("bildirilen 2 satır, geri okunan 3 satır" in error for error in parsed.errors)


def test_fazla_satir_bildirimi_icerigi_reddeder() -> None:
    source = "print('tek satır')"

    parsed = parse_tool_calls(_payload(source, declared=5))

    assert not parsed.calls
    assert any("bildirilen 5 satır, geri okunan 1 satır" in error for error in parsed.errors)


def test_lines_ozniteligi_yoksa_reddedilir() -> None:
    """Doğrulanamayan payload sessizce kabul edilmez."""
    raw = (
        '<tool_payload id="source-1">\n'
        f"{PAYLOAD_SENTINEL}\n"
        "print('x')\n"
        "</tool_payload>\n"
        f"{_call()}"
    )

    parsed = parse_tool_calls(raw)

    assert not parsed.calls
    assert any('lines="N" özniteliği zorunlu' in error for error in parsed.errors)


def test_hata_mesaji_modele_ne_yapacagini_soyler() -> None:
    """Hata eyleme dönüştürülebilir olmalı (RULES.md "Hata Yönetimi")."""
    parsed = parse_tool_calls(_payload("a\nb", declared=9))

    (error,) = [item for item in parsed.errors if "satır" in item]
    assert "içerik YAZILMADI" in error
    assert "yeniden gönder" in error


def test_tarayici_gurultusu_satir_sayimina_girmez() -> None:
    """Rozet ve araç çubuğu satırları içerik değildir; sayım gövdeyi ölçer."""
    source = "import re\nprint(re)"
    raw = (
        '<tool_payload id="source-1" lines="2">\n'
        "```python\n"
        "Python\n"
        "Copy code\n"
        f"{PAYLOAD_SENTINEL}\n"
        f"{source}\n"
        "```\n"
        "</tool_payload>\n"
        f"{_call()}"
    )

    parsed = parse_tool_calls(raw)

    assert not parsed.errors
    assert json.loads(parsed.calls[0].arguments)["content"] == source


def test_kirpilmis_payload_yakalanir() -> None:
    """Yanıt yarıda kesilirse kalan satırlar eksiktir ve bu görülür."""
    tam = "satir-1\nsatir-2\nsatir-3\nsatir-4"
    kirpilmis = "satir-1\nsatir-2"

    saglam = parse_tool_calls(_payload(tam, declared=4))
    bozuk = parse_tool_calls(_payload(kirpilmis, declared=4))

    assert not saglam.errors
    assert not bozuk.calls
    assert any("geri okunan 2 satır" in error for error in bozuk.errors)

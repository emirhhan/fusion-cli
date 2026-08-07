"""Payload bütünlüğü — modelin aritmetiğine değil, doğrulanabilir yapıya dayanır.

Önce `lines="N"` zorunluydu: model gövdenin satır sayısını bildirecek, biz geri
okuduğumuzla karşılaştıracaktık. Canlı ölçüm (Gemini web) bunu çürüttü — dört payload
denemesinde SIFIR gerçek bozulma yakalandı, buna karşılık İKİ kez doğru taşınmış
içerik reddedildi ve ikisinde de görev tamamen durdu:

    bildirilen 3  / geri okunan 2   → sondaki boş satır sayılmış
    bildirilen 33 / geri okunan 28  → dil rozeti, sentinel ve kod bloğu çiti sayılmış

Model gövdeyi doğru üretiyor ama ÇERÇEVEYİ de sayıyor. Yanlış alarmın bedeli,
yakalamadığı riskten büyüktü.

Yerine geçen kontroller modelden hiçbir şey istemez: kapanış işareti, sentinel'in
kesinliği, çerçeve sızıntısı ve boş gövde.
"""

from __future__ import annotations

import json

from fusion_cli.core.tool_emulation import (
    PAYLOAD_CLOSE,
    PAYLOAD_OPEN,
    PAYLOAD_SENTINEL,
    parse_tool_calls,
)


def _call(path: str = "example.py") -> str:
    payload = {
        "name": "write_file",
        "arguments": {"path": path, "content": {"$ref": "source-1"}},
    }
    return f"FUSION_TOOL_CALL\n{json.dumps(payload)}\nFUSION_TOOL_CALL_END"


def _payload(body: str, *, attrs: str = "") -> str:
    return (
        f'{PAYLOAD_OPEN} id="source-1"{attrs}\n'
        "```python\n"
        f"{PAYLOAD_SENTINEL}\n"
        f"{body}\n"
        "```\n"
        f"{PAYLOAD_CLOSE}\n"
        f"{_call()}"
    )


# --- Kabul edilen: doğru taşınmış içerik ------------------------------------- #


def test_dogru_icerik_lines_olmadan_kabul_edilir() -> None:
    source = "def f():\n    return 1"

    parsed = parse_tool_calls(_payload(source))

    assert not parsed.errors, parsed.errors
    assert json.loads(parsed.calls[0].arguments)["content"] == source


def test_yanlis_lines_bildirimi_artik_icerigi_reddetmez() -> None:
    """Canlı vaka: model çerçeveyi de sayıp 33 dedi, gövde 28 satırdı."""
    source = "\n".join(f"satir-{i}" for i in range(28))

    parsed = parse_tool_calls(_payload(source, attrs=' lines="33"'))

    assert not parsed.errors, parsed.errors
    assert json.loads(parsed.calls[0].arguments)["content"] == source


def test_sondaki_bos_satir_reddedilmez() -> None:
    """Canlı vaka: model sondaki boş satırı sayıp 3 dedi, gövde 2 satırdı."""
    source = 'def greet(name: str) -> str:\n    return f"Hello!"'
    ham = (
        f'{PAYLOAD_OPEN} id="source-1" lines="3"\n'
        "```python\n"
        f"{PAYLOAD_SENTINEL}\n"
        f"{source}\n"
        "\n"
        "```\n"
        f"{PAYLOAD_CLOSE}\n"
        f"{_call()}"
    )

    parsed = parse_tool_calls(ham)

    assert not parsed.errors, parsed.errors
    assert json.loads(parsed.calls[0].arguments)["content"].rstrip("\n") == source


def test_gemininin_gercek_ciktisi_ayristirilir() -> None:
    """Canlı ölçümden BİREBİR alınmış çıktı: rozet yutulmuş, sentinel ayıklıyor."""
    ham = (
        f'{PAYLOAD_OPEN} id="file-1" lines="3"\n'
        "\n"
        "Python\n"
        f"{PAYLOAD_SENTINEL}\n"
        "def greet(name: str) -> str:\n"
        '    return f"Hello, {name}!"\n'
        "\n"
        f"{PAYLOAD_CLOSE}\n"
        "FUSION_TOOL_CALL\n"
        '{"name":"write_file","arguments":{"path":"greet.py","content":{"$ref":"file-1"}}}\n'
        "FUSION_TOOL_CALL_END"
    )

    parsed = parse_tool_calls(ham)

    assert not parsed.errors, parsed.errors
    icerik = json.loads(parsed.calls[0].arguments)["content"]
    assert "def greet(name: str) -> str:" in icerik
    assert "Python" not in icerik, "dil rozeti içeriğe sızmamalı"
    assert PAYLOAD_SENTINEL not in icerik


# --- Reddedilen: yapısal bozulma --------------------------------------------- #


def test_bos_govde_reddedilir() -> None:
    parsed = parse_tool_calls(_payload(""))

    assert not parsed.calls
    assert any("gövde boş" in error for error in parsed.errors)


def test_cerceve_isareti_icerikte_kalirsa_reddedilir() -> None:
    """Temizleme başarısızsa içerikte sentinel kalır; bu sessizce yazılmamalı."""
    # Sentinel ilk dört satırda DEĞİLSE gürültü ayıklaması onu bulamaz ve içerikte
    # kalır. Bu, temizlemenin başarısız olduğu anlamına gelir; sessizce yazılmamalı.
    ham = (
        f'{PAYLOAD_OPEN} id="source-1"\n'
        "satir-1\nsatir-2\nsatir-3\nsatir-4\nsatir-5\n"
        f"{PAYLOAD_SENTINEL}\n"
        "gercek icerik\n"
        f"{PAYLOAD_CLOSE}\n"
        f"{_call()}"
    )

    parsed = parse_tool_calls(ham)

    assert not parsed.calls
    assert any("çerçeve işareti içerikte kaldı" in error for error in parsed.errors)


def test_kapanmamis_payload_reddedilir() -> None:
    ham = (
        f'{PAYLOAD_OPEN} id="source-1"\n'
        "```python\n"
        f"{PAYLOAD_SENTINEL}\n"
        "print('x')\n"
        f"{_call()}"
    )

    parsed = parse_tool_calls(ham)

    assert not parsed.calls
    assert any("payload" in error for error in parsed.errors)


def test_kapanmamis_kod_blogu_reddedilir() -> None:
    ham = (
        f'{PAYLOAD_OPEN} id="source-1"\n'
        "```python\n"
        f"{PAYLOAD_SENTINEL}\n"
        "print('x')\n"
        f"{PAYLOAD_CLOSE}\n"
        f"{_call()}"
    )

    parsed = parse_tool_calls(ham)

    assert not parsed.calls
    assert any("code fence" in error for error in parsed.errors)


def test_hata_mesaji_modele_ne_yapacagini_soyler() -> None:
    """Hata eyleme dönüştürülebilir olmalı (RULES.md "Hata Yönetimi")."""
    ham = (
        f'{PAYLOAD_OPEN} id="source-1"\n'
        "satir-1\nsatir-2\nsatir-3\nsatir-4\nsatir-5\n"
        f"{PAYLOAD_SENTINEL}\n"
        "daha\n"
        f"{PAYLOAD_CLOSE}\n"
        f"{_call()}"
    )

    (hata,) = [item for item in parse_tool_calls(ham).errors if "çerçeve" in item]

    assert "sentinel'den SONRA" in hata

"""Tel biçiminin kodlanması ve çözülmesi."""

from __future__ import annotations

import json

from fusion_cli.appserver.protocol import (
    Reply,
    Request,
    decode,
    encode_error,
    encode_event,
    encode_question,
    encode_result,
)


def test_istek_cozulur():
    satir = json.dumps({"tip": "istek", "id": "7", "ad": "tur.calistir", "veri": {"gorev": "x"}})
    sonuc = decode(satir)
    assert isinstance(sonuc, Request)
    assert sonuc.id == "7"
    assert sonuc.name == "tur.calistir"
    assert sonuc.data == {"gorev": "x"}


def test_cevap_cozulur():
    satir = json.dumps({"tip": "cevap", "id": "12", "veri": {"secim": "once"}})
    sonuc = decode(satir)
    assert isinstance(sonuc, Reply)
    assert sonuc.id == "12"
    assert sonuc.data == {"secim": "once"}


def test_bozuk_json_none_doner():
    assert decode("{bozuk") is None


def test_bilinmeyen_tip_none_doner():
    assert decode(json.dumps({"tip": "baska", "id": "1"})) is None


def test_id_olmayan_istek_none_doner():
    assert decode(json.dumps({"tip": "istek", "ad": "x"})) is None


def test_bos_satir_none_doner():
    assert decode("   ") is None


def test_olay_tek_satir_olur():
    satir = encode_event({"olay": "TurnFinished"})
    assert "\n" not in satir
    assert json.loads(satir) == {"tip": "olay", "veri": {"olay": "TurnFinished"}}


def test_sonuc_istek_kimligini_tasir():
    yuk = json.loads(encode_result("7", {"ok": True}))
    assert yuk == {"tip": "sonuc", "id": "7", "veri": {"ok": True}}


def test_soru_kimlik_tasir():
    yuk = json.loads(encode_question("12", {"tur": "onay"}))
    assert yuk == {"tip": "soru", "id": "12", "veri": {"tur": "onay"}}


def test_hata_kodlanir():
    yuk = json.loads(encode_error("bozuk satır"))
    assert yuk["tip"] == "olay"
    assert yuk["veri"]["olay"] == "ProtocolError"
    assert yuk["veri"]["mesaj"] == "bozuk satır"


def test_satir_sonlari_kacisla_tasinir():
    satir = encode_event({"olay": "X", "metin": "bir\niki"})
    assert satir.count("\n") == 0
    assert json.loads(satir)["veri"]["metin"] == "bir\niki"

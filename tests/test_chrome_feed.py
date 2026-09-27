"""Yan panel adımları: tel satırı → kısa, insan dilinde öğe."""

from __future__ import annotations

import json

from fusion_cli.appserver.chrome_feed import panel_item, step_text
from fusion_cli.appserver.protocol import encode_event, encode_question


def _tool(name: str, args: dict, output: str = "{}", outcome: str = "ok") -> str:
    return encode_event(
        {"olay": "ToolExecuted", "name": name, "args": args, "outcome": outcome, "output": output}
    )


def test_tarayici_adimlari_insan_diliyle_yazilir() -> None:
    assert panel_item(
        _tool("chrome_navigate", {"url": "https://www.instagram.com/moto.gate/"})
    ) == {
        "tur": "adim",
        "arac": "chrome_navigate",
        "metin": "instagram.com açıldı",
        "durum": "ok",
    }
    tik = panel_item(_tool("chrome_click", {"ref": "e5"}, json.dumps({"name": "Kampanyalar"})))
    assert tik is not None and tik["metin"] == "“Kampanyalar” tıklandı"
    assert step_text("chrome_action", {"action": "scroll"}) == "Sayfa aşağı kaydırıldı"
    assert (
        step_text("chrome_action", {"action": "scroll", "value": "up"}) == "Sayfa yukarı kaydırıldı"
    )
    assert step_text("chrome_page", {}) == "Sayfa okundu"
    assert step_text("chrome_page", {"query": "Kampanya"}) == "“Kampanya” arandı"
    assert step_text("chrome_action", {"action": "screenshot"}) == "Ekran görüntüsü alındı"


def test_basarisiz_adim_hata_ozetini_tasir_uzun_metin_kisaltilir() -> None:
    item = panel_item(_tool("chrome_type", {"text": "x" * 200}, "Öğe bulunamadı", "failed"))
    assert item is not None
    assert item["durum"] == "failed" and item["hata"] == "Öğe bulunamadı"
    assert item["metin"].endswith("…” yazıldı") and len(item["metin"]) < 80


def test_soru_dusunme_ve_hata_gecer_ilgisiz_olay_gecmez() -> None:
    soru = panel_item(encode_question("3", {"tur": "onay", "baslik": "İzin?"}))
    assert soru == {"tur": "soru", "id": "3", "veri": {"tur": "onay", "baslik": "İzin?"}}
    assert panel_item(encode_event({"olay": "ModelCallStarted", "role": "agent"})) == {
        "tur": "dusunuyor"
    }
    assert panel_item(encode_event({"olay": "ModelCallStarted", "background": True})) is None
    assert panel_item(_tool("read_file", {"path": "a.py"})) is None
    assert panel_item("bozuk satır") is None
    assert panel_item(encode_event({"olay": "ErrorOccurred", "message": "Model yok"})) == {
        "tur": "hata",
        "metin": "Model yok",
    }

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
        _tool("chrome_navigate", {"url": "https://www.instagram.com/ornek.magaza/"})
    ) == {
        "tur": "adim",
        "arac": "chrome_navigate",
        "metin": "instagram.com açıldı",
        "durum": "ok",
        "ayrinti": "https://www.instagram.com/ornek.magaza/",
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
    assert panel_item(_tool("unknown_tool", {})) is None
    assert panel_item("bozuk satır") is None
    assert panel_item(encode_event({"olay": "ErrorOccurred", "message": "Model yok"})) == {
        "tur": "hata",
        "metin": "Model yok",
    }


def test_yeni_tarayici_islemleri_de_insan_diliyle_yazilir() -> None:
    assert step_text("chrome_action", {"action": "back"}) == "Geri gidildi"
    assert step_text("chrome_action", {"action": "text", "value": "2"}) == "Sayfanın tamamı okundu"
    assert step_text("chrome_action", {"action": "click_at", "value": "10,20"}) == (
        "Ekrandaki noktaya tıklandı"
    )


def test_panel_kod_ve_ogretmen_adimlarini_da_gosterir() -> None:
    assert panel_item(_tool("read_file", {"path": "src/App.tsx"}))["metin"] == (
        "src/App.tsx okundu"
    )
    assert panel_item(_tool("write_file", {"path": "src/App.tsx"}))["metin"] == (
        "src/App.tsx yazıldı"
    )
    assert panel_item(_tool("ask_teacher", {"question": "Nasıl uygulanır?"}))["metin"] == (
        "Öğretmene danışıldı"
    )


def test_adimlar_ekran_fare_klavye_kanalini_tasir():
    from fusion_cli.appserver.chrome_feed import control_channel

    assert control_channel("chrome_click", {}) == "fare"
    assert control_channel("chrome_type", {}) == "klavye"
    assert control_channel("chrome_action", {"action": "screenshot"}) == "ekran"
    assert control_channel("chrome_action", {"action": "key"}) == "klavye"
    assert control_channel("chrome_action", {"action": "scroll"}) == "fare"
    assert control_channel("chrome_page", {}) is None
    assert control_channel("chrome_action", {"action": "tabs"}) is None


def test_adim_ayrintisi_hedef_adresi_ve_bulunan_ogeyi_gosterir():
    from fusion_cli.appserver.chrome_feed import step_detail

    cikti = '{"title": "Ads Manager", "url": "https://business.facebook.com/adsmanager"}'
    ayrinti = step_detail(
        "chrome_navigate", {"url": "https://business.facebook.com/adsmanager"}, cikti
    )
    assert "Ads Manager" in ayrinti and ayrinti.count("business.facebook.com/adsmanager") == 1
    assert step_detail("chrome_click", {}, '{"name": "Giriş yap"}') == "Giriş yap"
    assert (
        step_detail("chrome_type", {"text": "gizli-parola"}, '{"name": "Parola"}') == "Alan: Parola"
    )
    assert "gizli-parola" not in step_detail("chrome_type", {"text": "gizli-parola"}, "{}")

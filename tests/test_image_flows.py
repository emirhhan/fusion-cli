"""Görsel iş akışı deposu ve galeri: kaydet/aç, doğrulama, yalnız seçilen yere indir."""

from __future__ import annotations

from fusion_cli.appserver.image_flows import (
    export_image,
    list_flows,
    list_gallery,
    load_flow,
    save_flow,
    validate_flow,
    write_sidecar,
)

_FLOW = {
    "ad": "Kask akışı",
    "dugumler": [
        {"id": "m", "tur": "metin", "x": 1, "y": 2, "istem": "kask", "durum": "bitti"},
        {"id": "u", "tur": "uret", "x": 3, "y": 4, "saglayici": "nvidia_nim/x", "adet": 3},
    ],
    "baglantilar": [{"kaynak": "m", "hedef": "u"}],
}


def test_akis_kaydedilir_listelenir_ve_acilir(tmp_path) -> None:
    saved = save_flow({"akis": _FLOW}, tmp_path)

    assert saved["ok"] is True
    assert list_flows(tmp_path)["akislar"] == [{"id": saved["id"], "ad": "Kask akışı"}]
    loaded = load_flow({"id": saved["id"]}, tmp_path)
    assert loaded["akis"]["dugumler"][0] == {
        "id": "m",
        "tur": "metin",
        "x": 1.0,
        "y": 2.0,
        "istem": "kask",
    }


def test_varyasyon_sayisi_saklanir_aralik_disi_atilir(tmp_path) -> None:
    flow = validate_flow(_FLOW)
    assert flow["dugumler"][1]["adet"] == 3
    bozuk = {**_FLOW, "dugumler": [{**_FLOW["dugumler"][1], "adet": 99}]}
    assert "adet" not in validate_flow({**bozuk, "baglantilar": []})["dugumler"][0]


def test_ayni_kimlikle_kaydetme_uzerine_yazar(tmp_path) -> None:
    first = save_flow({"akis": _FLOW}, tmp_path)
    second = save_flow({"akis": {**_FLOW, "id": first["id"], "ad": "Yeni ad"}}, tmp_path)

    assert second["id"] == first["id"]
    assert list_flows(tmp_path)["akislar"][0]["ad"] == "Yeni ad"


def test_gecersiz_akis_reddedilir(tmp_path) -> None:
    bad = {**_FLOW, "baglantilar": [{"kaynak": "m", "hedef": "yok"}]}
    assert save_flow({"akis": bad}, tmp_path)["ok"] is False
    assert (
        save_flow({"akis": {**_FLOW, "dugumler": [{"id": "x", "tur": "betik"}]}}, tmp_path)["ok"]
        is False
    )
    assert load_flow({"id": "../../etc/passwd"}, tmp_path)["ok"] is False
    assert validate_flow(_FLOW)["ad"] == "Kask akışı"


def test_galeri_istem_ve_saglayiciyi_listeler(tmp_path) -> None:
    image = tmp_path / "a.jpg"
    image.write_bytes(b"\xff\xd8")
    write_sidecar(image, prompt="kask", provider="FLUX.1-dev")

    assert list_gallery(tmp_path)["dosyalar"] == [
        {"yol": str(image), "istem": "kask", "saglayici": "FLUX.1-dev"}
    ]


def test_indir_yalniz_galeriden_ve_secilen_yere_kopyalar(tmp_path) -> None:
    gallery = tmp_path / "galeri"
    gallery.mkdir()
    image = gallery / "a.jpg"
    image.write_bytes(b"\xff\xd8veri")
    outside = tmp_path / "gizli.jpg"
    outside.write_bytes(b"x")
    target = tmp_path / "masaustu" / "kask.jpg"

    assert export_image({"yol": str(image), "hedef": str(target)}, gallery)["ok"] is True
    assert target.read_bytes() == b"\xff\xd8veri"
    assert export_image({"yol": str(outside), "hedef": str(target)}, gallery)["ok"] is False
    assert export_image({"yol": str(image), "hedef": "goreli.jpg"}, gallery)["ok"] is False
    assert (
        export_image({"yol": str(image), "hedef": str(tmp_path / "a.exe")}, gallery)["ok"] is False
    )


def test_galeri_dizini_masaustu_varlik_iznine_acikca_eklidir() -> None:
    """Ölçüldü (30 Eylül, paketli 0.5.9): galeri görselleri "?" olarak görünüyordu.

    Galeri `~/.local/share/fusion-cli/gallery` altında; Tauri'nin kapsam deseni
    Unix'te `**` ile noktayla başlayan klasörü (`.local`) eşleştirmez. Bütün
    gizli klasörleri açmak (~/.ssh dahil) yerine yalnız galeri yolu eklenir.
    """
    import json
    from pathlib import Path

    conf = json.loads(
        (Path(__file__).resolve().parents[1] / "app/src-tauri/tauri.conf.json").read_text()
    )
    scope = conf["app"]["security"]["assetProtocol"]["scope"]

    assert "$HOME/.local/share/fusion-cli/gallery/**" in scope
    assert "$LOCALDATA/fusion-cli/gallery/**" in scope
    assert not any(".ssh" in item or item == "$HOME/.*/**" for item in scope)

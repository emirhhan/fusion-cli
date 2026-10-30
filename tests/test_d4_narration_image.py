"""Giriş anlatımı kesik cümle, görsel içerik doğrulaması ve sağlayıcı hatası (A2-38, A2-39)."""

from __future__ import annotations

from fusion_cli.core.errors import ConfigError
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import image_view
from fusion_cli.engines.agent.narration import _drop_cut_sentence

from .fakes import make_config


def test_kesik_giris_son_tam_cumleye_kirpilir():
    assert _drop_cut_sentence("Önce testi okuyorum. Sonra düzelt") == "Önce testi okuyorum."


def test_hic_tam_cumle_yoksa_giris_bos_olur():
    assert _drop_cut_sentence("Önce testi oku") == ""


def test_png_uzantili_svg_icerik_elenir(tmp_path):
    yol = tmp_path / "logo.png"
    yol.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>")

    uri, sorun = image_view.load_image_data_uri(yol)

    assert uri == "" and sorun is not None and "içeriği" in sorun


def test_gercek_png_kabul_edilir(tmp_path):
    yol = tmp_path / "a.png"
    yol.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)

    uri, sorun = image_view.load_image_data_uri(yol)

    assert sorun is None and uri.startswith("data:image/png;base64,")


def test_gercek_webp_kabul_edilir(tmp_path):
    yol = tmp_path / "a.webp"
    yol.write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 ")

    assert image_view.load_image_data_uri(yol)[1] is None


async def test_gorsel_saglayicisi_kurulamazsa_arac_dusmez(tmp_path, monkeypatch):
    yol = tmp_path / "a.png"
    yol.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)

    def _kur(*args, **kwargs):
        raise ConfigError("anahtar yok")

    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", _kur)
    config = make_config(vision=ModelSpec(name="v", model="x/vision"))

    aciklama, hata = await image_view.describe_image(config, yol, "ne var?")

    assert aciklama == "" and hata is not None and "anahtar yok" in hata

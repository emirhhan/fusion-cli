"""Kullanıcı kalan bağlamı görebilmeli.

Claude'da kalan bağlam görünür; Fusion'da yalnız `/cost` komutu vardı ve sohbet
sessizce sıkıştırılıyordu. Ölçüldü (17 Eylül denetimi): uzun oturumda bağlam
91 mesajdan 13'e indi ve kullanıcı bunu yalnız cevabın bozulmasından anladı.
"""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.appserver.context_gauge import baglam_olcusu
from fusion_cli.config.loader import load_config
from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.types import Message, ModelSpec
from fusion_cli.engines.agent.execution_policy import uses_web_context


def test_web_modelinde_dar_esik_kullanilir() -> None:
    gecmis = [Message("user", "x" * 12_000)]

    olcu = baglam_olcusu(gecmis, web=True)

    assert olcu["sinir"] == 24_000
    assert olcu["yuzde"] == 50


def test_api_modelinde_genis_esik_kullanilir() -> None:
    gecmis = [Message("user", "x" * 17_700)]

    olcu = baglam_olcusu(gecmis, web=False)

    assert olcu["sinir"] == 177_000
    assert olcu["yuzde"] == 10


def test_bagli_web_oturumu_secilen_api_modelinin_baglamini_daraltmaz(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}\n", encoding="utf-8")
    config = replace(
        load_config(config_path),
        web_sessions=(WebSessionConfig(model="gemini_web/main/auto", enabled=True),),
    )
    selected = ModelSpec(
        name="secilen", model="nvidia_nim/nvidia/nemotron-3-super-120b-a12b", tags=("strict",)
    )

    assert not uses_web_context(config, selected)
    assert baglam_olcusu([Message("user", "x" * 24_000)], web=False)["yuzde"] == 14
    assert uses_web_context(
        config,
        replace(selected, tags=(), fallback=("gemini_web/main/auto",)),
    )


def test_bos_gecmis_sifir_doner() -> None:
    assert baglam_olcusu([], web=True)["yuzde"] == 0


def test_yuzde_yuzu_asamaz() -> None:
    """Eşik aşıldıysa gösterge %100'de durur; sıkıştırma zaten devreye girer."""
    olcu = baglam_olcusu([Message("user", "x" * 90_000)], web=True)

    assert olcu["yuzde"] == 100
    assert olcu["kullanilan"] == 90_000

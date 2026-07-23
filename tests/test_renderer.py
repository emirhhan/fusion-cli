"""Render — satır bütünlüğü ve kanal ayrımı (eski "anlamsız görüntü" hatasının testi)."""

from __future__ import annotations

import io

from rich.console import Console

from fusion_cli.core.events import (
    Channel,
    ErrorOccurred,
    ModelCallFinished,
    StatusChanged,
    TokenReceived,
    TurnFinished,
)
from fusion_cli.core.types import ModelResult, TokenUsage
from fusion_cli.ui.renderer import ConsoleRenderer


def _renderer():
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=200, no_color=True)
    return ConsoleRenderer(console), buffer


def test_yarim_satir_varken_durum_satiri_metnin_ustune_binmez():
    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "yarim cumle"))
    renderer.handle(StatusChanged("araç çalıştı"))

    satirlar = buffer.getvalue().splitlines()
    assert satirlar[0] == "yarim cumle"
    assert "araç çalıştı" in satirlar[1]


def test_tam_satirdan_sonra_bos_satir_eklenmez():
    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "tam satir\n"))
    renderer.handle(StatusChanged("durum"))

    assert buffer.getvalue().splitlines()[0] == "tam satir"
    assert "" not in buffer.getvalue().splitlines()[:1]


def test_kanal_degisiminde_satir_kapatilir_ve_baslik_basilir():
    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "ana akis"))
    renderer.handle(TokenReceived(Channel.SUBAGENT, "alt akis"))

    cikti = buffer.getvalue()
    satirlar = cikti.splitlines()
    assert satirlar[0] == "ana akis"
    assert "alt-ajan" in satirlar[1]
    assert satirlar[2] == "alt akis"


def test_ayni_kanalda_pespese_parcalar_birlesir():
    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "mer"))
    renderer.handle(TokenReceived(Channel.MAIN, "haba"))
    renderer.handle(TurnFinished())

    assert buffer.getvalue().splitlines()[0] == "merhaba"


def test_model_ciktisindaki_koseli_parantez_markup_sanilmaz():
    renderer, buffer = _renderer()

    renderer.handle(TokenReceived(Channel.MAIN, "dizi[0] ve [bold] metni\n"))

    assert "dizi[0] ve [bold] metni" in buffer.getvalue()


def test_hata_mesajindaki_markup_yorumlanmaz():
    renderer, buffer = _renderer()

    renderer.handle(ErrorOccurred("beklenmedik [token] geldi"))

    assert "[token]" in buffer.getvalue()


def test_basarili_model_cagrisi_gecikme_ve_token_gosterir():
    renderer, buffer = _renderer()
    result = ModelResult(
        name="agent",
        model="m",
        text="x",
        latency_ms=120,
        ok=True,
        usage=TokenUsage(prompt_tokens=3, completion_tokens=7),
    )

    renderer.handle(ModelCallFinished(role="agent", result=result))

    cikti = buffer.getvalue()
    assert "120" in cikti and "10" in cikti


def test_quiet_modda_durum_basilmaz_ama_metin_akar():
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=200, no_color=True)
    renderer = ConsoleRenderer(console, show_progress=False)

    renderer.handle(StatusChanged("gizli"))
    renderer.handle(TokenReceived(Channel.MAIN, "gorunur\n"))

    cikti = buffer.getvalue()
    assert "gizli" not in cikti
    assert "gorunur" in cikti

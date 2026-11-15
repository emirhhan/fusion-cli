"""Ölçüldü (30 Ekim, gerçek kullanım denemesi): paket günlüğüne işleyici bağlı
olmadığı için Python'un son çare işleyicisi `logger.warning` satırlarını ham hâliyle
terminale basıyordu ("model secenegi tiklanamadi: … Locator.click: Timeout …",
"web oturumu hatasi: …"). Uyarılar artık kullanıcı veri dizinindeki günlük dosyasına
gider; ekrana yalnız olay tabanlı kısa satırlar düşer. Aynı denemede "yedek devrede"
satırı tek turda 12 kez basıldı: aynı yedek geçişi turda bir kez gösterilir."""

from __future__ import annotations

import logging

from rich.console import Console

from fusion_cli.cli import app as app_module
from fusion_cli.core.events import ModelFallbackActivated, TurnFinished
from fusion_cli.ui.renderer import ConsoleRenderer


def test_paket_uyarisi_terminale_degil_gunluk_dosyasina_gider(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(app_module, "user_data_dir", lambda: tmp_path)
    kok = logging.getLogger("fusion_cli")
    eski = list(kok.handlers)
    try:
        app_module.configure_file_logging()
        app_module.configure_file_logging()  # ikinci çağrı işleyici çoğaltmaz
        logging.getLogger("fusion_cli.providers.web_browser").warning("model secenegi tiklanamadi")
        for handler in kok.handlers:
            handler.flush()
        assert "tiklanamadi" not in capsys.readouterr().err
        assert "tiklanamadi" in (tmp_path / "logs" / "fusion.log").read_text(encoding="utf-8")
        assert len([h for h in kok.handlers if h not in eski]) == 1
    finally:
        for handler in [h for h in kok.handlers if h not in eski]:
            kok.removeHandler(handler)
            handler.close()


def _gecis(model: str = "nvidia_nim/x") -> ModelFallbackActivated:
    return ModelFallbackActivated(
        role="secilen", requested_model="gemini_web/main", fallback_model=model, reason="devre açık"
    )


def test_ayni_yedek_gecisi_turda_bir_kez_basilir():
    console = Console(record=True, width=120)
    renderer = ConsoleRenderer(console, show_progress=False, live_progress=False)

    for _ in range(5):
        renderer.handle(_gecis())
    renderer.handle(_gecis("nvidia_nim/y"))
    metin = console.export_text(clear=False)
    assert metin.count("yedek devrede") == 2

    renderer.handle(TurnFinished())
    renderer.handle(_gecis())
    assert console.export_text(clear=False).count("yedek devrede") == 3

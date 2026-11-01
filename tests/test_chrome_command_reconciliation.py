"""Tarayıcı komutunun sonucu kaybolunca "olmadı" denmez; sır adım günlüğüne düşmez (WP09).

Ölçüldü (29 Ekim): eklentiden sonuç gelmeyince (zaman aşımı) tıklama/yazma/gezinme
sıradan bir hata gibi dönüyordu. Model "olmadı" sanıp aynı tıklamayı tekrarlayabilir;
oysa tıklama gerçekleşmiş olabilir ("sepete ekle", "gönder" iki kez çalışır). Eylem
komutunda zaman aşımı artık "sonuç bilinmiyor" diye bildirilir ve önce sayfanın yeniden
okunması istenir. Okuma komutlarında zaman aşımı eskisi gibi düz hatadır.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.appserver.chrome_feed import step_text
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools.chrome import UNKNOWN_OUTCOME_PREFIX, chrome_click, chrome_page


class SessizChrome:
    """Komutu alır ama sonucu hiç döndürmez."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def invoke(self, operation: str, args: dict) -> dict:
        self.calls.append(operation)
        raise TimeoutError("Chrome komutu 30 sn içinde yanıt vermedi.")


def _ctx(tmp_path: Path, chrome: SessizChrome) -> ToolContext:
    return ToolContext(root=tmp_path, chrome=chrome)


async def test_eylemde_zaman_asimi_sonuc_bilinmiyor_der(tmp_path):
    chrome = SessizChrome()

    sonuc = await chrome_click({"ref": "e7"}, _ctx(tmp_path, chrome))

    assert not sonuc.ok
    assert sonuc.output.startswith(UNKNOWN_OUTCOME_PREFIX)
    assert "chrome_page" in sonuc.output and "tekrar" in sonuc.output
    # Önce öğe tarifi okunur (#422 yasak eylem kapısı); okunamazsa tıklama yine denenir.
    assert chrome.calls == ["describe", "click"]


async def test_okumada_zaman_asimi_duz_hatadir(tmp_path):
    sonuc = await chrome_page({}, _ctx(tmp_path, SessizChrome()))

    assert not sonuc.ok
    assert not sonuc.output.startswith(UNKNOWN_OUTCOME_PREFIX)


@pytest.mark.parametrize("gizli", ["sk-proj-abcdefghijklmnopqrstuvwx1234"])
def test_alana_yazilan_sir_adim_gunlugunde_gorunmez(gizli):
    metin = step_text("chrome_type", {"ref": "e3", "text": gizli})

    assert gizli not in metin

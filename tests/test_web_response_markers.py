"""Kapanmış araç çağrısı bloğu "kapanmamış" sayılmaz (C1-01, WP04).

Ölçüldü (28 Ekim): açılış işareti `FUSION_TOOL_CALL`, kapanış işareti
`FUSION_TOOL_CALL_END`'in öneki olduğu için düz sayım kapanışı da açılış sayıyordu;
düzgün kapanmış blok `unclosed_block` sınıflanıp modelden gereksiz yere "eksik bloğu
gönder" isteniyordu.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.tool_emulation import CALL_CLOSE, CALL_OPEN, PAYLOAD_CLOSE, PAYLOAD_OPEN
from fusion_cli.core.web_response import ResponseIntegrity, classify_response


def _sinif(text: str) -> ResponseIntegrity:
    return classify_response(text, truncated=False, has_tool_calls=False)


@pytest.mark.parametrize(
    "metin",
    [
        f"{CALL_OPEN}\n{{}}\n{CALL_CLOSE}",
        f'önce {CALL_OPEN}\n{{"name": "a"}}\n{CALL_CLOSE}\nsonra {CALL_OPEN}\n{{}}\n{CALL_CLOSE}',
        f"{PAYLOAD_OPEN}x{PAYLOAD_CLOSE}",
    ],
)
def test_kapali_blok_acik_sayilmaz(metin):
    assert _sinif(metin) is ResponseIntegrity.OK


@pytest.mark.parametrize(
    "metin",
    [
        f'{CALL_OPEN}\n{{"name": "a"',
        f"{CALL_OPEN}\n{{}}\n{CALL_CLOSE}\n{CALL_OPEN}\n{{",
    ],
)
def test_gercekten_kapanmamis_blok_yakalanir(metin):
    assert _sinif(metin) is ResponseIntegrity.UNCLOSED_BLOCK

"""Sağlayıcı yanıtının protokol kenar durumları (WP04).

Ölçüldü (29 Ekim): araç çağrısında `id` gelmeyince `str(item.id)` "None" üretiyordu.
Kimliksiz iki çağrı aynı "None" kimliğini alıyor; araç sonuçları geçmişe aynı
`tool_call_id` ile yazılıyor ve sağlayıcı sonraki turda eşleşmeyen geçmişi
reddediyordu (OpenAI uyumlu uçlar yinelenen/eksik kimliğe 400 verir).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from fusion_cli.engines.agent.loop_contract import _parse_arguments_checked
from fusion_cli.providers.litellm_provider import _response_tool_calls


def _yanit(*calls: tuple[object, str, str]) -> SimpleNamespace:
    tool_calls = [
        SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=args))
        for call_id, name, args in calls
    ]
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=tool_calls))]
    )


@pytest.mark.parametrize("eksik", [None, "", "  "])
def test_kimliksiz_cagrilar_cakismayan_kimlik_alir(eksik):
    calls = _response_tool_calls(
        _yanit(
            (eksik, "read_file", '{"path": "a"}'),
            (eksik, "read_file", '{"path": "b"}'),
            ("call_1", "list_dir", "{}"),
        )
    )

    ids = [call.id for call in calls]
    assert len(set(ids)) == 3
    assert "None" not in ids and "" not in ids
    assert ids[2] == "call_1", "sağlayıcının verdiği kimlik korunur"


def test_uretilen_kimlik_saglayicinin_kimligiyle_cakismaz():
    calls = _response_tool_calls(
        _yanit(("fusion_call_0", "read_file", "{}"), (None, "read_file", "{}"))
    )

    assert calls[0].id != calls[1].id


def test_yinelenen_saglayici_kimligi_ayristirilir():
    calls = _response_tool_calls(_yanit(("call_1", "a", "{}"), ("call_1", "b", "{}")))

    assert calls[0].id == "call_1"
    assert calls[1].id not in ("call_1", "")


@pytest.mark.parametrize(
    "kesik",
    ['{"command": "rm -rf build', '{"path": "a.py", "content": "yar', '{"path": "a.py",'],
)
def test_kesilmis_arguman_calistirilmaz_hata_doner(kesik):
    args, error = _parse_arguments_checked(kesik)

    assert args == {}
    assert error is not None


def test_tam_nesne_arkasindaki_artik_okunur():
    args, error = _parse_arguments_checked(json.dumps({"q": "x"}) + "\n```")

    assert args == {"q": "x"} and error is None

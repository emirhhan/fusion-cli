"""Tekrar koruması: aynı arama döngüsü turu kesmeden kırılır.

Kaynaklar (MIT): Hermes Agent `agent/tool_guardrails.py` (aynı salt-okunur sonuçta
uyar, 5.'de engelle), OpenClaw `src/agents/tool-loop-detection.ts` (argüman
değişimiyle aynı işi tekrarlamayı yakalar). Ölçüldü (29 Eylül): model aynı glob'u
36 dakika boyunca onlarca kez tekrarladı.
"""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.loop import REPEAT_BLOCK_AT, run_agent

from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
from .test_agent_loop import _deps, _kur

CEVAP = "İnceleme bitti: aranan klasör projede yok, bu yüzden değişiklik yapılmadı."


@pytest.fixture
def sink():
    return RecordingSink()


def _arac_sonuclari(sonuc):
    return [m.content for m in sonuc.messages if m.role == "tool"]


async def test_ayni_arama_besinci_kezde_engellenir_tur_surer(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                *[
                    model_result(tool_calls=[tool_call("glob", pattern="**/*.ts")])
                    for _ in range(6)
                ],
                model_result(CEVAP),
            ]
        ),
    )

    sonuc = await run_agent(
        "mcp klasörünü bul", _deps(tmp_path, sink, runtime={"agent_max_steps": None})
    )

    ciktilar = _arac_sonuclari(sonuc)
    assert sum(c.startswith("TOOL_CALL_CACHED") for c in ciktilar) == REPEAT_BLOCK_AT - 3
    engellenen = [c for c in ciktilar if c.startswith("TOOL_CALL_BLOCKED")]
    assert len(engellenen) == 2
    assert "5. kez" in engellenen[0]
    assert sonuc.final_text == CEVAP


async def test_farkli_argumanla_ayni_sonuc_tekrarlaninca_not_eklenir(monkeypatch, tmp_path, sink):
    desenler = ("mcp", "**/mcp/**", "**/lib/mcp/**/*.ts")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                *[model_result(tool_calls=[tool_call("glob", pattern=d)]) for d in desenler],
                model_result(CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("mcp klasörünü bul", _deps(tmp_path, sink))

    ciktilar = _arac_sonuclari(sonuc)
    assert "birebir aynı sonucu verdi" not in ciktilar[1]
    assert "son 3 farklı çağrıda birebir aynı sonucu verdi" in ciktilar[2]

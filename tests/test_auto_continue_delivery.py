"""Otomatik-devam notu asıl teslimi ezmez.

Ölçüldü (4 Ekim, tarayıcı kabul koşusu): görev listesinde açık madde kaldığı için
"bittiyse tek cümleyle teyit et" notu altı kez gitti; model her seferinde araçsız
"tamamlandı" dedi ve son kısa teyit, fiyatı içeren asıl cevabın yerine geçti.
"""

from __future__ import annotations

from fusion_cli.engines.agent import reflexion
from fusion_cli.engines.agent.loop import run_agent

from .agent_harness import WEB_MODEL, install_provider, web_deps
from .fakes import RecordingSink, model_result, tool_call

TESLIM = "Kırmızı Kask fiyatı: 1.249 TL. Form gönderildi, onay alındı."
TEYIT = "Tamamlandı."


class _Scripted:
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    @property
    def label(self) -> str:
        return WEB_MODEL

    async def complete(self, request):
        index = min(self.calls, len(self._results) - 1)
        self.calls += 1
        return self._results[index]

    async def stream(self, request):
        from fusion_cli.core.types import StreamDone

        yield StreamDone(await self.complete(request))


async def test_confirmation_after_nudge_keeps_delivery_and_stops(monkeypatch, tmp_path):
    saglayici = _Scripted(
        [
            model_result(
                tool_calls=[
                    tool_call(
                        "todo_write",
                        todos=[
                            {"content": "Fiyatı bul", "status": "pending"},
                            {"content": "Formu gönder", "status": "pending"},
                        ],
                    )
                ]
            ),
            model_result(tool_calls=[tool_call("list_dir", path=".")]),
            model_result(TESLIM),
            model_result(TEYIT),
            model_result("Görev %100 tamamlandı."),
        ]
    )
    install_provider(monkeypatch, saglayici)

    sonuc = await run_agent("Bu dizinde ne var, kısaca söyle.", web_deps(tmp_path, RecordingSink()))

    assert TESLIM in sonuc.final_text
    assert saglayici.calls == 4


def test_keep_delivery_prefers_longer_new_delivery():
    assert reflexion.keep_delivery("kısa", "çok daha dolu yeni teslim metni") == (
        "çok daha dolu yeni teslim metni"
    )
    assert reflexion.keep_delivery(TESLIM, TEYIT) == TESLIM
    assert reflexion.keep_delivery("", TEYIT) == TEYIT

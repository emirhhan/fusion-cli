"""Ajan döngüsü — Dalga 2 bulguları (A1/A2/A3 P1 kümesi).

Her test, 29 Ekim triyajında kodda ÖLÇÜLEN bir kusuru sabitler.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, run_agent

from .fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)

TAM_CEVAP = "Tamamlandı: dosya yazıldı ve kontrol edildi, her şey çalışıyor."


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


@pytest.fixture
def sink():
    return RecordingSink()


def _deps(tmp_path, sink, **config_args):
    return AgentDeps(
        config=make_config(**config_args),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )


def _kur(monkeypatch, provider):
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **kwargs: provider)
    return provider


# --- A2-01: son düzeltmeden sonra yeniden doğrulama ----------------------- #


class _SiraliDogrulayici:
    """Verilen sırayla sonuç döner; kaç kez çağrıldığını sayar."""

    def __init__(self, *sonuclar: bool) -> None:
        self._sonuclar = list(sonuclar)
        self.cagri = 0

    async def verify(self):
        ok = self._sonuclar[min(self.cagri, len(self._sonuclar) - 1)]
        self.cagri += 1
        return VerificationResult(
            ok=ok, summary="tamam" if ok else "bozuk", findings=() if ok else ("hata var",)
        )


async def test_son_duzeltme_dogrulanir_ve_basariliysa_tur_ok(monkeypatch, tmp_path, sink):
    """Ölçüldü (29 Ekim): iki başarısız doğrulama + işe yarayan ikinci düzeltme
    turu eskiden bayat `verification` yüzünden `ok=False` bitiyordu."""
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="1")]),
                model_result(TAM_CEVAP),
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="2")]),
                model_result(TAM_CEVAP),
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="3")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, sink)
    deps.verifier = _SiraliDogrulayici(False, False, True)

    sonuc = await run_agent("a.txt yaz", deps)

    assert deps.verifier.cagri == 3
    assert sonuc.ok


# --- A2-02: boş yanıt hakkı bitince başarı bildirilmez ---------------------- #


async def test_bos_yanit_hakki_bitince_tur_basarisiz_ve_aciklamali(monkeypatch, tmp_path, sink):
    """Ölçüldü (29 Ekim): boş yanıt hakkı bitince `_outcome(...)` varsayılanı
    `ok=True`, `budget_stopped=False` ve boş metinle bitiyordu."""
    _kur(monkeypatch, ScriptedProvider([model_result("")] * 6))
    deps = _deps(tmp_path, sink)

    sonuc = await run_agent("bir şey yap", deps)

    assert not sonuc.ok
    assert sonuc.budget_stopped
    assert sonuc.stop_reason == "empty_responses"
    assert sonuc.final_text.strip()


# --- A2-03: boş / sözleşme hatalı yanıt geri çekilmeyle AYNEN gönderilmez --- #


async def test_bos_yanit_ustel_geri_cekilmeye_girmez(monkeypatch, tmp_path, sink):
    """Ölçüldü (29 Ekim): `ok` ama boş yanıt `retryable` sayılıp yansıtıcı not
    eklenmeden `model_retry_attempts` kez aynen yeniden gönderiliyordu."""
    beklemeler: list[float] = []

    async def _sahte_bekle(delay_s: float) -> None:
        beklemeler.append(delay_s)

    monkeypatch.setattr(agent_loop, "_retry_sleep", _sahte_bekle)
    _kur(monkeypatch, ScriptedProvider([model_result(""), model_result(TAM_CEVAP)]))

    sonuc = await run_agent(
        "bir şey yap", _deps(tmp_path, sink, runtime={"model_retry_attempts": 3})
    )

    assert beklemeler == []
    assert any("boş" in m.content.lower() for m in sonuc.messages if m.role == "user")


async def test_sozlesme_hatali_yanit_ustel_geri_cekilmeye_girmez(monkeypatch, tmp_path, sink):
    beklemeler: list[float] = []

    async def _sahte_bekle(delay_s: float) -> None:
        beklemeler.append(delay_s)

    monkeypatch.setattr(agent_loop, "_retry_sleep", _sahte_bekle)
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result("", ok=False, error="TOOL_CALL_INVALID: bozuk argüman"),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent(
        "bir şey yap", _deps(tmp_path, sink, runtime={"model_retry_attempts": 3})
    )

    assert beklemeler == []
    assert sonuc.ok

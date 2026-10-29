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


# --- A2-04: sözleşme hatasıyla düşen çağrı "yapılmış" sayılmaz -------------- #


async def test_once_oku_hatasindan_sonra_ayni_yazma_tekrar_kapisina_takilmaz(
    monkeypatch, tmp_path, sink
):
    """Ölçüldü (29 Ekim): web modeli var olan küçük dosyaya `write_file` -> "önce
    oku" hatası -> okur -> AYNI `write_file` çağrısı `TOOL_CALL_DUPLICATE` ile
    engelleniyordu (imza hata anında sayılmış, unutulmamıştı)."""
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

    (tmp_path / "a.txt").write_text("eski\n", encoding="utf-8")
    yaz = tool_call("write_file", path="a.txt", content="yeni\n")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[yaz]),
                model_result(tool_calls=[tool_call("read_file", path="a.txt")]),
                model_result(tool_calls=[yaz]),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, sink)
    deps.execution = ExecutionPolicy(is_web=True, max_tool_rounds=12, max_model_calls=16)

    await run_agent("a.txt dosyasını değiştir", deps)

    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "yeni\n"


# --- A1-18: web öğretmenine sır dosyası / kök dışı görsel gitmez ------------ #


@pytest.mark.parametrize(
    "ad",
    [
        "id_rsa",
        "deploy.pem",
        "credentials.json",
        "secrets.enc",
        ".npmrc",
        "terraform.tfstate",
        "prod.tfvars",
        ".env.local",
        "service-account.json",
    ],
)
def test_ogretmen_kesitine_sir_dosyasi_girmez(tmp_path, ad):
    from fusion_cli.engines.agent.engine_tools import _teacher_excerpts

    sir = tmp_path / ad
    sir.write_text("GIZLI_ICERIK_xyz", encoding="utf-8")
    kod = tmp_path / "app.py"
    kod.write_text("print('merhaba')\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)
    context.touched.update({sir, kod})

    kesitler = _teacher_excerpts(context)

    assert [yol for yol, _ in kesitler] == ["app.py"]
    assert "GIZLI_ICERIK_xyz" not in repr(kesitler)


def test_ogretmen_kesiti_kaynak_kod_adlarini_sir_saymaz(tmp_path):
    """`token.py` / `reset-password.tsx` kaynak koddur; yanlış pozitif olmamalı."""
    from fusion_cli.engines.agent.engine_tools import _teacher_excerpts

    dosyalar = [tmp_path / "token.py", tmp_path / "reset-password.tsx"]
    for dosya in dosyalar:
        dosya.write_text("x = 1\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)
    context.touched.update(dosyalar)

    assert len(_teacher_excerpts(context)) == 2


def test_ogretmen_kesiti_kok_disindaki_dosyayi_gondermez(tmp_path):
    from fusion_cli.engines.agent.engine_tools import _teacher_excerpts

    proje = tmp_path / "proje"
    proje.mkdir()
    disarida = tmp_path / "notlar.txt"
    disarida.write_text("özel not", encoding="utf-8")
    context = ToolContext(root=proje)
    context.touched.add(disarida)

    assert _teacher_excerpts(context) == []


def test_ogretmen_kesiti_buyuk_dosyayi_kirpar(tmp_path):
    from fusion_cli.engines.agent.engine_tools import _TEACHER_EXCERPT_CHARS, _teacher_excerpts

    buyuk = tmp_path / "big.py"
    buyuk.write_text("a" * (_TEACHER_EXCERPT_CHARS * 3), encoding="utf-8")
    context = ToolContext(root=tmp_path)
    context.touched.add(buyuk)

    ((_, icerik),) = _teacher_excerpts(context)

    assert len(icerik) <= _TEACHER_EXCERPT_CHARS


def test_ogretmen_gorseli_kok_disindan_alinmaz(tmp_path):
    from fusion_cli.core.tools import ToolResult
    from fusion_cli.engines.agent.engine_tools import _teacher_images

    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / "ekran.png").write_bytes(b"\x89PNG")
    disarida = tmp_path / "ozel.png"
    disarida.write_bytes(b"\x89PNG")
    # Varsayılan yapılandırma (`restrict_to_root=False`) kök dışına izin verir.
    context = ToolContext(root=proje, restrict_to_root=False)

    assert isinstance(_teacher_images([str(disarida)], context), ToolResult)
    assert isinstance(_teacher_images(["../ozel.png"], context), ToolResult)
    icerde = _teacher_images(["ekran.png"], context)
    assert isinstance(icerde, tuple) and len(icerde) == 1

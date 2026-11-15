"""Kabuk komutu çalışma alanı parmak izi: dosya değiştirmeyen komut kanıtı eskitmez (30 Ekim).

Ölçüldü (g3/y3): edit -> `pytest` geçti -> modelin elle denediği `python3 -m gorevler.cli
listele` (tanınmayan program) dosya DEĞİŞTİRMEDİĞİ hâlde mutasyon sayıldı; testler bayatladı,
tur "⚠ Görev kısmi kaldı" bitti ve ekranda "hiçbir doğrulama başarıyla çalışmadı; bu iddia
GEÇERSİZ" yazdı. Parmak izi komut öncesi/sonrası proje kökünü karşılaştırır.
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import replace

import pytest

from fusion_cli.core.events import ToolExecuted
from fusion_cli.core.evidence import ToolUse
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.workspace_fingerprint import (
    WorkspaceEffect,
    changed_paths,
    launches_background_process,
    take_fingerprint,
)
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.engines.agent.turn_report import build_turn_report
from fusion_cli.memory.checkpoint_evidence import _effect, _tool, _tool_payload
from fusion_cli.tools.shell import run_shell

from .fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)

# --- Parmak izi ------------------------------------------------------------------- #


def test_parmak_izi_gurultu_dizinlerini_atlar(tmp_path):
    (tmp_path / "a.py").write_text("x")
    for ad in (".git", "node_modules", ".venv", "__pycache__", "dist", "build", ".fusion"):
        (tmp_path / ad).mkdir()
        (tmp_path / ad / "y.txt").write_text("y")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.pyc").write_text("c")
    (tmp_path / ".DS_Store").write_text("")

    izi = take_fingerprint(tmp_path)

    assert izi is not None and set(izi) == {"a.py"}


def test_parmak_izi_degisen_eklenen_silinen_dosyayi_adiyla_bulur(tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.py").write_text("x")
    once = take_fingerprint(tmp_path)
    (tmp_path / "a.py").write_text("daha uzun")
    (tmp_path / "b.py").unlink()
    (tmp_path / "c.py").write_text("yeni")

    assert changed_paths(once, take_fingerprint(tmp_path)) == ("a.py", "b.py", "c.py")


def test_parmak_izi_dosya_siniri_asilirsa_olculemedi(tmp_path):
    for sayi in range(5):
        (tmp_path / f"{sayi}.txt").write_text("x")

    assert take_fingerprint(tmp_path, max_files=3) is None


def test_parmak_izi_sure_siniri_asilirsa_olculemedi(tmp_path):
    for sayi in range(600):
        (tmp_path / f"{sayi}.txt").write_text("x")
    saat = iter(range(0, 10_000, 1))

    assert take_fingerprint(tmp_path, max_seconds=1.0, clock=lambda: float(next(saat))) is None


def test_parmak_izi_kok_yoksa_olculemedi(tmp_path):
    assert take_fingerprint(tmp_path / "yok") is None


@pytest.mark.parametrize(
    ("komut", "arka_plan"),
    [
        ("python3 sunucu.py &", True),
        ("nohup python3 s.py", True),
        ("python3 -m http.server & sleep 1", True),
        ("python3 a.py && python3 b.py", False),
        ("python3 a.py 2>&1 | tail", False),
        ("python3 a.py &> cikti.txt", False),
        ("echo 'a & b'", False),
    ],
)
def test_arka_plan_sureci_tespiti(komut, arka_plan):
    assert launches_background_process(komut) is arka_plan


# --- run_shell: ölçüm sonucu --------------------------------------------------------- #


def _gorevler(tmp_path):
    """y3'teki küçük uygulamanın iskeleti: `listele` dosya yazmaz, `ekle` yazar."""
    paket = tmp_path / "gorevler"
    paket.mkdir()
    (paket / "__init__.py").write_text("")
    (paket / "cli.py").write_text(
        textwrap.dedent(
            """
            import sys
            if sys.argv[1] == "ekle":
                open("gorevler.json", "w").write("[]")
            print("tamam")
            """
        )
    )


def test_run_shell_dosya_degistirmeyen_komut_degismedi_olarak_olculur(tmp_path):
    _gorevler(tmp_path)
    context = ToolContext(root=tmp_path)

    sonuc = run_shell({"command": "python3 -m gorevler.cli listele"}, context)

    assert sonuc.ok and sonuc.workspace_effect is not None
    assert sonuc.workspace_effect.changed == ()
    assert sonuc.workspace_effect.label == "değişmedi"


def test_run_shell_dosya_degistiren_komut_adiyla_kaydedilir(tmp_path):
    _gorevler(tmp_path)
    context = ToolContext(root=tmp_path)

    sonuc = run_shell({"command": "python3 -m gorevler.cli ekle"}, context)

    assert sonuc.workspace_effect is not None
    assert sonuc.workspace_effect.changed == ("gorevler.json",)
    assert sonuc.workspace_effect.label == "1 dosya değişti: gorevler.json"


def test_run_shell_arka_plan_komutu_olculemedi_sayilir(tmp_path):
    sonuc = run_shell({"command": "python3 -c pass &"}, ToolContext(root=tmp_path))

    assert sonuc.workspace_effect == WorkspaceEffect(None, "arka plan süreci")


def test_run_shell_ayar_kapaliysa_olculmez(tmp_path):
    context = ToolContext(root=tmp_path, shell_fingerprint=False)

    assert run_shell({"command": "python3 -c 'pass'"}, context).workspace_effect is None


def test_run_shell_salt_okunur_komut_olculmez(tmp_path):
    assert run_shell({"command": "ls"}, ToolContext(root=tmp_path)).workspace_effect is None


def test_run_shell_sinir_asilirsa_olculemedi(tmp_path, monkeypatch):
    from functools import partial

    from fusion_cli.core import workspace_fingerprint as modul
    from fusion_cli.tools import shell as kabuk_modulu

    dar = partial(modul.take_fingerprint, max_files=1)
    monkeypatch.setattr(kabuk_modulu, "take_fingerprint", dar)
    monkeypatch.setattr(modul, "take_fingerprint", dar)
    for sayi in range(3):
        (tmp_path / f"{sayi}.txt").write_text("x")

    sonuc = run_shell({"command": "python3 -c 'pass'"}, ToolContext(root=tmp_path))

    assert sonuc.workspace_effect is not None and sonuc.workspace_effect.changed is None
    assert sonuc.workspace_effect.label.startswith("ölçülemedi")


# --- Tur raporu: kanıt tazeliği -------------------------------------------------------- #


def _yaz(yol: str) -> ToolUse:
    return ToolUse(name="write_file", ok=True, mutating=True, arguments={"path": yol})


def _kabuk(komut: str, cikti: str = "", *, etki: WorkspaceEffect | None = None) -> ToolUse:
    return ToolUse(
        name="run_shell",
        ok=True,
        mutating=True,
        arguments={"command": komut},
        output=f"(çıkış kodu 0)\n{cikti}",
        workspace_effect=etki,
    )


_TEST = "python3 -m pytest -q"
_LISTELE = "python3 -m gorevler.cli listele"


def _g3(etki: WorkspaceEffect | None):
    return build_turn_report(
        ("gorevler/depo.py",),
        (_yaz("gorevler/depo.py"), _kabuk(_TEST, "3 passed in 0.1s"), _kabuk(_LISTELE, etki=etki)),
        None,
    )


def test_dosya_degistirmeyen_komut_onceki_test_kanitini_bayatlatmaz():
    rapor = _g3(WorkspaceEffect(()))

    assert rapor.is_verified is True
    assert "✓ Doğrulandı" in rapor.render()
    assert not rapor.blocks_success


def test_olculmemis_komut_eski_temkinli_davranista_kalir():
    rapor = _g3(None)

    assert rapor.is_verified is False
    assert "Test bundan önce geçmişti" in rapor.render()


def test_olculemeyen_komut_temkinli_kalir():
    assert _g3(WorkspaceEffect(None, "arka plan süreci")).is_verified is False


def test_dosya_degistiren_komut_kaniti_bayatlatir_ve_dosyayi_adlandirir():
    rapor = _g3(WorkspaceEffect(("gorevler.json",)))

    metin = rapor.render()
    assert rapor.is_verified is False
    assert "dosyaları değiştirdi (gorevler.json)" in metin
    assert "gorevler.json" in rapor.changed_paths


def test_kabuk_degisikligi_tek_basina_yeni_rapor_yuzeyi_acmaz():
    rapor = build_turn_report(
        (), (_kabuk("python3 uret.py", etki=WorkspaceEffect(("cikti.csv",))),), None
    )

    assert rapor.changed_paths == () and rapor.render() == ""


def test_bayat_kanitta_sert_gecersiz_mesaji_yerine_dogru_mesaj():
    rapor = _g3(WorkspaceEffect(("gorevler.json",)))

    metin = rapor.render_with_model_text("Tüm testler geçti.")

    assert "GEÇERSİZ" not in metin
    assert (
        f"testler daha önce geçmişti ama sonra `{_LISTELE}` çalıştı ve dosyaları değiştirdi; "
        "doğrulama yeniden çalıştırılmalı" in metin
    )


def test_olculemeyen_bayat_kanitta_degistirmis_olabilir_denir():
    metin = _g3(None).render_with_model_text("Testler geçti.")

    assert "dosyaları değiştirmiş olabilir; doğrulama yeniden çalıştırılmalı" in metin
    assert "GEÇERSİZ" not in metin


def test_hic_dogrulama_yoksa_sert_mesaj_kalir():
    rapor = build_turn_report(("a.py",), (_yaz("a.py"),), None)

    assert "bu iddia GEÇERSİZ" in rapor.render_with_model_text("Tüm testler geçti.")


def test_test_sonradan_dosya_duzenlenince_de_bayat_mesaj_kullanilir():
    rapor = build_turn_report(("a.py",), (_kabuk(_TEST, "1 passed"), _yaz("a.py")), None)

    metin = rapor.render_with_model_text("Testler geçti.")

    assert "dosyalar yeniden değişti" in metin and "GEÇERSİZ" not in metin


# --- Checkpoint kalıcılığı ------------------------------------------------------------ #


@pytest.mark.parametrize(
    "etki",
    [WorkspaceEffect(()), WorkspaceEffect(("a.py",)), WorkspaceEffect(None, "arka plan süreci")],
)
def test_calisma_alani_etkisi_checkpointten_geri_okunur(etki):
    kullanim = _kabuk("python3 x.py", etki=etki)

    assert _tool(json.loads(json.dumps(_tool_payload(kullanim)))).workspace_effect == etki


def test_eski_checkpoint_kaydinda_olcum_uydurulmaz():
    assert _effect({"name": "run_shell"}) is None


# --- Uçtan uca: g3/y3 sırası -------------------------------------------------------- #


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


def _kur(monkeypatch, provider):
    def _build(spec, **kwargs):
        del spec, kwargs
        return provider

    monkeypatch.setattr(agent_loop, "build_provider", _build)


def _deps(tmp_path, sink, **context):
    return AgentDeps(
        config=make_config(runtime={"self_review": False}),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path, **context),
    )


def _sahte_pytest(tmp_path):
    betik = tmp_path / "pytest"
    betik.write_text("#!/bin/sh\necho '3 passed in 0.1s'\nexit 0\n", encoding="utf-8")
    betik.chmod(0o755)


def _senaryo(komut: str) -> ScriptedProvider:
    return ScriptedProvider(
        [
            model_result(
                tool_calls=[tool_call("write_file", path="gorevler/depo.py", content="x")]
            ),
            model_result(tool_calls=[tool_call("run_shell", command="./pytest -q")]),
            model_result(tool_calls=[tool_call("run_shell", command=komut)]),
            model_result("Tamamlandı. Tüm testler geçti."),
        ]
    )


async def test_g3_dosya_degistirmeyen_komut_turu_tamamlandi_birakir(monkeypatch, tmp_path):
    _gorevler(tmp_path)
    _sahte_pytest(tmp_path)
    sink = RecordingSink()
    _kur(monkeypatch, _senaryo(_LISTELE))

    sonuc = await run_agent("depoya temizle ekle", _deps(tmp_path, sink))

    assert sonuc.ok is True
    assert "✓ Doğrulandı" in sonuc.final_text and "GEÇERSİZ" not in sonuc.final_text
    olay = [e for e in sink.events if isinstance(e, ToolExecuted) and e.workspace]
    assert [e.workspace for e in olay] == ["değişmedi", "değişmedi"]


async def test_g3_dosya_degistiren_komut_kaniti_bayatlatir(monkeypatch, tmp_path):
    _gorevler(tmp_path)
    _sahte_pytest(tmp_path)
    sink = RecordingSink()
    _kur(monkeypatch, _senaryo("python3 -m gorevler.cli ekle"))

    sonuc = await run_agent("depoya temizle ekle", _deps(tmp_path, sink))

    assert sonuc.ok is False, "bayat kanıtla 'testler geçti' demek başarı sayılmaz"
    assert "dosyaları değiştirdi" in sonuc.final_text and "GEÇERSİZ" not in sonuc.final_text
    olay = [e for e in sink.events if isinstance(e, ToolExecuted) and e.workspace]
    assert [e.workspace for e in olay] == ["değişmedi", "1 dosya değişti: gorevler.json"]


async def test_g3_ayar_kapaliysa_eski_temkinli_davranis(monkeypatch, tmp_path):
    _gorevler(tmp_path)
    _sahte_pytest(tmp_path)
    sink = RecordingSink()
    _kur(monkeypatch, _senaryo(_LISTELE))

    sonuc = await run_agent("depoya temizle ekle", _deps(tmp_path, sink, shell_fingerprint=False))

    assert sonuc.ok is False and "değiştirmiş olabilir" in sonuc.final_text
    assert not any(e.workspace for e in sink.events if isinstance(e, ToolExecuted))


def test_team_scope_ayari_alt_ajana_tasir(tmp_path):
    from fusion_cli.engines.agent.team_scope import derive_sub_context

    kapali = replace(ToolContext(root=tmp_path), shell_fingerprint=False)

    assert derive_sub_context(kapali, None).shell_fingerprint is False

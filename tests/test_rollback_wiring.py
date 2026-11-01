"""Geri alma plan yürütücüsüne bağlı.

Denetlendi (6 Eylül): `core/rollback.py` yazıldı ve test edildi ama plan yürütücüsü
onu HİÇ çağırmıyordu — başarısız deneme diske yarım durum bırakmaya devam ediyordu.
Modülün var olması, Fusion'ın onu kullanabildiği anlamına gelmez.

Ayırt edici senaryo: düşen deneme, başarılı denemenin DOKUNMADIĞI bir artık dosya
bırakır. Geri alma yoksa o dosya diskte kalır ve sonraki adım onunla uğraşır.
"""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.core.execution_plan import ExecutionPlan, VerificationCheck, VerificationCheckKind
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_runner import run_execution_plan
from tests.test_plan_repair import _deps, _step


def _adim(ad: str, path: str):
    adim = _step(ad, expected_effects=(f"file:{path}",))
    return replace(
        adim,
        verification_checks=(
            VerificationCheck(
                adim.success_criteria[0], VerificationCheckKind.FILE_CONTAINS, path, "sağlam"
            ),
        ),
    )


def _yaz(context, ad: str, icerik: str, tmp_path) -> None:
    """Gerçek araç yolu gibi: yazmadan ÖNCE değişiklik kaydına gir."""
    yol = tmp_path / ad
    context.changes.record(yol)
    yol.write_text(icerik, encoding="utf-8")
    context.changes.record_applied(yol)


async def test_dusen_denemenin_artigi_geri_alinir(tmp_path):
    plan = ExecutionPlan("rb", "iş", (_adim("yaz", "kod.py"),))
    deps = _deps(tmp_path)
    turlar: list[str] = []

    async def agent(task, agent_deps, **kwargs):
        turlar.append(task)
        context = agent_deps.tool_context
        if len(turlar) == 1:
            _yaz(context, "kod.py", "yarim", tmp_path)
            _yaz(context, "artik.py", "yarim kalan deneme", tmp_path)
        else:
            _yaz(context, "kod.py", "sağlam", tmp_path)
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=1, tool_calls_made=1)

    sonuc = await run_execution_plan("iş", deps, agent, plan=plan)

    assert sonuc.ok
    assert (tmp_path / "kod.py").read_text(encoding="utf-8") == "sağlam"
    assert not (tmp_path / "artik.py").exists()


async def test_dogrulanan_adim_ciktisi_silinmez(tmp_path):
    plan = ExecutionPlan("rb2", "iş", (_adim("yaz", "kod.py"),))
    deps = _deps(tmp_path)

    async def agent(task, agent_deps, **kwargs):
        _yaz(agent_deps.tool_context, "kod.py", "sağlam", tmp_path)
        _yaz(agent_deps.tool_context, "yan.py", "korunmalı", tmp_path)
        return AgentOutcome(final_text="tamam", messages=[], model_calls_made=1, tool_calls_made=1)

    sonuc = await run_execution_plan("iş", deps, agent, plan=plan)

    assert sonuc.ok
    assert (tmp_path / "yan.py").is_file()


async def test_geri_alma_cakismasi_bildirilir_ve_otomatik_yeniden_yazma_durur(tmp_path):
    from fusion_cli.core.events import StatusChanged
    from fusion_cli.tools.files import edit_file

    plan = ExecutionPlan("conflict", "iş", (_adim("yaz", "kod.py"),))
    deps = _deps(tmp_path)
    yol = tmp_path / "kod.py"
    yol.write_text("ilk", encoding="utf-8")
    calls = []

    async def agent(task, agent_deps, **kwargs):
        calls.append(task)
        if len(calls) > 1:
            return AgentOutcome(final_text="dur", messages=[], model_calls_made=1, ok=False)
        result = edit_file(
            {"path": "kod.py", "old": "ilk", "new": "yarim"}, agent_deps.tool_context
        )
        assert result.ok, result.output
        yol.write_text("kullanici", encoding="utf-8")
        return AgentOutcome(
            final_text="denendi", messages=[], model_calls_made=1, tool_calls_made=1
        )

    sonuc = await run_execution_plan("iş", deps, agent, plan=plan)

    assert not sonuc.ok
    assert len(calls) == 1
    assert yol.read_text(encoding="utf-8") == "kullanici"
    assert deps.tool_context.changes.conflicts[0].path == yol
    assert any(
        isinstance(event, StatusChanged) and "çakış" in event.message and "kod.py" in event.message
        for event in deps.publisher.events
    )
    assert "kod.py" in sonuc.final_text


def test_checkpoint_cakisan_dosyanin_ilk_kaydini_korur(tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.core.turn_checkpoints import RewindScope, TurnCheckpointLedger
    from fusion_cli.tools.files import edit_file

    yol = tmp_path / "kod.py"
    yol.write_text("ilk", encoding="utf-8")
    ledger = TurnCheckpointLedger(clock=lambda: 0)
    checkpoint = ledger.begin("iş", ())
    context = ToolContext(root=tmp_path, changes=checkpoint.changes)
    assert edit_file({"path": "kod.py", "old": "ilk", "new": "ajan"}, context).ok
    yol.write_text("kullanici", encoding="utf-8")

    result = ledger.rewind(checkpoint.index, RewindScope.CODE)

    assert result.failed == (yol,)
    assert yol.read_text(encoding="utf-8") == "kullanici"
    retained = ledger.find(checkpoint.index)
    assert retained is not None
    assert retained.changes.snapshots[0].content == b"ilk"


def test_undo_cakismada_kaydi_ve_kullanici_dosyasini_korur(tmp_path):
    from types import SimpleNamespace

    from fusion_cli.cli.repl.commands import _undo
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.core.turn_checkpoints import TurnCheckpointLedger
    from fusion_cli.tools.files import edit_file

    yol = tmp_path / "kod.py"
    yol.write_text("ilk", encoding="utf-8")
    context = ToolContext(root=tmp_path)
    assert edit_file({"path": "kod.py", "old": "ilk", "new": "ajan"}, context).ok
    yol.write_text("kullanici", encoding="utf-8")
    state = SimpleNamespace(checkpoints=TurnCheckpointLedger(), last_changes=context.changes)

    text = _undo(state, "")

    assert yol.read_text(encoding="utf-8") == "kullanici"
    assert state.last_changes is context.changes
    assert "kod.py" in text and "çakış" in text


async def test_kabuk_dosya_geri_alma_sonraki_kullanici_yazmasini_korur(tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools import build_registry

    yol = tmp_path / "notlar.txt"
    yol.write_text("ilk", encoding="utf-8")
    context = ToolContext(root=tmp_path)
    sonuc = await build_registry().execute(
        "run_shell", {"command": "echo ajan > notlar.txt"}, context
    )
    assert sonuc.ok, sonuc.output
    yol.write_text("kullanici", encoding="utf-8")

    assert context.changes.restore() == ()
    assert yol.read_text(encoding="utf-8") == "kullanici"
    assert context.changes.conflicts[0].path == yol


def test_gorsel_varyantlarinin_basarili_yazmalari_geri_alinir(tmp_path):
    from PIL import Image

    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools.image_ops import optimize_image

    kaynak = tmp_path / "kaynak.png"
    Image.new("RGB", (1600, 900), "red").save(kaynak)
    context = ToolContext(root=tmp_path)
    sonuc = optimize_image({"path": "kaynak.png", "out": "sonuc.webp"}, context)
    assert sonuc.ok, sonuc.output
    written = context.changes.paths
    assert len(written) > 1

    assert set(context.changes.restore()) == set(written)
    assert all(not path.exists() for path in written)
    assert kaynak.exists()

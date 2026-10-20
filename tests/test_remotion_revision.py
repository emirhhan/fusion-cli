"""Sahne revizyonu host beklentisini açık CAS işlemiyle yeniler."""

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools.remotion_scaffold import scaffold_remotion


async def _context(root):
    context = ToolContext(root=root)
    scenes = [{"id": f"scene{i}", "kind": "custom", "duration": 150} for i in range(6)]
    assert (
        await scaffold_remotion(
            {"path": "video", "composition_id": "Video", "timeout_s": 10, "scenes": scenes}, context
        )
    ).ok
    return context


def _scenes():
    return [
        {"id": f"new{i}", "kind": "custom", "duration": duration}
        for i, duration in enumerate([90, 150, 120, 120, 120, 150, 150])
    ]


async def test_alti_sahneden_yediye_host_sure_ve_hashi_yeniler(tmp_path):
    from fusion_cli.tools.remotion_revision import revise_remotion_scenes

    context = await _context(tmp_path)
    old = context.remotion_contract.registered
    result = await revise_remotion_scenes({"scenes": _scenes()}, context)
    assert result.ok
    new = context.remotion_contract.registered
    assert len(new.scenes) == 7 and sum(scene.duration for scene in new.scenes) == 900
    assert new.plan.entry == old.plan.entry and new.plan.composition_id == old.plan.composition_id
    assert len(new.plan.samples) == 21
    assert context.remotion_contract.history == (old,)


async def test_degismis_bootstrap_ve_sure_farki_revizyonu_reddeder(tmp_path):
    from fusion_cli.tools.remotion_revision import revise_remotion_scenes

    context = await _context(tmp_path)
    old = context.remotion_contract.registered
    (tmp_path / "video/src/index.tsx").write_text("bozuk")
    assert not (await revise_remotion_scenes({"scenes": _scenes()}, context)).ok
    assert context.remotion_contract.registered == old


async def test_yazma_hatasi_bootstrap_ve_kaydi_geri_alir(tmp_path, monkeypatch):
    from fusion_cli.tools import remotion_revision

    context = await _context(tmp_path)
    old = context.remotion_contract.registered
    entry = tmp_path / "video/src/index.tsx"
    original = entry.read_bytes()
    write = remotion_revision.atomic_write
    calls = []

    def fail_second(path, content):
        calls.append(path)
        if len(calls) == 2:
            raise OSError("metadata yazılamadı")
        write(path, content)

    monkeypatch.setattr(remotion_revision, "atomic_write", fail_second)
    result = await remotion_revision.revise_remotion_scenes({"scenes": _scenes()}, context)
    assert not result.ok and entry.read_bytes() == original
    assert context.remotion_contract.registered == old and context.remotion_contract.history == ()


async def test_stale_cas_callback_cagirmadan_reddedilir(tmp_path):
    from dataclasses import replace

    context = await _context(tmp_path)
    old = context.remotion_contract.registered
    new = replace(old, scenes=tuple(reversed(old.scenes)))
    context.remotion_contract.revise(old, new, lambda: None)
    calls = []
    with pytest.raises(ValueError, match="eskidi"):
        context.remotion_contract.revise(old, new, lambda: calls.append(True))
    assert calls == [] and context.remotion_contract.history == (old,)


async def test_toplam_sure_degismez_iptal_ve_write_scope_korunur(tmp_path):
    from dataclasses import replace
    from threading import Event

    from fusion_cli.tools.remotion_revision import revise_remotion_scenes

    context = await _context(tmp_path)
    old = context.remotion_contract.registered
    scenes = _scenes()
    scenes[0]["duration"] = 1
    assert not (await revise_remotion_scenes({"scenes": scenes}, context)).ok
    scoped = replace(context, write_scope=(tmp_path / "elsewhere",))
    assert not (await revise_remotion_scenes({"scenes": _scenes()}, scoped)).ok
    cancelled = Event()
    cancelled.set()
    assert not (
        await revise_remotion_scenes({"scenes": _scenes()}, replace(context, cancelled=cancelled))
    ).ok
    assert context.remotion_contract.registered == old


async def test_atomic_snapshot_aba_revizyonu_ayirt_eder(tmp_path):
    from dataclasses import replace

    context = await _context(tmp_path)
    state = context.remotion_contract
    first = state.snapshot()
    alternate = replace(first.registered, scenes=tuple(reversed(first.registered.scenes)))
    state.revise(first.registered, alternate, lambda: None)
    middle = state.snapshot()
    state.revise(alternate, first.registered, lambda: None)
    last = state.snapshot()
    assert first.registered == last.registered
    assert (first.revision, middle.revision, last.revision) == (0, 1, 2)
    assert state.history == (first.registered, alternate)


@pytest.mark.parametrize("problem", ["kit", "metadata"])
async def test_ayni_plan_bozuk_kitte_ve_eksik_metadata_ile_basari_degil(tmp_path, problem):
    from fusion_cli.tools.remotion_revision import revise_remotion_scenes

    context = await _context(tmp_path)
    old = context.remotion_contract.registered
    scenes = [
        {"id": scene.scene_id, "kind": scene.kind, "duration": scene.duration}
        for scene in old.scenes
    ]
    if problem == "kit":
        (tmp_path / "video/src/kit/LayoutAudit.tsx").write_text("bozuk")
    else:
        (tmp_path / "video/fusion-contract.json").unlink()
    assert not (await revise_remotion_scenes({"scenes": scenes}, context)).ok
    assert context.remotion_contract.history == ()


def test_revizyon_files_plan_adiminda_cagrilabilir(tmp_path):
    from fusion_cli.core.tools import ToolFamily, tool_family
    from fusion_cli.engines.agent.plan_context import step_deps

    from .test_plan_runner import _FakeDeps, _step

    assert tool_family("revise_remotion_scenes") is ToolFamily.FILES
    child = step_deps(_FakeDeps(ToolContext(root=tmp_path)), _step("revision"), 10, observe=False)
    assert "revise_remotion_scenes" in child.execution.allowed_tool_names

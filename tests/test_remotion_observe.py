"""Taşıma kaynak hashlerini kendisi alır; eksik renderer/statik kayıt başarı sayılmaz."""

from __future__ import annotations

import json

from fusion_cli.tools.remotion_observe import ProcessOutput, RenderRequest, observe_frame


async def test_taze_kare_transport_hashleri_ve_nonce_tasir(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/index.ts").write_text("export const video = 1")
    request = RenderRequest(tmp_path, "src/index.ts", "Fusion", 30, "still.png", ("src",), 10)

    async def runner(command, root, deadline_s):
        payload = json.loads(command[-1])
        assert payload["session"] == "new-session"
        (root / "still.png").write_bytes(b"\x89PNG\r\n\x1a\nreal")
        record = {
            "session": "new-session",
            "composition": "Fusion",
            "frame": 30,
            "activeScenes": ["feature"],
            "activeSceneKinds": ["feature"],
            "featureReady": True,
            "auditSettled": True,
            "findings": [],
            "runtimeExecuted": True,
            "timelineSeen": True,
        }
        return ProcessOutput(0, json.dumps({"record": record, "rendered": True}), "")

    result = await observe_frame(request, runner=runner, new_session=lambda: "new-session")
    assert result.rendered and result.runtime is not None
    assert result.source_before == result.source_after
    assert result.source_before[0].path == "src/index.ts"
    assert result.session_id == "new-session"


async def test_kaynak_degisimi_gercek_transport_manifestinde_gorulur(tmp_path):
    (tmp_path / "index.ts").write_text("old")
    request = RenderRequest(tmp_path, "index.ts", "Fusion", 0, "still.png", ("index.ts",), 10)

    async def runner(command, root, deadline_s):
        (root / "index.ts").write_text("new")
        return ProcessOutput(1, "{}", "")

    result = await observe_frame(request, runner=runner, new_session=lambda: "session")
    assert result.source_before != result.source_after
    assert not result.rendered


async def test_eksik_renderer_kurulum_yapmadan_dogrulanamadi_der(tmp_path):
    (tmp_path / "index.ts").write_text("old")
    request = RenderRequest(tmp_path, "index.ts", "Fusion", 0, "still.png", ("index.ts",), 10)

    async def runner(command, root, deadline_s):
        return ProcessOutput(1, json.dumps({"error": "renderer yok"}), "")

    result = await observe_frame(request, runner=runner, new_session=lambda: "session")
    assert not result.rendered and result.runtime is None
    assert result.error


async def test_sir_symlink_kapsami_okunmaz(tmp_path):
    import pytest

    (tmp_path / ".env").write_text("test placeholder")
    (tmp_path / "linked.ts").symlink_to(tmp_path / ".env")
    request = RenderRequest(tmp_path, "linked.ts", "Fusion", 0, "still.png", ("linked.ts",), 10)
    with pytest.raises(ValueError, match="sır"):
        await observe_frame(request)


async def test_eski_png_yeni_kare_kaniti_olamaz(tmp_path):
    import pytest

    (tmp_path / "index.ts").write_text("old")
    (tmp_path / "still.png").write_bytes(b"\x89PNG\r\n\x1a\nold")
    request = RenderRequest(tmp_path, "index.ts", "Fusion", 0, "still.png", ("index.ts",), 10)
    with pytest.raises(ValueError, match="zaten var"):
        await observe_frame(request)


async def test_node_runner_gercek_parametreleri_renderer_siniri_uzerinden_tasir(tmp_path):
    (tmp_path / "index.ts").write_text("placeholder")
    (tmp_path / "package.json").write_text("{}")
    modules = tmp_path / "node_modules/@remotion"
    for name in ("renderer", "bundler"):
        (modules / name).mkdir(parents=True)
    (modules / "bundler/index.js").write_text("exports.bundle=async({entryPoint})=>entryPoint;")
    (modules / "renderer/index.js").write_text("""
    exports.openBrowser=async()=>({close:async()=>{}});
    exports.selectComposition=async({id,inputProps})=>({id,inputProps});
    exports.renderStill=async args=>{
      require('fs').writeFileSync(args.output,Buffer.from([137,80,78,71,13,10,26,10]));
      args.onBrowserLog({text:'FUSION_RUNTIME_V1:'+JSON.stringify({
      session:args.inputProps.__fusionRuntimeSession,composition:args.composition.id,
      frame:args.frame,activeScenes:['scene'],featureReady:true,auditSettled:true,
      findings:[],runtimeExecuted:true,timelineSeen:true})});};
    """)
    request = RenderRequest(tmp_path, "index.ts", "RealId", 47, "still.png", ("index.ts",), 10)
    result = await observe_frame(request, new_session=lambda: "fresh")
    assert result.rendered and result.runtime is not None
    assert result.runtime.composition == "RealId" and result.runtime.frame == 47
    assert result.runtime.session == "fresh"


def _write_owned_process_fixture(tmp_path):
    child = tmp_path / "child.py"
    child.write_text(
        "import os,signal,time\nfrom pathlib import Path\n"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
        "Path('child.pid').write_text(str(os.getpid()))\ntime.sleep(60)\n"
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import subprocess,sys,time\n"
        "subprocess.Popen([sys.executable,'child.py'])\ntime.sleep(60)\n"
    )
    return parent


async def _assert_owned_child_dead(pid):
    import asyncio
    import contextlib
    import os
    import signal

    import pytest

    try:
        for _ in range(30):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            await asyncio.sleep(0.01)
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        # Yalnız testin kendi PID'si; kullanıcı süreçlerine dokunulmaz.
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


async def test_timeout_kendi_direncli_alt_surecini_yetim_birakmaz(tmp_path):
    import sys

    import pytest

    from fusion_cli.tools.remotion_observe import _run

    parent = _write_owned_process_fixture(tmp_path)
    with pytest.raises(TimeoutError):
        await _run((sys.executable, str(parent)), tmp_path, 0.2)
    await _assert_owned_child_dead(int((tmp_path / "child.pid").read_text()))


async def test_tekrarlanan_iptal_kendi_direncli_alt_surecini_yetim_birakmaz(tmp_path):
    import asyncio
    import sys

    import pytest

    from fusion_cli.tools.remotion_observe import _run

    parent = _write_owned_process_fixture(tmp_path)
    task = asyncio.create_task(_run((sys.executable, str(parent)), tmp_path, 0.2))
    for _ in range(50):
        if (tmp_path / "child.pid").exists():
            break
        await asyncio.sleep(0.01)
    pid = int((tmp_path / "child.pid").read_text())
    task.cancel()
    asyncio.get_running_loop().call_later(0.02, task.cancel)
    with pytest.raises(asyncio.CancelledError):
        await task
    await _assert_owned_child_dead(pid)


async def test_renderer_ayri_gruptaki_direncli_chromium_benzeri_cocugu_temizler(tmp_path):
    (tmp_path / "index.ts").write_text("placeholder")
    (tmp_path / "package.json").write_text("{}")
    modules = tmp_path / "node_modules/@remotion"
    for name in ("renderer", "bundler"):
        (modules / name).mkdir(parents=True)
    (modules / "bundler/index.js").write_text("exports.bundle=async()=>null;")
    (modules / "renderer/index.js").write_text("""
    exports.openBrowser=()=>{
      const source="process.on('SIGTERM',()=>{});"+
        "require('fs').writeFileSync('child.pid',String(process.pid));"+
        "setInterval(()=>{},1000);";
      require('child_process').spawn(process.execPath,['-e',source],{detached:true,stdio:'ignore'});
      return new Promise(()=>{});
    };
    """)
    request = RenderRequest(tmp_path, "index.ts", "Fusion", 0, "still.png", ("index.ts",), 0.3)
    result = await observe_frame(request)
    assert not result.rendered
    await _assert_owned_child_dead(int((tmp_path / "child.pid").read_text()))


def test_runtime_turu_eksik_ise_eski_tasima_kaydi_tur_uydurmaz():
    from fusion_cli.tools.remotion_observe import _record

    payload = {
        "session": "host",
        "composition": "Fusion",
        "frame": 0,
        "activeScenes": ["intro"],
        "featureReady": True,
        "auditSettled": True,
        "findings": [],
        "runtimeExecuted": True,
        "timelineSeen": True,
    }
    legacy = _record(payload)
    assert legacy is not None and legacy.active_scene_kinds == ()
    payload["activeSceneKinds"] = ["custom"]
    actual = _record(payload)
    assert actual is not None and actual.active_scene_kinds == ("custom",)

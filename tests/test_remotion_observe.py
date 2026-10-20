"""Taşıma kaynak hashlerini kendisi alır; eksik renderer/statik kayıt başarı sayılmaz."""

from __future__ import annotations

import json

import pytest

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
    _browser_fixture(tmp_path)
    (modules / "bundler/index.js").write_text("exports.bundle=async({entryPoint})=>entryPoint;")
    (modules / "renderer/index.js").write_text("""
    exports.openBrowser=async()=>({close:async()=>{}});
    exports.selectComposition=async options=>{
      if(options.timeoutInMilliseconds!==10000 || typeof options.onBrowserLog!=='function')
        throw Error('selectComposition seçenekleri eksik');
      return {id:options.id,inputProps:options.inputProps};};
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

    from fusion_cli.tools.remotion_observe import _run

    parent = _write_owned_process_fixture(tmp_path)
    output = await _run((sys.executable, str(parent)), tmp_path, 0.2)
    assert output.timed_out
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
    import asyncio

    from fusion_cli.tools.remotion_observe import _run

    (tmp_path / "index.ts").write_text("placeholder")
    (tmp_path / "package.json").write_text("{}")
    modules = tmp_path / "node_modules/@remotion"
    for name in ("renderer", "bundler"):
        (modules / name).mkdir(parents=True)
    _browser_fixture(tmp_path)
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

    async def runner(command, root, deadline):
        process = asyncio.create_task(_run(command, root, deadline))

        async def wait_started():
            for _ in range(500):
                if (tmp_path / "child.pid").exists():
                    return
                await asyncio.sleep(0.01)
            raise AssertionError("Testin kendi alt süreci başlangıç sinyali vermedi.")

        try:
            await asyncio.wait_for(wait_started(), 5)
        except (TimeoutError, AssertionError, asyncio.CancelledError, OSError):
            process.cancel()
            await asyncio.gather(process, return_exceptions=True)
            raise
        process.cancel()
        return await process

    request = RenderRequest(tmp_path, "index.ts", "Fusion", 0, "still.png", ("index.ts",), 30)
    with pytest.raises(asyncio.CancelledError):
        await observe_frame(request, runner=runner)
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


@pytest.mark.parametrize("mode", ["missing", "mismatch", "installed", "hang"])
async def test_node_tarayici_yok_veya_surumu_yanlissa_indirmez(tmp_path, mode):
    (tmp_path / "index.ts").write_text("placeholder")
    (tmp_path / "package.json").write_text("{}")
    modules = tmp_path / "node_modules/@remotion"
    renderer = modules / "renderer"
    (renderer / "browser").mkdir(parents=True)
    (modules / "bundler").mkdir(parents=True)
    executable = _browser_fixture(tmp_path, mode)
    (modules / "bundler/index.js").write_text("exports.bundle=async()=> 'url';")
    (renderer / "index.js").write_text(
        "exports.openBrowser=async(_,options)=>{"
        "require('fs').writeFileSync('opened',JSON.stringify(options ?? null));"
        "if(!options?.browserExecutable)throw Error('DOWNLOAD MUST NEVER RUN');"
        "return {close:async()=>{}}};"
        "exports.selectComposition=async options=>{"
        + (
            "options.onBrowserLog({text:'JS root-load error'});"
            "setInterval(()=>{},1000);return new Promise(()=>{});"
            if mode == "hang"
            else "return {id:'Fusion'};"
        )
        + "};"
        "exports.renderStill=async()=>{};"
    )
    request = RenderRequest(
        tmp_path, "index.ts", "Fusion", 0, "still.png", ("index.ts",), 0.3 if mode == "hang" else 10
    )
    from fusion_cli.tools.remotion_observe import _run

    async def runner(command, root, deadline):
        process = await _run(command, root, deadline)
        assert "Mevcut renderer/bundler" not in process.stdout, process.stdout
        return process

    result = await observe_frame(request, runner=runner)
    assert not result.rendered
    if mode == "hang":
        assert "select" in result.error and "JS root-load error" in result.error
    if mode in ("installed", "hang"):
        options = json.loads((tmp_path / "opened").read_text())
        assert options["browserExecutable"] == str(executable)
    else:
        assert not (tmp_path / "opened").exists()


def _browser_fixture(tmp_path, mode="installed"):
    renderer = tmp_path / "node_modules/@remotion/renderer"
    (renderer / "browser").mkdir(exist_ok=True)
    executable = tmp_path / "chrome"
    if mode != "missing":
        executable.write_text("installed")
    local = str(mode != "missing").lower()
    revision = json.dumps(str(executable))
    (renderer / "browser/BrowserFetcher.js").write_text(
        "exports.getPlatform=()=> 'linux';exports.getExpectedVersion=()=> '123';"
        f"exports.getRevisionInfo=()=>({{local:{local},executablePath:{revision}}});"
        f"exports.readVersionFile=()=> '{'old' if mode == 'mismatch' else '123'}';"
        "exports.downloadBrowser=()=>{throw Error('DOWNLOAD MUST NEVER RUN')};"
    )
    return executable


@pytest.mark.parametrize(
    "mode", ["banner", "malformed", "multiple", "wrong-session", "wrong-frame"]
)
async def test_framed_transport_banner_ve_gecersiz_cevabi_ayirir(tmp_path, mode):
    (tmp_path / "index.ts").write_text("entry")
    request = RenderRequest(tmp_path, "index.ts", "Fusion", 0, "still.png", ("index.ts",), 10)

    async def runner(command, root, deadline):
        payload = json.loads(command[-1])
        record = {
            "session": payload["session"],
            "rendered": False,
            "record": None,
            "composition": payload["composition"],
            "frame": payload["frame"],
            "stage": "select",
            "error": "Waiting for root component to load",
        }
        if mode == "wrong-session":
            record["session"] = "stale"
        if mode == "wrong-frame":
            record["frame"] = 99
        line = "FUSION_OBSERVE_V1:" + json.dumps(record)
        if mode == "malformed":
            line = "FUSION_OBSERVE_V1:{"
        if mode == "multiple":
            line += "\n" + line
        return ProcessOutput(1, "Remotion help banner\n" + line, "")

    result = await observe_frame(request, runner=runner)
    assert not result.rendered and result.runtime is None
    if mode == "banner":
        assert "select" in result.error and "Waiting for root component" in result.error
    else:
        assert "protokol" in result.error


async def test_timeout_kismi_asama_kanitini_butce_icinde_korur(tmp_path):
    import sys

    from fusion_cli.core.constants import MAX_CHECKPOINT_OUTPUT_CHARS
    from fusion_cli.tools.remotion_observe import _run

    child = tmp_path / "diagnostic.py"
    child.write_text(
        "import time,sys\nprint('banner',flush=True)\n"
        "print('FUSION_PROGRESS_V1: select root-load',file=sys.stderr,flush=True)\n"
        "time.sleep(60)\n"
    )
    output = await _run((sys.executable, str(child)), tmp_path, 0.1)
    assert output.timed_out and output.exit_code != 0
    assert "select root-load" in output.stderr and "banner" in output.stdout
    assert len(output.stderr) <= MAX_CHECKPOINT_OUTPUT_CHARS


@pytest.mark.parametrize("stale", [False, True])
async def test_timeout_nonce_bagli_kismi_taniyi_korur_fakat_basari_saymaz(tmp_path, stale):
    import sys

    from fusion_cli.core.constants import MAX_CHECKPOINT_OUTPUT_CHARS
    from fusion_cli.tools.remotion_observe import _run

    (tmp_path / "index.ts").write_text("entry")
    child = tmp_path / "progress.py"
    session_expression = repr("stale") if stale else "request['session']"
    child.write_text(
        "import json,sys,time\nrequest=json.loads(sys.argv[1])\n"
        "print('x'*20000,file=sys.stderr,flush=True)\n"
        f"request['session']={session_expression}\n"
        "request.update(stage='select',message='Root JS error before hang')\n"
        "print('FUSION_PROGRESS_V1:'+json.dumps(request),file=sys.stderr,flush=True)\n"
        "time.sleep(60)\n"
    )

    async def runner(command, root, deadline):
        return await _run((sys.executable, str(child), command[-1]), root, deadline)

    request = RenderRequest(tmp_path, "index.ts", "Fusion", 0, "still.png", ("index.ts",), 0.1)
    result = await observe_frame(request, runner=runner)
    assert not result.rendered and result.runtime is None
    assert len(result.error) <= MAX_CHECKPOINT_OUTPUT_CHARS
    assert ("Root JS error" in result.error) is (not stale)


async def test_sinirli_kuyruk_onceki_final_cevabi_silip_coklu_protokolu_gizlemez(tmp_path):
    import sys

    from fusion_cli.tools.remotion_observe import _run

    child = tmp_path / "duplicate.py"
    child.write_text(
        "print('FUSION_OBSERVE_V1:{}')\nprint('x'*20000)\nprint('FUSION_OBSERVE_V1:{}')\n"
    )
    output = await _run((sys.executable, str(child)), tmp_path, 10)
    assert output.framed_count == 2
    assert output.stdout.count("FUSION_OBSERVE_V1:") == 1

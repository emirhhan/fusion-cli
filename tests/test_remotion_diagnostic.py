"""Kök/rAF/CDP tanısı başarının yerine geçmeden gerçek sayfa sınırına bağlanır."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from fusion_cli.tools.remotion_observe import RenderRequest, observe_frame

RUNNER = (
    Path(__file__).resolve().parents[1]
    / "src/fusion_cli/config/skills/remotion-video/kit/observe.cjs"
)


async def test_cdp_exception_select_timeout_oncesi_tanida_korunur(tmp_path):
    from .test_remotion_observe import _browser_fixture

    (tmp_path / "index.ts").write_text("entry")
    (tmp_path / "package.json").write_text("{}")
    modules = tmp_path / "node_modules/@remotion"
    (modules / "renderer").mkdir(parents=True)
    (modules / "bundler").mkdir()
    _browser_fixture(tmp_path)
    (modules / "bundler/index.js").write_text("exports.bundle=async()=> 'url';")
    (modules / "renderer/index.js").write_text("""
    const events={};
    const page={_client:()=>({on:(name,fn)=>events[name]=fn}),evaluateOnNewDocument:async()=>{}};
    exports.openBrowser=async()=>({newPage:async()=>page,close:async()=>{}});
    exports.selectComposition=async({puppeteerInstance})=>{
      await puppeteerInstance.newPage({});
      events['Runtime.exceptionThrown']?.({exceptionDetails:{
        exception:{description:'Entry JS failed'}}});
      setInterval(()=>{},1000);return new Promise(()=>{});
    };
    """)
    request = RenderRequest(tmp_path, "index.ts", "Fusion", 0, "still.png", ("index.ts",), 0.3)
    result = await observe_frame(request)
    assert not result.rendered and result.runtime is None
    assert "Entry JS failed" in result.error


@pytest.mark.parametrize("mode", ["registered", "root-error", "no-api", "no-raf"])
def test_kok_ve_raf_tanisi_gozlemi_basari_kaniti_uydurmaz(tmp_path, mode):
    script = tmp_path / "diagnostic.cjs"
    script.write_text(
        "const vm=require('node:vm');const {pageDiagnostics}=require(process.argv[2]);"
        "const events={};const logs=[];const mode=process.argv[3];"
        "const window={addEventListener:(name,fn)=>events[name]=fn};"
        "if(mode!=='no-api')window.remotion_getCompositionNames=()=>{"
        "if(mode==='root-error')throw Error('registerRoot was never called');return ['Fusion']};"
        "vm.runInNewContext('('+pageDiagnostics.toString()+')()',"
        "{window,console:{log:text=>logs.push(text)},requestAnimationFrame:fn=>{if(mode!=='no-raf')fn();}});"
        "events.load();process.stdout.write(JSON.stringify(logs));"
    )
    output = subprocess.check_output(
        ["node", str(script), str(RUNNER), mode], text=True, timeout=10
    )
    records = [json.loads(line.split(":", 1)[1]) for line in json.loads(output)]
    assert records[0]["rafObserved"] is False
    if mode in ("registered", "no-raf"):
        assert records[0]["rootRegistered"] is True
    else:
        assert records[0]["rootRegistered"] is None and records[0]["rootError"]
    assert records[-1]["rafObserved"] is (mode != "no-raf")
    assert all("runtimeExecuted" not in record for record in records)


@pytest.mark.parametrize("mode", ["missing-browser", "missing-page", "throwing-client"])
def test_desteklenmeyen_tani_api_sessiz_kesinlik_uretmez(tmp_path, mode):
    script = tmp_path / "unsupported.cjs"
    script.write_text(
        "const {installPageDiagnostics}=require(process.argv[2]);"
        "const mode=process.argv[3],logs=[];"
        "const page=mode==='throwing-client'?{_client:()=>{throw Error('unsupported')}}:{};"
        "const browser=mode==='missing-browser'?{}:{newPage:async()=>page};"
        "installPageDiagnostics(browser,text=>logs.push(text));"
        "(async()=>{if(browser.newPage){const actual=await browser.newPage();"
        "if(actual!==page)throw Error('Page değiştirilmemeli')};"
        "process.stdout.write(JSON.stringify(logs))})();"
    )
    output = subprocess.check_output(
        ["node", str(script), str(RUNNER), mode], text=True, timeout=10
    )
    logs = json.loads(output)
    assert logs and all("UNVERIFIED" in line for line in logs)

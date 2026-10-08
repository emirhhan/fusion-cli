"""Host tarafından seçilen mevcut tarayıcı taşımasının denetimleri."""

import json
from pathlib import Path

import pytest

from fusion_cli.tools.remotion_observe import ExistingBrowser, RenderRequest, observe_frame


@pytest.mark.parametrize("mode", ["headless-shell", "chrome-for-testing"])
async def test_existing_browser_explicit_path_and_mode_reach_renderer(tmp_path, mode):
    executable = tmp_path / "existing-chrome"
    executable.write_text("installed")
    executable.chmod(0o755)
    _renderer(tmp_path)
    request = RenderRequest(tmp_path, "index.ts", "Fusion", 0, "still.png", ("index.ts",), 10)
    result = await observe_frame(request, browser=ExistingBrowser(executable, mode))
    options = json.loads((tmp_path / "opened").read_text())
    assert options["browserExecutable"] == str(executable)
    assert options["chromeMode"] == mode
    assert not result.rendered and result.runtime is None


@pytest.mark.parametrize("case", ["missing", "directory", "relative", "mode", "not_executable"])
async def test_invalid_host_browser_never_opens_or_falls_back(tmp_path, case):
    executable = tmp_path / "existing-chrome"
    if case == "directory":
        executable.mkdir()
    elif case != "missing":
        executable.write_text("installed")
        executable.chmod(0o644 if case == "not_executable" else 0o755)
    _renderer(tmp_path)
    request = RenderRequest(tmp_path, "index.ts", "Fusion", 0, "still.png", ("index.ts",), 10)
    selected = Path("existing-chrome") if case == "relative" else executable
    result = await observe_frame(
        request,
        browser=ExistingBrowser(selected, "invalid" if case == "mode" else "chrome-for-testing"),
    )
    assert not result.rendered and result.runtime is None
    assert result.error
    assert not (tmp_path / "opened").exists()


def _renderer(root):
    (root / "index.ts").write_text("placeholder")
    (root / "package.json").write_text("{}")
    modules = root / "node_modules/@remotion"
    (modules / "renderer").mkdir(parents=True)
    (modules / "bundler").mkdir()
    (modules / "bundler/index.js").write_text("exports.bundle=async()=> 'url';")
    (modules / "renderer/index.js").write_text(
        "exports.openBrowser=async(_,options)=>{"
        "require('fs').writeFileSync('opened',JSON.stringify(options));"
        "return {close:async()=>{}}};"
        "exports.selectComposition=async()=>({id:'Fusion'});"
        "exports.renderStill=async()=>{};"
    )


async def test_host_browser_does_not_authorize_reused_runtime_session(tmp_path):
    from fusion_cli.tools.remotion_observe import ProcessOutput

    (tmp_path / "index.ts").write_text("placeholder")
    request = RenderRequest(tmp_path, "index.ts", "Fusion", 3, "still.png", ("index.ts",), 10)

    async def runner(command, root, deadline):
        payload = json.loads(command[-1])
        assert payload["session"] == "fresh" and payload["frame"] == 3
        assert payload["timeoutMs"] == 10000 and deadline == 10
        assert payload["browser"]["mode"] == "chrome-for-testing"
        (root / "still.png").write_bytes(b"\x89PNG\r\n\x1a\nreal")
        record = {
            "session": "old",
            "composition": "Fusion",
            "frame": 3,
            "activeScenes": ["intro"],
            "featureReady": True,
            "auditSettled": True,
            "findings": [],
            "runtimeExecuted": True,
            "timelineSeen": True,
        }
        return ProcessOutput(
            0,
            "FUSION_OBSERVE_V1:"
            + json.dumps(
                {
                    "session": "old",
                    "composition": "Fusion",
                    "frame": 3,
                    "record": record,
                    "rendered": True,
                }
            ),
            "",
        )

    result = await observe_frame(
        request,
        browser=ExistingBrowser(tmp_path / "chrome", "chrome-for-testing"),
        runner=runner,
        new_session=lambda: "fresh",
    )
    assert result.runtime is None
    assert result.source_before == result.source_after
    assert result.error

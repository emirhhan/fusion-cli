"""Açık host seçenekleri ve seçilmiş main bağımlılık çağrısı."""

import argparse
import hashlib
import json
import subprocess
import sys

import pytest


def test_browser_options_require_pair_and_selected_engine(tmp_path):
    from evals.live_drive import _komut

    args = argparse.Namespace(
        engine_source="",
        engine_manifest="",
        engine_proof="",
        log=False,
        remotion_browser_executable=str(tmp_path / "chrome"),
        remotion_browser_mode="",
    )
    with pytest.raises(ValueError):
        _komut(args)


def test_launcher_fresh_source_host_factory_reaches_selected_main(tmp_path):
    root = tmp_path / "engine"
    package = root / "src/fusion_cli"
    (package / "cli").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "cli/__init__.py").write_text("")
    marker = tmp_path / "main.json"
    (package / "cli/app.py").write_text(
        "import json\nfrom pathlib import Path\ndef main(*,host_dependencies=None):\n"
        f" Path({str(marker)!r}).write_text(json.dumps(host_dependencies))\n"
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "requested_revision": "a" * 40,
                "sources": [
                    {
                        "path": str(p.relative_to(root)),
                        "digest": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                    for p in sorted(package.rglob("*.py"))
                ],
            }
        )
    )
    code = (
        "from pathlib import Path;from evals.engine_launcher import launch;"
        f"launch(Path({str(root)!r}),Path({str(manifest)!r}),"
        f"Path({str(tmp_path / 'proof.json')!r}),"
        "host_dependencies_factory=lambda proof,entry:"
        "{'pid':proof.pid,'selected':entry.__file__})"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    observed = json.loads(marker.read_text())
    assert observed["selected"] == str(package / "cli/app.py")
    assert observed["pid"] == json.loads((tmp_path / "proof.json").read_text())["pid"]


@pytest.mark.parametrize("mode", ["", "chrome-for-testing"])
def test_selected_browser_missing_engine_never_uses_legacy_launcher(tmp_path, mode):
    from evals.live_drive import _komut

    executable = tmp_path / "chrome"
    executable.write_text("existing")
    executable.chmod(0o755)
    args = argparse.Namespace(
        engine_source="",
        engine_manifest="",
        engine_proof="",
        log=False,
        remotion_browser_executable=str(executable),
        remotion_browser_mode=mode,
    )
    with pytest.raises(ValueError):
        _komut(args)


def test_real_selected_factories_carry_transport_into_main_session(tmp_path):
    root = tmp_path / "engine"
    package = root / "src/fusion_cli"
    for name in ("cli", "tools"):
        (package / name).mkdir(parents=True, exist_ok=True)
        (package / name / "__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    marker = tmp_path / "observed.json"
    executable = tmp_path / "chrome"
    executable.write_text("existing")
    executable.chmod(0o755)
    (package / "cli/app_host.py").write_text(
        "class AppHostDependencies:\n"
        " def __init__(self,*,remotion_transport): self.remotion_transport=remotion_transport\n"
    )
    (package / "tools/remotion_observe.py").write_text(
        "class ExistingBrowser:\n"
        " def __init__(self,executable,mode): self.executable=executable;self.mode=mode\n"
        "async def observe_frame(request,*,browser):\n"
        " return {'request':request,'executable':str(browser.executable),'mode':browser.mode}\n"
    )
    (package / "cli/app.py").write_text(
        "import asyncio,json\nfrom pathlib import Path\n"
        "class AppSession:\n"
        " def __init__(self,*,transport): self.transport=transport\n"
        "def main(*,host_dependencies=None):\n"
        " session=AppSession(transport=host_dependencies.remotion_transport)\n"
        f" Path({str(marker)!r}).write_text(json.dumps(asyncio.run(session.transport('frame'))))\n"
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "requested_revision": "a" * 40,
                "sources": [
                    {
                        "path": str(p.relative_to(root)),
                        "digest": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                    for p in sorted(package.rglob("*.py"))
                ],
            }
        )
    )
    code = (
        "from pathlib import Path;from evals.engine_launcher import launch;"
        "from evals.driver_engine import _browser_host;"
        "from evals.driver_browser import HostBrowserSelection;"
        f"choice=HostBrowserSelection(Path({str(executable)!r}),'chrome-for-testing');"
        f"launch(Path({str(root)!r}),Path({str(manifest)!r}),"
        f"Path({str(tmp_path / 'proof.json')!r}),"
        "host_dependencies_factory=lambda proof,entry:_browser_host(choice,proof,entry))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(marker.read_text()) == {
        "request": "frame",
        "executable": str(executable),
        "mode": "chrome-for-testing",
    }

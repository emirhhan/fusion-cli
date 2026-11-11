import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from evals.fixtures.production_acceptance import check_assets
from typer.testing import CliRunner

from fusion_cli.cli.app import app
from fusion_cli.core.events import ToolExecuted
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.loop import run_agent
from fusion_cli.tools import godot_sprite
from fusion_cli.tools.builtin import build_registry
from fusion_cli.tools.write_targets import write_targets

from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
from .test_agent_loop import _deps, _kur

pytestmark = pytest.mark.skipif(
    os.open not in os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"),
    reason="Godot sprite writes require anchored file descriptors",
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    marker = tmp_path / "project.godot"
    marker.write_bytes(b'[application]\nconfig/name="Fusion Eval"\n')
    return tmp_path


def test_add_godot_sprite_cli_runs_the_existing_asset_check(project):
    runner = CliRunner()
    command = ["godot-sprite", "--project", str(project)]
    result = runner.invoke(app, command)
    assert result.exit_code == 0, result.output
    check_assets(project)
    before = (project / "assets/ASSETS.json").read_bytes()
    entry = json.loads(before)["assets"][0]
    assert entry["license"] == "CC0-1.0"
    assert "godotengine/godot-demo-projects/" in entry["source_url"]
    assert runner.invoke(app, command).exit_code == 0
    assert (project / "assets/ASSETS.json").read_bytes() == before


def test_add_godot_sprite_does_not_overwrite_existing_files(project):
    assets = project / "assets"
    assets.mkdir()
    (assets / "player.png").write_bytes(b"existing")
    (assets / "ASSETS.json").write_bytes(b'{"assets": []}\n')
    result = CliRunner().invoke(app, ["godot-sprite", "--project", str(project)])
    assert result.exit_code == 1
    assert (assets / "player.png").read_bytes() == b"existing"
    assert (assets / "ASSETS.json").read_bytes() == b'{"assets": []}\n'


def test_add_godot_sprite_preserves_existing_manifest_entries(project):
    assets = project / "assets"
    assets.mkdir()
    entry = {"path": "other.png", "source_url": "https://example.org/other.png", "license": "MIT"}
    (assets / "ASSETS.json").write_text(json.dumps({"assets": [entry], "version": 1}))
    result = CliRunner().invoke(app, ["godot-sprite", "--project", str(project)])
    assert result.exit_code == 0, result.output
    check_assets(project)
    manifest = json.loads((assets / "ASSETS.json").read_bytes())
    assert manifest["assets"][0] == entry
    assert manifest["version"] == 1


def test_registered_sprite_tool_declares_and_respects_both_write_targets(project):
    tool = build_registry().get("add_godot_sprite")
    args = {"path": "assets/player.png"}
    assert tool is not None and tool.mutating
    assert write_targets(tool.name, args) == ("assets/player.png", "assets/ASSETS.json")
    context = ToolContext(root=project, restrict_to_root=True)
    assert tool.run(args, context).ok
    assert context.touched == {project / "assets/player.png", project / "assets/ASSETS.json"}
    check_assets(project)


async def test_godot_actor_writes_both_assets_in_one_tool_call(project, monkeypatch):
    sink = RecordingSink()
    deps = _deps(
        project,
        sink,
        runtime={"interaction_prompts": False, "self_review": False, "teacherless": True},
    )
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[tool_call("add_godot_sprite", path="assets/player.png")],
                ),
                model_result("Oyuncu PNG'si ve CC0 lisans kaydı eklendi."),
            ]
        ),
    )
    monkeypatch.setattr(
        "fusion_cli.engines.agent.loop.intro_paragraph",
        lambda *args, **kwargs: _empty_intro(),
    )
    result = await run_agent(
        "Mevcut Godot projesine assets/player.png için gerçek bir PNG ve "
        "assets/ASSETS.json içinde source_url ile license kaydı ekle. "
        "project.godot dosyasını koru.",
        deps,
    )
    assert result.mutating_tool_calls_made == 1 and result.failed_tool_calls == 0
    assert "add_godot_sprite" in {s["function"]["name"] for s in provider.seen_requests[0]}
    assert [e.name for e in sink.events if isinstance(e, ToolExecuted)] == ["add_godot_sprite"]
    check_assets(project)


async def _empty_intro():
    return ""


def test_add_godot_sprite_leaves_no_png_after_manifest_write_error(project, monkeypatch):
    original = godot_sprite._publish

    def fail_write(directory, name, content, *, previous):
        if name == "ASSETS.json":
            raise OSError("no space left")
        return original(directory, name, content, previous=previous)

    monkeypatch.setattr(godot_sprite, "_publish", fail_write)
    context = ToolContext(root=project)
    result = godot_sprite.add_godot_sprite({"path": "assets/player.png"}, context)
    assert not result.ok
    assert not (project / "assets/player.png").exists()
    assert not (project / "assets/ASSETS.json").exists()


def test_add_godot_sprite_refuses_symlinked_destination_directory(project, tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (project / "assets").symlink_to(outside, target_is_directory=True)
    result = CliRunner().invoke(app, ["godot-sprite", "--project", str(project)])
    assert result.exit_code == 1
    assert list(outside.iterdir()) == []


def test_add_godot_sprite_refuses_project_symlink_to_protected_directory(project):
    protected = project / ".git"
    protected.mkdir()
    (project / "assets").symlink_to(protected, target_is_directory=True)
    result = godot_sprite.add_godot_sprite({"path": "assets/player.png"}, ToolContext(root=project))
    assert not result.ok
    assert list(protected.iterdir()) == []


@pytest.mark.parametrize("mode", ["replace", "rewrite", "publish_then_replace"])
def test_manifest_publication_preserves_an_editors_replacement(project, monkeypatch, mode):
    original = godot_sprite._publish

    def replace_png(directory, name, content, *, previous):
        if name == "ASSETS.json":
            png = project / "assets/player.png"
            if mode == "rewrite":
                png.write_bytes(b"editor output")
            else:
                replacement = project / "assets/editor.png"
                replacement.write_bytes(b"editor output")
                replacement.replace(png)
            if mode == "publish_then_replace":
                return original(directory, name, content, previous=previous)
            raise OSError("manifest write failed")
        return original(directory, name, content, previous=previous)

    monkeypatch.setattr(godot_sprite, "_publish", replace_png)
    context = ToolContext(root=project)
    result = godot_sprite.add_godot_sprite({"path": "assets/player.png"}, context)
    assert not result.ok
    assert not (project / "assets/ASSETS.json").exists()
    context.changes.restore()
    assert (project / "assets/player.png").read_bytes() == b"editor output"


@pytest.mark.parametrize("directory", ["$literal", "-literal"])
def test_shell_like_paths_are_rejected_before_any_project_write(project, directory):
    result = godot_sprite.add_godot_sprite(
        {"path": f"{directory}/.git/player.png"}, ToolContext(root=project)
    )
    assert not result.ok
    assert not (project / directory).exists()


def test_concurrent_sprite_additions_keep_both_manifest_entries(project, monkeypatch):
    original = godot_sprite._publish
    first_at_write = Event()
    second_at_write = Event()
    first_finished = Event()

    def interleave(directory, name, content, *, previous):
        if name != "ASSETS.json":
            return original(directory, name, content, previous=previous)
        entries = json.loads(content)["assets"]
        if [entry["path"] for entry in entries] == ["first.png"]:
            first_at_write.set()
            second_at_write.wait(0.5)
            published = original(directory, name, content, previous=previous)
            first_finished.set()
            return published
        else:
            second_at_write.set()
            assert first_finished.wait(5)
            return original(directory, name, content, previous=previous)

    def add(name):
        context = ToolContext(root=project)
        return godot_sprite.add_godot_sprite({"path": f"assets/{name}"}, context)

    monkeypatch.setattr(godot_sprite, "_publish", interleave)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(add, "first.png")
        assert first_at_write.wait(5)
        second = pool.submit(add, "second.png")
        assert first.result(timeout=5).ok and second.result(timeout=5).ok

    entries = json.loads((project / "assets/ASSETS.json").read_bytes())["assets"]
    assert {entry["path"] for entry in entries} == {"first.png", "second.png"}

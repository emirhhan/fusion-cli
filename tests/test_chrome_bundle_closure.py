"""Check the extension actually assembled from resource maps and installer output."""

import json
import shutil
from pathlib import Path

import pytest
from desktop_build.chrome_bundle import inspect_extension

from fusion_cli.appserver import chrome_install

ROOT = Path(__file__).resolve().parents[1]
TAURI = ROOT / "app/src-tauri"


@pytest.mark.parametrize("config", ["tauri.bundle.conf.json", "tauri.windows.bundle.conf.json"])
def test_tauri_assembled_extension_import_closure(tmp_path, config):
    resources = json.loads((TAURI / config).read_text())["bundle"]["resources"]
    for source, target in resources.items():
        if target.startswith("chrome-extension/"):
            destination = tmp_path / target
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(TAURI / source, destination)
    inspected = inspect_extension(tmp_path / "chrome-extension")
    assert inspected["modules"] > 0


def test_python_installer_stages_complete_source_import_closure(tmp_path, monkeypatch):
    monkeypatch.setattr(chrome_install, "base_config_dir", lambda: tmp_path)
    staged = chrome_install.stage_extension()
    assert inspect_extension(staged)["modules"] > 0


def _extension(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "background": {"service_worker": "background.js"},
                "side_panel": {"default_path": "panel.html"},
            }
        )
    )
    (tmp_path / "background.js").write_text('import {\n  value,\n} from "./nested/entry.js";')
    (tmp_path / "panel.html").write_text('<script type="module" src="panel.js"></script>')
    (tmp_path / "panel.js").write_text('export {\n  value,\n} from "./nested/entry.js";')
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "entry.js").write_text('import "../leaf.js"; export const value=1;')
    return tmp_path


def test_missing_arbitrary_transitive_import_fails(tmp_path):
    directory = _extension(tmp_path)
    with pytest.raises(FileNotFoundError, match=r"leaf\.js"):
        inspect_extension(directory)
    (directory / "leaf.js").write_text("export const unrelated=1;")
    assert inspect_extension(directory)["modules"] == 4


def test_missing_manifest_or_html_entrypoint_fails(tmp_path):
    directory = _extension(tmp_path)
    (directory / "leaf.js").write_text("")
    (directory / "panel.js").unlink()
    with pytest.raises(FileNotFoundError, match=r"panel\.js"):
        inspect_extension(directory)
    (directory / "panel.js").write_text("")
    (directory / "background.js").unlink()
    with pytest.raises(FileNotFoundError, match=r"background\.js"):
        inspect_extension(directory)


@pytest.mark.parametrize("kind", [".js", ".html", "transitive"])
def test_outside_symlinks_are_rejected_before_any_content_read(tmp_path, monkeypatch, kind):
    root = tmp_path / "extension"
    root.mkdir()
    directory = _extension(root)
    (directory / "leaf.js").write_text("")
    outside = tmp_path / "outside.js"
    outside.write_text("throw new Error('outside content must never be read');")
    if kind == "transitive":
        (directory / "nested/entry.js").write_text('import "../linked-leaf"; export const value=1;')
        link = directory / "linked-leaf"
    else:
        link = directory / f"unreferenced{kind}"
    link.symlink_to(outside)
    original_read = Path.read_text

    def checked_read(path, *args, **kwargs):
        assert path.resolve() != outside, "outside symlink content was read before containment"
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", checked_read)
    with pytest.raises(ValueError, match="escapes its directory"):
        inspect_extension(directory)


def test_inside_symlink_remains_valid_without_evaluating_its_source(tmp_path):
    directory = _extension(tmp_path)
    target = directory / "nested/owned.js"
    target.write_text("throw new Error('parser must never evaluate extension code');")
    (directory / "leaf.js").symlink_to(target)
    assert inspect_extension(directory)["modules"] == 5


def test_root_relative_module_is_resolved_in_extension_and_missing_file_rejected(tmp_path):
    directory = _extension(tmp_path)
    (directory / "leaf.js").write_text("")
    (directory / "nested/entry.js").write_text('import "/root.js"; export const value=1;')
    root_module = directory / "root.js"
    root_module.write_text("export const rootValue=1;")
    assert inspect_extension(directory)["modules"] == 5
    root_module.unlink()
    with pytest.raises(FileNotFoundError, match=r"root\.js"):
        inspect_extension(directory)


@pytest.mark.parametrize(
    "specifier",
    [
        "missing-package",
        "https://example.test/module.js",
        "//example.test/module.js",
        "data:text/javascript,export default 1",
        "node:fs",
    ],
)
def test_unsupported_module_specifiers_are_rejected_explicitly(tmp_path, specifier):
    directory = _extension(tmp_path)
    (directory / "leaf.js").write_text("")
    (directory / "nested/entry.js").write_text(
        f"import {json.dumps(specifier)}; export const value=1;"
    )
    with pytest.raises(ValueError, match="Unsupported extension module specifier"):
        inspect_extension(directory)

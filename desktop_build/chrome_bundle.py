"""Inspect actual Chrome extension resources without evaluating their JavaScript.

The desktop build already requires Node. Its native module parser checks every
shipped JS module's static imports/re-exports, including multiline declarations.
The source checkout cannot satisfy an import missing from the inspected directory.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

_PARSE_MODULES = """
const fs = require('node:fs');
const vm = require('node:vm');
const sources = JSON.parse(fs.readFileSync(0, 'utf8'));
const imports = {};
for (const [name, source] of Object.entries(sources)) {
  imports[name] = new vm.SourceTextModule(source, {identifier: name}).dependencySpecifiers;
}
process.stdout.write(JSON.stringify(imports));
"""


class _Scripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        source = dict(attrs).get("src")
        if tag == "script" and source:
            self.sources.append(source)


def _resource(root: Path, parent: Path, reference: str) -> Path:
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc:
        raise ValueError(f"Extension resource is not local: {reference}")
    path = (parent / unquote(parsed.path)).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Extension resource escapes its directory: {reference}")
    if not path.is_file():
        raise FileNotFoundError(f"Missing extension resource: {path.relative_to(root)}")
    return path


def inspect_extension(directory: Path) -> dict[str, int]:
    """Validate entrypoints and static module import closure in a built/staged directory."""
    root = directory.resolve()
    manifest = json.loads(_resource(root, root, "manifest.json").read_text(encoding="utf-8"))
    _resource(root, root, manifest["background"]["service_worker"])
    _resource(root, root, manifest["side_panel"]["default_path"])
    for html in root.rglob("*.html"):
        parser = _Scripts()
        checked_html = _resource(root, root, html.relative_to(root).as_posix())
        parser.feed(checked_html.read_text(encoding="utf-8"))
        for reference in parser.sources:
            _resource(root, html.parent, reference)
    sources = {
        path.relative_to(root).as_posix(): _resource(
            root, root, path.relative_to(root).as_posix()
        ).read_text(encoding="utf-8")
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".js", ".mjs"}
    }
    result = subprocess.run(
        ["node", "--no-warnings", "--experimental-vm-modules", "-e", _PARSE_MODULES],
        input=json.dumps(sources),
        text=True,
        capture_output=True,
        check=True,
        timeout=15,
    )
    imports = json.loads(result.stdout)
    for name, references in imports.items():
        for reference in references:
            if reference.startswith(("./", "../")):
                _resource(root, (root / name).parent, reference)
            elif reference.startswith("/") and not reference.startswith("//"):
                _resource(root, root, reference[1:])
            else:
                raise ValueError(f"Unsupported extension module specifier: {reference}")
    return {"modules": len(sources), "imports": sum(len(refs) for refs in imports.values())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory", type=Path, help="Actual built or staged chrome-extension directory"
    )
    print(json.dumps(inspect_extension(parser.parse_args().directory)))

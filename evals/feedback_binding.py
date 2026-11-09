"""Fixed release-inspector route, shared by host preparation and frozen entrypoint."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
from pathlib import Path
from typing import Any

from fusion_cli.core.shell_sandbox import temporary_roots

INSPECTOR_COMMAND = "fusion-inspect-production"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_wrapper(binding: Path, binding_sha256: str, python: Path, repo: Path) -> bytes:
    code = (
        "import sys;"
        f"sys.path[:0]=[{str(repo)!r},{str(repo / 'src')!r}];"
        "from scripts.release_feedback import run_bound;"
        f"raise SystemExit(run_bound({str(binding)!r},{binding_sha256!r}))"
    )
    command = shlex.join([str(python), "-I", "-c", code])
    return (
        "#!/bin/sh\nset -eu\n"
        'if [ "$#" -ne 0 ]; then echo "fixed inspector accepts no arguments" >&2; exit 64; fi\n'
        f"exec {command}\n"
    ).encode()


def assert_protected_path(path: Path, root: Path) -> None:
    if not path.is_absolute() or path.resolve() != path or path.is_relative_to(root):
        raise ValueError("Inspector control path is not protected from the candidate root.")
    if any(path.is_relative_to(temporary) for temporary in temporary_roots()):
        raise ValueError("Inspector control path is inside writable temporary roots.")
    if not path.is_file() or path.stat().st_mode & 0o222:
        raise ValueError("Inspector control file must be readonly.")


def _trusted_location(path: Path, root: Path) -> None:
    if (
        not path.is_absolute()
        or path.resolve() != path
        or path.is_relative_to(root)
        or any(path.is_relative_to(temporary) for temporary in temporary_roots())
    ):
        raise ValueError("Trusted inspector source/profile is inside candidate-writable paths.")


def assert_source_locations(repo: Path, profile: Path, root: Path) -> None:
    _trusted_location(repo, root)
    _trusted_location(profile, root)
    # Candidate writes must not overlap any imported code/control namespace,
    # including new modules the candidate might otherwise plant in that tree.
    for name in ("src", "evals", "scripts", "desktop_build", "tests", "release", ".github"):
        scope = repo / name
        _trusted_location(scope, root)
        if root.is_relative_to(scope):
            raise ValueError("Candidate root overlaps trusted inspector source/control namespaces.")


def assert_interpreter_location(python: Path, root: Path) -> None:
    for path in (python, python.resolve()):
        if (
            not path.is_absolute()
            or path.is_relative_to(root)
            or any(path.is_relative_to(temporary) for temporary in temporary_roots())
        ):
            raise ValueError("Trusted inspector interpreter is inside candidate-writable paths.")


def runtime_route(root: Path, source_digest: str) -> None:
    """Validate a host-supplied route; actor PATH/CWD and environment are not authority."""
    wrapper = Path(os.environ["FUSION_RELEASE_INSPECTOR"])
    binding = Path(os.environ["FUSION_RELEASE_INSPECTOR_BINDING"])
    assert_protected_path(wrapper, root)
    assert_protected_path(binding, root)
    if wrapper.name != INSPECTOR_COMMAND or wrapper.parent != binding.parent:
        raise ValueError("Fixed inspector route differs from the protected host prefix.")
    entries = os.environ.get("PATH", "").split(os.pathsep)
    if (
        not entries
        or entries[0] != str(wrapper.parent)
        or any(
            not part or not Path(part).is_absolute() or Path(part).resolve().is_relative_to(root)
            for part in entries
        )
    ):
        raise ValueError("Inspector PATH prefix is not absolute/protected.")
    if digest(wrapper) != os.environ["FUSION_RELEASE_INSPECTOR_SHA256"]:
        raise ValueError("Inspector wrapper bytes changed.")
    if digest(binding) != os.environ["FUSION_RELEASE_INSPECTOR_BINDING_SHA256"]:
        raise ValueError("Inspector binding bytes changed.")
    raw: dict[str, Any] = json.loads(binding.read_text())
    assert_interpreter_location(Path(raw["python"]), root)
    assert_source_locations(Path(raw["repo"]), Path(raw["profile"]), root)
    if raw["root"] != str(root) or raw["source_digest"] != source_digest:
        raise ValueError("Inspector task root/source binding differs from the frozen run.")
    if digest(Path(os.environ["FUSION_CONFIG"])) != raw["profile_sha256"]:
        raise ValueError("Inspector profile binding changed.")
    expected = render_wrapper(binding, digest(binding), Path(raw["python"]), Path(raw["repo"]))
    if wrapper.read_bytes() != expected:
        raise ValueError("Inspector wrapper does not implement the fixed route.")

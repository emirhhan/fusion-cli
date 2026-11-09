"""Frozen runtime identity adapter for the existing live stdio driver.

Build provenance is trusted only through the CI build job/artifact channel. It is
not a signature or proof that an arbitrary developer archive came from git.
"""

from __future__ import annotations

import inspect
import json
import os
import sys
from collections.abc import Awaitable
from dataclasses import asdict
from functools import wraps
from pathlib import Path
from typing import Any, cast

from evals.driver_config import SessionAPI
from evals.engine_proof import ImportedEngineProof
from fusion_cli.config.models import Config

PROVENANCE = "release-build.json"
PROTECTED_TARGETS = frozenset({"aarch64-apple-darwin", "x86_64-apple-darwin"})


def frozen_proof(root: Path, provenance: dict[str, Any], pid: int) -> ImportedEngineProof:
    return ImportedEngineProof(
        pid,
        str(root / "fusion_cli/__init__.py"),
        str(root / "fusion_cli/cli/app.py"),
        str(root),
        provenance["source_digest"],
        provenance["commit"],
    )


ACCEPTANCE_TOOLS = frozenset(
    {
        "read_file",
        "write_file",
        "edit_file",
        "multi_edit",
        "list_dir",
        "glob",
        "grep_search",
        "run_shell",
    }
)


def require_protected_profile(config: Config, *, platform: str = sys.platform) -> None:
    """Validate an explicit caller profile; never rewrite the user's config.

    No process/MCP/browser launcher is exposed outside the mandatory shell
    sandbox. Windows has no protected actor adapter and must remain unmeasured.
    """
    if platform not in {"darwin", "linux"}:
        raise ValueError("K29: protected frozen actor unavailable on this platform.")
    runtime, sandbox = config.runtime, config.sandbox
    if not (
        runtime.restrict_to_root
        and runtime.block_writes_outside_root
        and runtime.block_reads_outside_root
        and runtime.shell_sandbox == "write_root"
        and runtime.teacherless
        and not runtime.lessons
        and not runtime.verification_commands
        and not runtime.post_edit_commands
        and not runtime.web_verification
        and not runtime.browser_verification
        and not runtime.visual_verification
        and not runtime.playbooks
        and not runtime.auto_web_fallback
        and not runtime.teacher_lesson_sync
        and not runtime.teacher_codex_fallback
        and not runtime.escalate_on_gate_failure
        and sandbox.fail_if_unavailable
        and not sandbox.allow_unsandboxed
        and not sandbox.excluded_commands
        and not sandbox.allow_write
        and not sandbox.filesystem_disabled
        and not sandbox.enable_weaker_nested_sandbox
        and not sandbox.allow_nested_user_namespaces
        and sandbox.hide_secret_env
        and not config.mcp_servers
        and not config.hosted_connectors
        and not config.web_sessions
    ):
        raise ValueError("Explicit protected release acceptance profile required.")


def install_profile_guard(session: SessionAPI) -> None:
    original = session.run_agent_task
    signature = inspect.signature(original)

    @wraps(original)
    async def guarded(*args: object, **kwargs: object) -> object:
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        require_protected_profile(cast(Config, bound.arguments["config"]))
        if bound.arguments.get("extra_roots"):
            raise ValueError("Protected acceptance cannot expose extra writable roots.")
        kwargs["allowed_tools"] = set(ACCEPTANCE_TOOLS)
        kwargs["bootstrap_mcp"] = False
        return await cast(Awaitable[object], original(*args, **kwargs))

    session.run_agent_task = guarded


def install() -> None:
    """Explicit acceptance mode in the actual frozen entrypoint, never normal startup."""
    from evals.driver_engine import _install_config_observer

    root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    provenance = json.loads((root / PROVENANCE).read_text())
    proof = frozen_proof(root, provenance, os.getpid())
    print(json.dumps({"tip": "motor_kaniti", "veri": asdict(proof)}), flush=True)
    _install_config_observer(proof)
    import fusion_cli.cli.session as session

    install_profile_guard(cast(SessionAPI, session))


def validate(raw: object, executable: Path, pid: int) -> ImportedEngineProof:
    if not isinstance(raw, dict):
        raise ValueError("Frozen motor kanıtı eksik.")
    # PyInstaller onedir contents live under _internal; executable is outside it.
    root = executable.parent / "_internal"
    provenance = json.loads((root / PROVENANCE).read_text())
    expected = asdict(frozen_proof(root, provenance, pid))
    if raw != expected:
        raise ValueError("Frozen motor kanıtı çalıştırılan paketle uyuşmuyor.")
    return frozen_proof(root, provenance, pid)

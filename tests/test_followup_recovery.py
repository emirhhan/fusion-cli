"""Followups describe unresolved work, retaining distinct target failures."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from fusion_cli.core.evidence import EvidenceEnvironment, ToolUse
from fusion_cli.core.followups import suggest_followups
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.turn_evidence import evidence_from_turn


def _failed(root: Path, *uses: ToolUse) -> tuple[str, ...]:
    return evidence_from_turn(SimpleNamespace(tool_uses=uses), ToolContext(root=root)).failed_tools


def test_identical_successful_retry_removes_fix_suggestion(tmp_path: Path) -> None:
    uses = (
        ToolUse("read_file", ok=False, arguments={"path": "a.py"}),
        ToolUse("read_file", arguments={"path": "a.py"}),
    )
    assert _failed(tmp_path, *uses) == ()


def test_different_targets_do_not_recover_each_other(tmp_path: Path) -> None:
    assert _failed(
        tmp_path,
        ToolUse("read_file", ok=False, arguments={"path": "a.py"}),
        ToolUse("read_file", arguments={"path": "b.py"}),
    ) == ("read_file",)


def test_success_before_later_failure_does_not_recover_it(tmp_path: Path) -> None:
    assert _failed(
        tmp_path,
        ToolUse("read_file", arguments={"path": "a"}),
        ToolUse("read_file", ok=False, arguments={"path": "a"}),
    ) == ("read_file",)


def test_same_arguments_in_different_environment_stay_unresolved(tmp_path: Path) -> None:
    def env(cwd: str) -> EvidenceEnvironment:
        return EvidenceEnvironment("", cwd, "", "", "")

    assert _failed(
        tmp_path,
        ToolUse("run_shell", ok=False, arguments={"command": "pytest"}, environment=env("/one")),
        ToolUse("run_shell", arguments={"command": "pytest"}, environment=env("/two")),
    ) == ("run_shell",)


def _preview_uses(
    root: Path,
    *,
    failed_path: str = "a.html",
    preview_path: str = "/a.html",
    successful_url: str | None = None,
    preview_root: Path | None = None,
    origin: str = "http://127.0.0.1:8770",
) -> tuple[ToolUse, ...]:
    url = origin + preview_path
    return (
        ToolUse("browser_open", ok=False, arguments={"url": (root / failed_path).as_uri()}),
        ToolUse(
            "start_preview",
            arguments={"path": str(preview_root or root)},
            output=(
                f"Önizleme çalışıyor: {url} (static). Kullanıcı bu adresi açabilir."
                "\nÖlçüm: HTTP 200"
            ),
        ),
        ToolUse("browser_open", arguments={"url": successful_url or url}),
    )


def test_owned_static_preview_recovers_file_url_failure(tmp_path: Path) -> None:
    uses = _preview_uses(tmp_path)
    evidence = evidence_from_turn(SimpleNamespace(tool_uses=uses), ToolContext(root=tmp_path))
    assert evidence.failed_tools == ()
    assert not any(item.reason == "failed_tools" for item in suggest_followups(evidence))
    assert uses[0].ok is False  # Historical outcome is preserved.


@pytest.mark.parametrize(
    "kwargs",
    [
        {"preview_path": "/b.html"},
        {"preview_path": "/nested/../a.html"},
        {"preview_path": "/%2e%2e/a.html"},
        {"preview_path": "/a.html?other=1"},
        {"successful_url": "http://127.0.0.1:8771/a.html"},
        {"origin": "https://foreign.test"},
        {"origin": "http://user:pass@127.0.0.1:8770"},
    ],
)
def test_unproven_preview_recovery_keeps_failure(tmp_path: Path, kwargs: dict) -> None:
    assert _failed(tmp_path, *_preview_uses(tmp_path, **kwargs)) == ("browser_open",)


def test_foreign_preview_root_does_not_recover_file(tmp_path: Path) -> None:
    assert _failed(tmp_path, *_preview_uses(tmp_path, preview_root=tmp_path / "other")) == (
        "browser_open",
    )


def test_encoded_same_filename_can_recover(tmp_path: Path) -> None:
    assert (
        _failed(
            tmp_path, *_preview_uses(tmp_path, failed_path="a b.html", preview_path="/a%20b.html")
        )
        == ()
    )


def test_legacy_missing_arguments_do_not_recover_by_name(tmp_path: Path) -> None:
    uses = (
        SimpleNamespace(name="browser_open", ok=False),
        SimpleNamespace(name="browser_open", ok=True),
    )
    assert evidence_from_turn(
        SimpleNamespace(tool_uses=uses), ToolContext(root=tmp_path)
    ).failed_tools == ("browser_open",)


def test_implicit_page_action_does_not_recover_by_identical_selector(tmp_path: Path) -> None:
    assert _failed(
        tmp_path,
        ToolUse("browser_click", ok=False, arguments={"selector": "button"}),
        ToolUse("browser_click", arguments={"selector": "button"}),
    ) == ("browser_click",)


@pytest.mark.parametrize("failed_index", [1, 2])
def test_preview_or_browser_failure_cannot_recover_file(tmp_path: Path, failed_index: int) -> None:
    uses = list(_preview_uses(tmp_path))
    uses[failed_index] = replace(uses[failed_index], ok=False)
    assert "browser_open" in _failed(tmp_path, *uses)


def test_preview_existing_before_failed_file_is_not_recovery(tmp_path: Path) -> None:
    failed, preview, opened = _preview_uses(tmp_path)
    assert _failed(tmp_path, preview, failed, opened) == ("browser_open",)


def test_same_file_preview_does_not_hide_other_browser_target_failure(tmp_path: Path) -> None:
    uses = _preview_uses(tmp_path)
    remote = ToolUse("browser_open", ok=False, arguments={"url": "https://example.com"})
    assert _failed(tmp_path, remote, *uses) == ("browser_open",)


def test_static_preview_environment_mismatch_keeps_file_failure(tmp_path: Path) -> None:
    failed, preview, opened = _preview_uses(tmp_path)
    opened = replace(opened, environment=EvidenceEnvironment("", "/other", "", "", ""))
    assert _failed(tmp_path, failed, preview, opened) == ("browser_open",)


@pytest.mark.parametrize("preview_env", [None, EvidenceEnvironment("", "/other", "", "", "")])
def test_preview_proof_must_share_the_browser_environment(
    tmp_path: Path, preview_env: EvidenceEnvironment | None
) -> None:
    failed, preview, opened = _preview_uses(tmp_path)
    browser_env = EvidenceEnvironment("", str(tmp_path), "owned-runtime", "", "")
    failed = replace(failed, environment=browser_env)
    opened = replace(opened, environment=browser_env)
    preview = replace(preview, environment=preview_env)
    assert _failed(tmp_path, failed, preview, opened) == ("browser_open",)


def test_preview_environment_alone_cannot_bind_unknown_browser_environment(tmp_path: Path) -> None:
    failed, preview, opened = _preview_uses(tmp_path)
    preview = replace(preview, environment=EvidenceEnvironment("", str(tmp_path), "", "", ""))
    assert _failed(tmp_path, failed, preview, opened) == ("browser_open",)


def test_explicit_shared_preview_environment_recovers_same_file(tmp_path: Path) -> None:
    environment = EvidenceEnvironment("", str(tmp_path), "owned-runtime", "", "")
    uses = tuple(replace(use, environment=environment) for use in _preview_uses(tmp_path))
    assert _failed(tmp_path, *uses) == ()

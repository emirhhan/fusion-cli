"""`.claude/launch.json` `autoVerify` önizleme doğrulamasını açar/kapatır (#440)."""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.browser_verify import BrowserVerifier
from fusion_cli.engines.agent.verification import CompositeVerifier, build_verifier
from fusion_cli.tools.preview_launch import auto_verify_enabled

from .fakes import make_config


def _write(root: Path, body: str) -> None:
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "launch.json").write_text(body, encoding="utf-8")


def _has_browser(root: Path) -> bool:
    config = make_config(runtime={"web_verification": False, "browser_verification": True})
    verifier = build_verifier(config, root=root, tool_context=ToolContext(root=root))
    parts = verifier._verifiers if isinstance(verifier, CompositeVerifier) else (verifier,)
    return any(isinstance(part, BrowserVerifier) for part in parts)


def test_dosya_yoksa_ve_belirtilmemisse_acik(tmp_path):
    assert auto_verify_enabled(tmp_path) is True
    _write(tmp_path, '{"version": "0.0.1", "configurations": []}')
    assert auto_verify_enabled(tmp_path) is True
    assert _has_browser(tmp_path)


def test_auto_verify_false_onizleme_dogrulamasini_kapatir(tmp_path):
    _write(
        tmp_path,
        '{\n  // yorum\n  "version": "0.0.1", "autoVerify": false, "configurations": []\n}',
    )
    assert auto_verify_enabled(tmp_path) is False
    assert not _has_browser(tmp_path)


def test_bozuk_dosya_dogrulamayi_kapatmaz(tmp_path):
    _write(tmp_path, "{bozuk")
    assert auto_verify_enabled(tmp_path) is True

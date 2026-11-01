"""Claude `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` (#368).

Claude Code (env-vars): `1` iken Anthropic ve bulut sağlayıcı kimlik bilgileri Bash aracının
alt süreç ortamından çıkarılır. Fusion değişkeni okumuyordu.
"""

from __future__ import annotations

from types import SimpleNamespace

from fusion_cli.config import keys
from fusion_cli.core.env_scrub import SCRUBBED_NAMES, scrub_enabled, scrubbed_env
from fusion_cli.tools import shell


def test_kapaliyken_ortam_degismez():
    taban = {"ANTHROPIC_API_KEY": "s", "PATH": "/bin"}
    assert scrubbed_env(taban, {}) == taban
    assert not scrub_enabled({"CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "0"})


def test_acikken_kimlik_bilgileri_cikarilir():
    taban = {"ANTHROPIC_API_KEY": "s", "AWS_SECRET_ACCESS_KEY": "a", "PATH": "/bin"}
    sonuc = scrubbed_env(taban, {"CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "1"})
    assert sonuc == {"PATH": "/bin"}


def test_fusion_saglayici_anahtarlari_listede():
    for ad in (keys.OPENROUTER_ENV, keys.NIM_ENV, keys.OPENAI_ENV, keys.GEMINI_ENV):
        assert ad in SCRUBBED_NAMES
    assert keys.ANTHROPIC_ENV in SCRUBBED_NAMES


def test_run_shell_ortami_temizlenir(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "gizli")
    monkeypatch.setenv("FUSION_TEST_SIRADAN", "kalir")
    ortam = shell._shell_env(SimpleNamespace(hidden_env=()))
    assert "OPENROUTER_API_KEY" not in ortam and ortam["FUSION_TEST_SIRADAN"] == "kalir"

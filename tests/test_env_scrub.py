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


async def test_kanca_sureci_kimlik_bilgilerini_gormez(monkeypatch, tmp_path):
    """Claude: scrub kancaları da kapsar (#368)."""
    from fusion_cli.core.hooks.events import HookCommand, HookEvent
    from fusion_cli.engines.hooks.runner import run_hook

    command = HookCommand(HookEvent.STOP, "", 'echo "anahtar=${ANTHROPIC_API_KEY:-yok}"', 5)
    env = {"PATH": "/usr/bin:/bin", "ANTHROPIC_API_KEY": "sk-gizli"}

    monkeypatch.delenv("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", raising=False)
    acik = await run_hook(command, {}, cwd=tmp_path, environment=env)
    monkeypatch.setenv("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", "1")
    kapali = await run_hook(command, {}, cwd=tmp_path, environment=env)

    assert "sk-gizli" in acik.stdout
    assert "anahtar=yok" in kapali.stdout


def test_mcp_stdio_varsayilan_ortami_kimlik_bilgisi_tasimaz(monkeypatch):
    """MCP SDK stdio sunucusuna yalnız güvenli ortam adlarını aktarır; scrub listesi oraya
    hiç girmez (sunucuya `env` ile açıkça verilen değer kullanıcının seçimidir)."""
    from mcp.client.stdio import get_default_environment

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-gizli")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-gizli")
    assert not SCRUBBED_NAMES & set(get_default_environment())

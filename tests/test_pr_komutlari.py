"""PR/CI komut paritesi (P-057): salt-okunur `gh` aracı, PR makroları, `--from-pr`,
`fusion gh-action kur`.

Ölçüldü (31 Ekim): depoda `gh` geçmiyordu; git aracı salt-okur, PR oluşturma/yorum okuma
aracı ve makrosu yoktu.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from types import SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli.gh_action_command import (
    WORKFLOW_RELATIVE_PATH,
    install_workflow,
    workflow_template,
)
from fusion_cli.cli.repl import macros
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.core.errors import FusionError
from fusion_cli.core.tools import ToolContext, ToolEffect, ToolFamily, tool_family
from fusion_cli.tools import auto_policy, github_cli
from fusion_cli.tools.builtin import build_registry as build_tools

runner = CliRunner()


# --- salt-okunur gh ------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "komut",
    [
        "pr view 12 --comments",
        "pr diff 12",
        "pr checks 12",
        "run view 7 --log-failed",
        "api repos/a/b/pulls/1/comments",
        "api repos/a/b/pulls -X GET --paginate --jq .[].title",
        "api --method=GET repos/a/b -H 'Accept: application/vnd.github+json' -q .name",
    ],
)
def test_salt_okunur_gh_komutlari_kabul_edilir(komut):
    assert github_cli.gh_reads_only(shlex.split(komut))


@pytest.mark.parametrize(
    "komut",
    [
        "pr create --title x",
        "pr comment 12 --body hi",
        "pr merge 12",
        "api repos/a/b/issues -f title=x",
        "api -X DELETE repos/a/b",
        "api --method POST repos/a/b",
        # Ölçüldü (31 Ekim): eşittir biçimli ve bitişik kısa bayraklar tam eşleşme
        # kontrolünden kaçıyordu; gh alan verilince varsayılan POST yapar.
        "api repos/o/r/issues/1/comments --field=body=hi",
        "api repos/o/r/issues/1/comments --raw-field=a=b",
        "api repos/o/r/issues --input=f.json",
        "api repos/o/r/issues -fbody=hi",
        "api repos/o/r/issues -Fbody=@f",
        "api repos/o/r --bilinmeyen-bayrak",
        # Tarayıcı açan ve token gösteren bayraklar da salt-okur değildir.
        "pr view 12 --web",
        "pr view 12 -w",
        "pr view 12 -cw",
        "repo view --web",
        "auth status",
        "auth status --show-token",
        "pr",
        "",
        "repo delete a/b",
    ],
)
def test_yazan_gh_komutlari_reddedilir(komut):
    assert not github_cli.gh_reads_only(shlex.split(komut))


@pytest.mark.parametrize(
    "komut",
    [
        "gh api -X POST repos/o/r/issues -f title=x",
        "gh api repos/o/r/issues/1/comments --field=body=hi",
        "gh workflow run ci.yml",
        "gh run cancel 12",
        "gh secret set TOKEN",
        "gh release create v1",
        "gh pr create --title x",
    ],
)
def test_run_shell_yazan_gh_cagrisi_otomatik_kipte_sorulur(komut, tmp_path):
    """Ölçüldü (31 Ekim): `gh api -X POST`, `gh workflow run` onaysız geçiyordu."""
    assert "gh" in (auto_policy.auto_risk(komut, tmp_path) or "")


def test_run_shell_okuyan_gh_cagrisi_otomatik_kipte_sorulmaz(tmp_path):
    assert auto_policy.auto_risk("gh pr view 12 --comments", tmp_path) is None
    assert auto_policy.auto_risk("gh api repos/o/r/pulls --paginate", tmp_path) is None


def test_gh_araci_yazan_komutu_calistirmadan_reddeder(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("çalıştırılmamalı"))

    sonuc = github_cli.gh({"args": "pr create --title x"}, ToolContext(root=tmp_path))

    assert not sonuc.ok and "run_shell" in sonuc.output


def test_gh_kurulu_degilse_kurulum_ipucu(tmp_path, monkeypatch):
    monkeypatch.setattr(github_cli.shutil, "which", lambda name: None)

    sonuc = github_cli.gh({"args": "pr view 1"}, ToolContext(root=tmp_path))

    assert not sonuc.ok and "cli.github.com" in sonuc.output


def test_gh_araci_komutu_proje_kokunde_etkilesimsiz_calistirir(tmp_path, monkeypatch):
    yakalanan = {}

    def _sahte_run(cmd, **kwargs):
        yakalanan["cmd"] = cmd
        yakalanan["kwargs"] = kwargs
        return SimpleNamespace(stdout="PR #1 açık", stderr="", returncode=0)

    monkeypatch.setattr(github_cli.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(subprocess, "run", _sahte_run)

    sonuc = github_cli.gh({"args": "pr view 1 --comments"}, ToolContext(root=tmp_path))

    assert sonuc.ok and sonuc.output == "PR #1 açık"
    assert yakalanan["cmd"] == ["/usr/bin/gh", "pr", "view", "1", "--comments"]
    assert yakalanan["kwargs"]["cwd"] == tmp_path
    assert yakalanan["kwargs"]["env"]["GH_PROMPT_DISABLED"] == "1"


def test_gh_araci_kayit_defterinde_uzak_okuma_etkisiyle():
    registry = build_tools()
    tool = registry.get("gh")

    assert tool is not None and tool.mutating is False
    assert tool.effect is ToolEffect.REMOTE_READ
    assert tool_family("gh") is ToolFamily.VCS


# --- --from-pr ------------------------------------------------------------------------- #


def test_pr_baglami_baslik_dal_ve_aciklamayi_tasir(tmp_path, monkeypatch):
    veri = {
        "number": 42,
        "title": "Önbellek düzeltmesi",
        "body": "Eski cevap dönüyordu.",
        "url": "https://github.com/a/b/pull/42",
        "headRefName": "fix/cache",
        "baseRefName": "main",
        "state": "OPEN",
    }
    monkeypatch.setattr(github_cli.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout=json.dumps(veri), stderr="", returncode=0),
    )

    metin = github_cli.pr_context(42, root=tmp_path)

    assert "PR #42" in metin and "Önbellek düzeltmesi" in metin
    assert "fix/cache → main" in metin and "Eski cevap" in metin


def test_from_pr_gorevin_basina_pr_ozetini_ekler(monkeypatch):
    monkeypatch.setattr(
        app_module, "pr_context", lambda n, root: f"# Bağlam: PR #{n}", raising=False
    )
    monkeypatch.setattr(
        "fusion_cli.tools.github_cli.pr_context", lambda n, root: f"# Bağlam: PR #{n}"
    )
    yakalanan = {}

    async def _sahte(task, config, **kwargs):
        yakalanan["task"] = task
        return SimpleNamespace(
            final_text="ok", ok=True, budget_stopped=False, stop_reason=None, model_calls_made=1
        )

    monkeypatch.setattr(app_module, "run_agent_task", _sahte)
    result = runner.invoke(
        app_module.app, ["agent", "yorumları uygula", "--from-pr", "7", "--no-memory", "-q"]
    )

    assert result.exit_code == 0, result.output
    assert (
        yakalanan["task"].startswith("# Bağlam: PR #7") and "yorumları uygula" in yakalanan["task"]
    )


def test_from_pr_gh_yoksa_acik_hata(monkeypatch):
    def _patla(n, root):
        raise RuntimeError("GitHub CLI (gh) kurulu değil.")

    monkeypatch.setattr("fusion_cli.tools.github_cli.pr_context", _patla)
    result = runner.invoke(
        app_module.app, ["agent", "gorev", "--from-pr", "7", "--no-memory", "-q"]
    )

    assert result.exit_code != 0 and "gh" in result.output


# --- makrolar ---------------------------------------------------------------------------- #


def test_pr_makrolari_kayitli_ve_gh_kullanir(tmp_path):
    registry = build_registry(tmp_path)
    for ad in ("pr", "autofix-pr"):
        assert registry.get(ad) is not None, ad
    # Claude Code v2.1.91'de `/pr-comments` kaldırıldı (#226): PR yorumları doğrudan sorulur.
    assert registry.get("pr-comments") is None

    assert "gh pr create" in macros.get("pr").build("")
    assert "gh pr checks 3" in macros.get("autofix-pr").build("3")


# --- gh-action kur ----------------------------------------------------------------------- #


def test_gh_action_kur_sablonu_yazar_ve_var_olani_ezmez(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app_module.app, ["gh-action", "kur"])

    assert result.exit_code == 0, result.output
    yazilan = (tmp_path / WORKFLOW_RELATIVE_PATH).read_text(encoding="utf-8")
    assert "@fusion" in yazilan and "fusion agent -" in yazilan and "--max-budget-usd" in yazilan
    assert "FUSION_PROVIDER_KEY" in yazilan

    with pytest.raises(FusionError, match="force"):
        install_workflow(tmp_path)
    assert install_workflow(tmp_path, force=True).is_file()


def test_gh_action_sablonu_yorum_yazanin_yetkisini_denetler():
    """Ölçüldü (31 Ekim): tek koşul `contains(body, '@fusion')` idi; açık depoda herhangi bir
    kullanıcı sırlı ve yazma yetkili koşuyu tetikleyebiliyordu."""
    kosul = yaml.safe_load(workflow_template())["jobs"]["fusion"]["if"]

    assert "author_association" in kosul
    for yetki in ("OWNER", "MEMBER", "COLLABORATOR"):
        assert yetki in kosul
    assert "@fusion" in kosul


def test_gh_action_bilinmeyen_eylem_hata(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app_module.app, ["gh-action", "sil"])

    assert result.exit_code != 0

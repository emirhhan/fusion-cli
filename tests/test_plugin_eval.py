"""`fusion plugin eval` vaka biçimi, puanlama ve ablasyon (Claude Code `plugin eval`, #380)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli import plugin_eval_command as eval_cmd
from fusion_cli.cli.plugin_commands import app
from fusion_cli.core.plugins import PluginError
from fusion_cli.tools.plugin_eval import RunTrace, load_cases, parse_score


def _plugin(tmp_path: Path) -> Path:
    root = tmp_path / "rapor"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "rapor"}), "utf-8")
    (root / "skills" / "ozet").mkdir(parents=True)
    (root / "skills" / "ozet" / "SKILL.md").write_text(
        "---\nname: ozet\ndescription: Ö\n---\nÖ\n", "utf-8"
    )
    case = root / "evals" / "ozet"
    (case / "graders").mkdir(parents=True)
    (case / "prompt.md").write_text(
        "---\nmax_turns: 4\nruns: 2\ntags: [hizli]\nallowed_tools: [Read, Skill]\n---\n\n"
        "Raporu özetle.\n",
        "utf-8",
    )
    (case / "graders" / "kelime.md").write_text("---\ntype: regex\n---\nÖZET\n", "utf-8")
    (case / "graders" / "beceri.md").write_text("---\ntype: tool_used\ntool: Skill\n---\n", "utf-8")
    (case / "graders" / "kalite.md").write_text(
        "---\ntype: llm\nweight: 2\n---\nKısa ve doğru.\n", "utf-8"
    )
    return root


def test_vakalar_prompt_md_ve_graders_md_den_okunur(tmp_path):
    (case,) = load_cases(_plugin(tmp_path) / "evals")

    assert (case.name, case.runs, case.max_turns, case.tags) == ("ozet", 2, 4, ("hizli",))
    assert [g.type for g in case.graders] == ["tool_used", "llm", "regex"]
    assert case.graders[1].weight == 2.0 and case.graders[1].fields["criteria"] == "Kısa ve doğru."
    assert load_cases(tmp_path / "rapor" / "evals", tags=["yavas"]) == ()


def test_bos_init_sablonu_hata(tmp_path):
    root = _plugin(tmp_path)
    (root / "evals" / "ozet" / "prompt.md").write_text(
        "---\nmax_turns: 10\n---\n\nTODO: describe what the agent should do\n", "utf-8"
    )
    with pytest.raises(PluginError, match="blank `init` template"):
        load_cases(root / "evals")


def _runner(spec):
    used = (("read_skill", {"name": "rapor:ozet"}),) if spec.arm == "with" else ()
    text = "ÖZET: hazır" if spec.arm == "with" else "bilmiyorum"
    return RunTrace(text, used, spec.workdir)


def test_ablasyon_eklentili_ve_eklentisiz_kol_puanlanir(tmp_path):
    root = _plugin(tmp_path)
    cases = load_cases(root / "evals")
    target = eval_cmd.Target(root, "rapor", installed=False)

    result = eval_cmd.run_suite(cases, target, runner=_runner, judge=lambda _p: 1.0)

    (row,) = result["cases"]
    assert row["with"]["score"] == 1.0
    # eklentisiz: regex 0, llm 1 (ağırlık 2) → 2/3; tool_used Skill gösterge, puana girmez
    assert row["without"]["score"] == pytest.approx(2 / 3)
    assert row["delta"] == pytest.approx(1 / 3)
    assert len(row["with"]["runs"]) == 2
    graders = {g["name"]: g for g in row["with"]["runs"][0]["graders"]}
    assert graders["beceri"]["scored"] is False


def test_cli_eval_guven_ister_esik_ve_sonuc_dosyasi(tmp_path, monkeypatch):
    root = _plugin(tmp_path)
    monkeypatch.setattr(eval_cmd, "run_agent", _runner)
    monkeypatch.setattr(eval_cmd, "judge_subprocess", lambda _p: 1.0)
    runner = CliRunner()

    refused = runner.invoke(app, ["eval", str(root)])
    assert refused.exit_code == 1 and "--trust-plugin" in refused.output

    out = runner.invoke(app, ["eval", str(root), "--trust-plugin", "--json"])
    assert out.exit_code == 0, out.output
    payload = json.loads(out.output)
    assert payload["ablation"] == "with-without" and payload["plugin"] == "rapor"
    assert list((root / "evals" / "results").glob("*/aggregate-result.json"))
    low = runner.invoke(app, ["eval", str(root), "--ablation", "none", "--threshold", "1.0"])
    assert low.exit_code == 0
    published = runner.invoke(app, ["eval", str(root), "--publish-report"])
    assert published.exit_code == 1 and "claude.ai" in published.output


def test_iz_olay_satirlarindan_cikarilir_ve_puan_ayristirilir(tmp_path):
    lines = "\n".join(
        [
            json.dumps({"event": "ToolExecuted", "name": "read_file", "args": {"path": "a"}}),
            json.dumps({"event": "TurnAnswered", "text": "bitti"}),
        ]
    )
    trace = eval_cmd.parse_trace(lines, tmp_path)

    assert trace.last_message == "bitti" and trace.tools == (("read_file", {"path": "a"}),)
    assert parse_score("Gerekçe…\nSCORE: 0.5") == 0.5 and parse_score("PASS") == 1.0


def test_eval_dislama_ortam_degiskeni_kurulu_eklentiyi_yuklemez(tmp_path, monkeypatch):
    from fusion_cli.config import plugin_store
    from fusion_cli.tools import plugin_install

    plugin_install.install_plugin(str(_plugin(tmp_path)), approve=lambda _p: True)
    monkeypatch.setenv(eval_cmd.EXCLUDE_ENV, "rapor")

    assert [i.record.name for i in plugin_store.active_plugins()] == []

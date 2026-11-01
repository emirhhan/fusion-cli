"""`fusion plugin eval` seçenekleri: -j, --max-cost-usd, --allow-tools, --model, --scaffold,
--report, --json [yol] ve `eval init` (Claude Code 2.1.287 `claude plugin eval`, #380)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli import plugin_eval_command as eval_cmd
from fusion_cli.cli import plugin_eval_init
from fusion_cli.cli.plugin_commands import app
from fusion_cli.config.plugin_eval_env import MODEL_ENV, with_eval_model
from fusion_cli.core.plugins import PluginError
from fusion_cli.tools import plugin_eval_run as run
from fusion_cli.tools.plugin_eval import RunTrace, load_cases


def _plugin(tmp_path: Path, *, runs: int = 2, extra: str = "") -> Path:
    root = tmp_path / "rapor"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "rapor"}), "utf-8")
    skill = root / "skills" / "yaz"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: yaz\ndescription: Y\nallowed-tools: Write, Bash(npm test:*)\n---\nY\n", "utf-8"
    )
    for name in ("a", "b", "c"):
        case = root / "evals" / name
        (case / "graders").mkdir(parents=True)
        (case / "prompt.md").write_text(
            f"---\nruns: {runs}\n{extra}---\n\n{name} görevini yap.\n", "utf-8"
        )
        (case / "graders" / "g.md").write_text("---\ntype: regex\n---\nTAMAM\n", "utf-8")
    return root


def _trace(spec: run.RunSpec, cost: float = 0.0) -> RunTrace:
    return RunTrace("TAMAM", (), spec.workdir, "", cost)


def test_eszamanli_kosular_vaka_sirasini_korur(tmp_path):
    root = _plugin(tmp_path, runs=1)
    cases = load_cases(root / "evals")
    active = []
    peak = []
    lock = threading.Lock()

    def runner(spec):
        with lock:
            active.append(1)
            peak.append(len(active))
        time.sleep(0.05 if spec.case.name == "a" else 0.0)
        with lock:
            active.pop()
        return _trace(spec)

    result = run.run_suite(
        cases, None, runner=runner, judge=lambda _p: 1.0, options=run.EvalOptions(concurrency=3)
    )

    assert [row["name"] for row in result["cases"]] == ["a", "b", "c"]
    assert max(peak) > 1


def test_maliyet_tavani_kalan_kosulari_baslatmaz_ve_cikis_2(tmp_path, monkeypatch):
    root = _plugin(tmp_path, runs=2)
    calls = []

    def runner(spec):
        calls.append(spec.case.name)
        return _trace(spec, cost=1.0)

    cases = load_cases(root / "evals")
    result = run.run_suite(
        cases, None, runner=runner, judge=lambda _p: 1.0, options=run.EvalOptions(max_cost_usd=1.5)
    )
    assert len(calls) == 2 and result["aborted"] is True and result["costUsd"] == 2.0
    assert result["cases"][2]["with"]["runs"] == []

    monkeypatch.setattr(eval_cmd, "run_agent", runner)
    out = CliRunner().invoke(
        app, ["eval", str(root), "--trust-plugin", "--ablation", "none", "--max-cost-usd", "1"]
    )
    assert out.exit_code == 2, out.output
    assert "--max-cost-usd" in out.output


def test_kapili_araclar_izinsiz_kapali_operator_ve_beceri_izni_acar(tmp_path):
    root = _plugin(tmp_path)
    (case, *_) = load_cases(root / "evals")
    target = run.Target(root, "rapor", installed=False)
    grants = run.skill_grants(root)
    assert grants == ("Bash", "Write")

    plain = run.RunSpec(case, "without", target, tmp_path, run.EvalOptions(plugin_grants=grants))
    assert run.denied_tools(plain) == run.GATED
    with_arm = run.RunSpec(case, "with", target, tmp_path, run.EvalOptions(plugin_grants=grants))
    assert run.denied_tools(with_arm) == ("Edit", "NotebookEdit", "WebFetch")
    operator = run.RunSpec(
        case, "without", target, tmp_path, run.EvalOptions(allow_tools=("Edit",))
    )
    command = run.child_command(operator)
    assert command[command.index("--disallowed-tools") + 1] == "Bash,Write,NotebookEdit,WebFetch"


def test_model_ortami_alt_surece_ve_yapilandirmaya_gecer(tmp_path, monkeypatch):
    from fusion_cli.config.loader import load_config

    (case, *_) = load_cases(_plugin(tmp_path, extra="model: vaka-modeli\n") / "evals")
    spec = run.RunSpec(case, "with", None, tmp_path, run.EvalOptions(model="genel"))
    assert run.child_env(spec)[MODEL_ENV] == "genel"
    assert run.child_env(run.RunSpec(case, "with", None, tmp_path))[MODEL_ENV] == "vaka-modeli"

    config = load_config()
    monkeypatch.setenv(MODEL_ENV, "deneme/model-x")
    assert with_eval_model(config).agent.model == "deneme/model-x"
    first = config.candidates[0]
    monkeypatch.setenv(MODEL_ENV, first.name)
    assert with_eval_model(config).agent == first


def test_scaffold_yalniz_bayrakla_calisir(tmp_path, monkeypatch):
    root = _plugin(tmp_path, runs=1, extra="scaffold_script: kur.sh\n")
    for name in ("a", "b", "c"):
        (root / "evals" / name / "kur.sh").write_text("echo hazir > hazir.txt\n", "utf-8")
    seen = []

    def runner(spec):
        seen.append((spec.workdir / "hazir.txt").is_file())
        return _trace(spec)

    monkeypatch.setattr(eval_cmd, "run_agent", runner)
    cli = CliRunner()
    skipped = cli.invoke(app, ["eval", str(root), "--trust-plugin", "--ablation", "none"])
    assert skipped.exit_code == 0, skipped.output
    assert "is not run without --scaffold" in skipped.output and seen == [False] * 3
    seen.clear()
    ran = cli.invoke(app, ["eval", str(root), "--trust-plugin", "--ablation", "none", "--scaffold"])
    assert ran.exit_code == 0 and seen == [True] * 3
    assert "Only use it on case files you" in ran.output
    both = cli.invoke(app, ["eval", str(root), "--scaffold", "--no-scaffold"])
    assert both.exit_code == 1


def test_rapor_html_ve_json_yolu_yazilir(tmp_path, monkeypatch):
    root = _plugin(tmp_path, runs=1)
    (root / "evals" / "a" / "prompt.md").write_text("---\nruns: 1\n---\n<b>kaçış</b>\n", "utf-8")
    monkeypatch.setattr(eval_cmd, "run_agent", _trace)
    out_dir = tmp_path / "sonuc"
    report = tmp_path / "rapor.html"
    target_json = tmp_path / "tam.json"
    result = CliRunner().invoke(
        app,
        ["eval", "--json", str(target_json), str(root), "--trust-plugin", "--ablation", "none",
         "--output-dir", str(out_dir), "--report", str(report)],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert json.loads(target_json.read_text("utf-8"))["plugin"] == "rapor"
    html = report.read_text("utf-8")
    assert "&lt;b&gt;kaçış&lt;/b&gt;" in html and "<b>kaçış</b>" not in html
    assert (out_dir / "aggregate-result.json").is_file()
    assert not (out_dir / "report.html").exists()


def test_es_zamanlilik_siniri(tmp_path):
    root = _plugin(tmp_path)
    out = CliRunner().invoke(app, ["eval", str(root), "-j", "9", "--trust-plugin"])
    assert out.exit_code == 1 and "1 to 8" in out.output


def test_eval_init_bare_claude_sablonu(tmp_path, monkeypatch):
    root = _plugin(tmp_path)
    monkeypatch.chdir(root)
    cli = CliRunner()

    made = cli.invoke(app, ["eval", "init", "--bare", "yeni-vaka"])
    assert made.exit_code == 0, made.output
    assert (
        "Created evals/yeni-vaka/prompt.md and evals/yeni-vaka/graders/criteria.md" in made.output
    )
    prompt = (root / "evals" / "yeni-vaka" / "prompt.md").read_text("utf-8")
    assert prompt == plugin_eval_init.PROMPT_TEMPLATE
    assert "allowed_tools: [Read, Glob, Grep, Skill]" in prompt
    criteria = (root / "evals" / "yeni-vaka" / "graders" / "criteria.md").read_text("utf-8")
    assert criteria.startswith("---\ntype: llm\nweight: 1\n---")
    with pytest.raises(PluginError, match="blank `init` template"):
        load_cases(root / "evals")
    assert cli.invoke(app, ["eval", "init", "--bare", "yeni-vaka"]).exit_code == 1
    bad = cli.invoke(app, ["eval", "init", "--bare", "Kötü Ad"])
    assert bad.exit_code == 1 and "is invalid" in bad.output
    nameless = cli.invoke(app, ["eval", "init", "--bare"])
    assert nameless.exit_code == 1 and "case name is required" in nameless.output


def test_eval_init_eklenti_disinda_ve_oturum_icinde(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = CliRunner()
    outside = cli.invoke(app, ["eval", "init", "--bare", "x"])
    assert outside.exit_code == 1 and "is not a plugin or skill folder" in outside.output
    here = cli.invoke(app, ["eval", "init", "--bare", "x", "--eval-dir", "vakalar"])
    assert here.exit_code == 0 and (tmp_path / "vakalar" / "x" / "prompt.md").is_file()

    monkeypatch.chdir(_plugin(tmp_path))
    monkeypatch.setenv("FUSION_SESSION_ID", "s1")
    text = cli.invoke(app, ["eval", "init", "ozet"])
    assert text.exit_code == 0
    assert "You are the interviewer" in text.output and '"ozet"' in text.output


def test_dosya_degerlendiricisi_izinsizse_uyari(tmp_path):
    root = _plugin(tmp_path, runs=1)
    (root / "evals" / "a" / "graders" / "dosya.md").write_text(
        "---\ntype: file_exists\npath: rapor.md\n---\n", "utf-8"
    )
    cases = load_cases(root / "evals")
    (warning,) = run.tool_warnings(cases, run.EvalOptions())
    assert warning.startswith("⚠ case a cannot pass with the granted tools")
    assert run.tool_warnings(cases, run.EvalOptions(allow_tools=("Write",))) == ()
    result = run.run_suite(
        cases, run.Target(root, "rapor", False), runner=_trace, judge=lambda _p: 1.0
    )
    assert result["suite"] == {"plugins": [{"name": "rapor", "root": str(root)}]}

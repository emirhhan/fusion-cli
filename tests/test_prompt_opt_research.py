"""F31: gerçek öneri hattında kör küme, bütçe ve sıra korumaları."""

from __future__ import annotations

from pathlib import Path

import pytest
from evals.execution import ModelCallIdentity
from evals.metrics import RunReport, TaskResult
from evals.profiles import RunMetadata
from prompt_opt.optimizer import search
from prompt_opt.selection import Candidate, select_winner
from prompt_opt.variants import PromptVariant
from typer.testing import CliRunner

from fusion_cli.cli import prompt_opt_commands
from fusion_cli.cli.app import app
from fusion_cli.core.events import ToolExecuted, ToolOutcome


def _report(*, passed=False, cost=None, failed_mutation=False, calls=1):
    events = (
        (
            ToolExecuted(
                name="write_file", args={}, outcome=ToolOutcome.FAILED, output="hata", mutating=True
            ),
        )
        if failed_mutation
        else ()
    )
    return RunReport(
        (TaskResult("a", passed, passed, 0, calls, 1.0, trace_events=events),),
        metadata=RunMetadata(
            calls=(ModelCallIdentity("m1", "agent", "model", "model", cost_usd=cost),)
        ),
    )


class _Generator:
    def __init__(self, texts=("aday",)):
        self.texts = texts
        self.calls = 0

    async def generate(self, base_text, count):
        self.calls += 1
        return self.texts


class _Evaluator:
    def __init__(self):
        self.calls = []

    async def evaluate(self, prompt_text):
        self.calls.append(prompt_text)
        return _report(passed=prompt_text != "temel", cost=1.0)


@pytest.mark.parametrize("count", [0, -1, 5])
async def test_dogrudan_arama_gecersiz_adedi_hic_cagri_yapmadan_reddeder(count):
    generator, evaluator = _Generator(), _Evaluator()
    with pytest.raises(ValueError, match=r"1.*4"):
        await search(
            "system", "temel", generator=generator, evaluator=evaluator, variant_count=count
        )
    assert generator.calls == 0
    assert evaluator.calls == []


async def test_fazla_donen_generator_dort_aday_sinirini_asamaz():
    evaluator = _Evaluator()
    with pytest.raises(ValueError, match="aday"):
        await search(
            "system",
            "temel",
            generator=_Generator(tuple(str(i) for i in range(5))),
            evaluator=evaluator,
            variant_count=4,
        )
    assert not any(value != "temel" for value in evaluator.calls)


async def test_karsilastirma_iki_bagimsiz_ab_ba_cifti_calistirir():
    evaluator = _Evaluator()
    result = await search("system", "temel", generator=_Generator(), evaluator=evaluator)
    assert evaluator.calls == ["temel", "temel", "aday", "aday", "temel"]
    assert [item.arm for item in result.manifest] == ["A", "B", "B", "A"]
    assert [item.order for item in result.manifest] == [1, 2, 3, 4]


@pytest.mark.parametrize("unsafe", ["usd", "execution", "calls"])
def test_dev_secimi_maliyet_veya_basarisiz_mutasyon_artisini_reddeder(unsafe):
    base = Candidate(PromptVariant("system", "temel"), _report(cost=1.0))
    report = _report(
        passed=True,
        cost=2.0 if unsafe == "usd" else 1.0,
        failed_mutation=unsafe == "execution",
        calls=2 if unsafe == "calls" else 1,
    )
    candidate = Candidate(PromptVariant("system", "aday"), report)
    assert not select_winner(base, (candidate,)).improved


def test_cli_bes_aday_config_yuklemeden_reddedilir(monkeypatch):
    def forbidden():
        raise AssertionError("config yüklenmemeli")

    monkeypatch.setattr(prompt_opt_commands, "load_config", forbidden)
    result = CliRunner().invoke(
        app, ["prompt-opt", "calistir", "--kume", "x", "--ayri", "y", "--aday", "5"]
    )
    assert result.exit_code == 2
    assert "4" in result.output


@pytest.mark.parametrize("split", ["blind", "validation", "development"])
def test_cli_yeniden_adlandirilmis_yanlis_split_kumesini_reddeder(tmp_path, monkeypatch, split):
    from fusion_cli.cli.dongu_ortak import LoopPaths

    suite = tmp_path / "renamed.yaml"
    task_id = "T04" if split == "development" else "a"
    suite.write_text(
        "namespace: fusion_research\n"
        f"split: {split}\ntasks:\n  - id: {task_id}\n    request: gizli istek\n"
        "    criterion:\n      kind: keyword\n      keyword: tamam\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(prompt_opt_commands, "_suite_file", lambda *args: suite)
    monkeypatch.setattr(
        prompt_opt_commands,
        "loop_paths",
        lambda: LoopPaths(tmp_path, tmp_path, tmp_path, tmp_path, tmp_path, tmp_path),
    )
    result = CliRunner().invoke(
        app, ["prompt-opt", "calistir", "--kume", "renamed", "--ayri", "other"]
    )
    assert result.exit_code == 1
    assert "split" in result.output.lower(), result.output


def _local_config(tmp_path):
    import yaml

    from fusion_cli.config.loader import _build_runtime
    from fusion_cli.config.models import Config, EmbeddingConfig
    from fusion_cli.core.types import ModelSpec

    defaults = Path(prompt_opt_commands.__file__).parents[1] / "config" / "defaults.yaml"
    runtime = _build_runtime(yaml.safe_load(defaults.read_text(encoding="utf-8"))["runtime"])
    model = ModelSpec("scripted", "scripted/local")
    return Config(model, (model,), model, {}, runtime, EmbeddingConfig("local", ""), tmp_path, None)


def _write_suite(path, split, prefix):
    import yaml

    tasks = [
        {
            "id": f"{prefix}{index}",
            "request": f"{prefix} görevi {index}",
            "criterion": {"kind": "keyword", "keyword": "tamam"},
        }
        for index in range(3)
    ]
    payload = {"tasks": tasks}
    if split is not None:
        payload["split"] = split
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")


class _ScriptedRunner:
    def __init__(self, module, base, seen, failures):
        self.module, self.base = module, base
        self.seen, self.failures = seen, failures

    async def run(self, request, *, root, strict_approval=False, transcript=None):
        from evals.executor import AgentRunObservation

        is_candidate = self.base != self.module.TEXT
        self.seen.append((request[0], "B" if is_candidate else "A"))
        unsafe = self.failures.get(request[0]) if is_candidate else None
        event = ToolExecuted(
            name="write_file" if unsafe == "mutation" else "read_file",
            args={},
            outcome=ToolOutcome.FAILED if unsafe == "mutation" else ToolOutcome.OK,
            output="gözlem",
            mutating=unsafe == "mutation",
        )
        count = 2 if unsafe == "calls" else 1
        calls = tuple(
            ModelCallIdentity(
                str(index),
                "agent",
                "scripted/local",
                "scripted/local",
                cost_usd=2.0 if unsafe == "cost" else 1.0,
            )
            for index in range(count)
        )
        return AgentRunObservation(
            "tamam" if is_candidate else "eksik",
            count,
            claimed_success=is_candidate,
            calls=calls,
            trace_events=(event,),
        )


@pytest.fixture
def research_cli(tmp_path, monkeypatch):
    import sys
    import types

    from prompt_opt.evaluator import agent_executor_factory
    from prompt_opt.targets import TARGETS, PromptTarget

    from fusion_cli.cli.dongu_ortak import LoopPaths
    from fusion_cli.core.clock import SystemClock

    base = "Önce dosyayı oku, sonra düzelt ve doğrula.\n" * 8
    addition = "Değişiklik sonrasında sonucu tekrar kontrol et."
    module = types.ModuleType("f31_scripted_prompt")
    module.TEXT = base
    monkeypatch.setitem(sys.modules, module.__name__, module)
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text(base, encoding="utf-8")
    target = PromptTarget("system", prompt_file, module.__name__, "TEXT")
    monkeypatch.setitem(TARGETS, "system", target)
    paths = LoopPaths(
        tmp_path,
        tmp_path,
        tmp_path / "proposals",
        tmp_path / "versions",
        tmp_path / "log.jsonl",
        tmp_path,
    )
    monkeypatch.setattr(prompt_opt_commands, "loop_paths", lambda: paths)
    monkeypatch.setattr(prompt_opt_commands, "load_config", lambda: _local_config(tmp_path))
    _write_suite(tmp_path / "dev.yaml", "development", "d")
    _write_suite(tmp_path / "val.yaml", "validation", "v")
    seen, configs, failures = [], [], {}

    class Provider:
        async def propose(self, base_text, notes, count):
            return (addition,)

    def factory(config, selected):
        configs.append(config)
        return agent_executor_factory(
            _ScriptedRunner(module, base, seen, failures),
            selected,
            workspace_root=tmp_path / "runs",
            clock=SystemClock(),
        )

    monkeypatch.setattr(prompt_opt_commands, "_executor_factory", factory)
    monkeypatch.setattr(prompt_opt_commands, "_snippet_provider", lambda config: Provider())
    return paths, prompt_file, base, seen, configs, failures


def _invoke_research():
    return CliRunner().invoke(
        app, ["prompt-opt", "calistir", "--kume", "dev", "--ayri", "val", "--aday", "1"]
    )


def test_public_cli_gercek_executor_kaniti_ve_ab_ba_sirasi_kaydeder(research_cli):
    from prompt_opt.proposals import ProposalStore, text_digest

    paths, prompt_file, base, seen, configs, _ = research_cli
    result = _invoke_research()
    assert result.exit_code == 0, (result.output, result.exception)
    assert "onerildi" in result.output
    (proposal,) = ProposalStore(paths.proposals).list()
    assert prompt_file.read_text(encoding="utf-8") == base
    assert seen[::3] == [("d", arm) for arm in "AABBA"] + [("v", arm) for arm in "ABBA"]
    assert [(item.stage, item.arm, item.order) for item in proposal.run_manifest] == [
        (stage, arm, order)
        for stage in ("development", "validation")
        for order, arm in enumerate("ABBA", 1)
    ]
    assert all(item.measurement.cost_usd == 3.0 for item in proposal.run_manifest)
    assert all(item.metadata.source_digest for item in proposal.run_manifest)
    assert all(item.metadata.requested_model == "scripted/local" for item in proposal.run_manifest)
    assert proposal.candidate_digest == text_digest(proposal.candidate_text)
    assert proposal.parent_prompt_hash == proposal.base_digest == text_digest(base)
    assert proposal.split_roles == ("development", "validation")
    assert proposal.diagnostic.stage == "diagnostic"
    assert all(
        config.runtime.teacherless
        and not config.runtime.teacher_codex_fallback
        and not config.runtime.lessons
        for config in configs
    )
    assert any(
        field.path == "runtime.teacherless" and field.value is True
        for field in proposal.effective_flags
    )


@pytest.mark.parametrize("stage", ["d", "v"])
@pytest.mark.parametrize("unsafe", ["cost", "mutation", "calls"])
def test_public_cli_guvensiz_adayi_dev_ve_validation_asamasinda_saklamaz(
    research_cli, stage, unsafe
):
    from prompt_opt.proposals import ProposalStore

    paths, _, _, seen, _, failures = research_cli
    failures[stage] = unsafe
    result = _invoke_research()
    assert result.exit_code == 0, (result.output, result.exception)
    assert "onerildi" not in result.output
    assert ProposalStore(paths.proposals).list() == ()
    if stage == "d":
        assert not any(split == "v" for split, _ in seen)


def test_bilinmeyen_usd_ve_yurutme_sifir_olcum_diye_yazilmaz():
    from prompt_opt.research_evidence import measure

    measurement = measure(RunReport((TaskResult("a", False, False, 0, 1, 1.0),)))
    assert measurement.model_calls == 1
    assert measurement.cost_usd is None
    assert measurement.failed_mutations is None
    assert "cost_usd" in measurement.unknowns


def test_eski_oneri_json_yeni_kanit_uydurmadan_okunur(tmp_path):
    import json

    from prompt_opt.proposals import ProposalStore

    values = {
        "id": "on-0123456789",
        "prompt": "system",
        "created": "eski",
        "suite": "old",
        "heldout_suite": "old-val",
        "base_digest": "hash",
        "base_text": "a",
        "candidate_text": "ab",
        "addition": "b",
        "opt_base": 0.0,
        "opt_candidate": 1.0,
        "heldout_base": 0.0,
        "heldout_candidate": 1.0,
        "reason": "eski",
    }
    (tmp_path / "on-0123456789.json").write_text(json.dumps(values), encoding="utf-8")
    proposal = ProposalStore(tmp_path).get("on-0123456789")
    assert proposal.run_manifest == ()
    assert proposal.candidate_digest is None
    assert proposal.diagnostic is None


@pytest.mark.parametrize("problem", ["same-split", "id-overlap", "request-overlap", "blind"])
def test_public_cli_split_ve_kopya_korumasini_config_oncesi_uygular(
    research_cli, monkeypatch, problem
):
    import yaml

    paths, _, _, seen, _, _ = research_cli
    development = yaml.safe_load((paths.suites / "dev.yaml").read_text(encoding="utf-8"))
    validation = yaml.safe_load((paths.suites / "val.yaml").read_text(encoding="utf-8"))
    if problem in {"same-split", "blind"}:
        validation["split"] = "development" if problem == "same-split" else "blind"
    elif problem == "id-overlap":
        validation["tasks"][0]["id"] = development["tasks"][0]["id"]
    else:
        validation["tasks"][0]["request"] = " D   GÖREVİ  0 "
    (paths.suites / "val.yaml").write_text(yaml.safe_dump(validation), encoding="utf-8")

    def forbidden():
        raise AssertionError("geçersiz split için config yüklenmemeli")

    monkeypatch.setattr(prompt_opt_commands, "load_config", forbidden)
    result = _invoke_research()
    assert result.exit_code == 1, (result.output, result.exception)
    assert seen == []
    assert not paths.proposals.exists()


def test_legacy_kumeler_kokeni_bilinmiyor_olarak_saklanir(research_cli):
    from prompt_opt.proposals import ProposalStore

    paths, _, _, _, _, _ = research_cli
    _write_suite(paths.suites / "dev.yaml", None, "d")
    _write_suite(paths.suites / "val.yaml", None, "v")
    result = _invoke_research()
    assert result.exit_code == 0, (result.output, result.exception)
    (proposal,) = ProposalStore(paths.proposals).list()
    assert proposal.split_roles == (None, None)
    assert all(item.metadata.split is None for item in proposal.run_manifest)

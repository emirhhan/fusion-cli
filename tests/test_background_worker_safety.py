"""Arka plan işçisinin güvenlik sınırları: başlatma, kısıt taşıma, onay ayrıntısı (P-048)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from fusion_cli.cli import background_worker
from fusion_cli.core.background_store import BackgroundTaskStore
from fusion_cli.core.background_tasks import BackgroundTask, TaskOptions
from fusion_cli.core.clock import SystemClock
from fusion_cli.tools import agent_tasks

from .fakes import make_config


def test_isci_proje_dizinindeki_golge_paketi_ice_aktarmaz(tmp_path):
    # Ölçüldü (31 Ekim): `python -m` cwd'yi sys.path[0]'a koyuyordu; güvenilmeyen depodaki
    # `yaml/__init__.py` işçi açılırken onaysız çalışıyordu.
    project = tmp_path / "depo"
    (project / "yaml").mkdir(parents=True)
    marker = tmp_path / "pwned"
    (project / "yaml" / "__init__.py").write_text(
        f"open({str(marker)!r}, 'w').write('x')\n", encoding="utf-8"
    )
    argv = [*agent_tasks.worker_argv(tmp_path / "arka-plan", "deadbeef"), "--help"]
    env = {
        **os.environ,
        "HOME": str(tmp_path / "ev"),
        "XDG_CONFIG_HOME": str(tmp_path / "ev" / ".config"),
        "FUSION_KEYCHAIN": "off",
    }

    result = subprocess.run(
        argv, cwd=project, env=env, capture_output=True, text=True, timeout=120, check=False
    )

    assert result.returncode == 0, result.stderr
    assert "arka-plan-calistir" in result.stdout
    assert not marker.exists()


def test_isci_komutu_guvenli_yol_kipini_kullanir():
    argv = agent_tasks.worker_argv(Path("/tmp/x"), "deadbeef")
    if not getattr(sys, "frozen", False):
        assert argv[1] == "-P"


# ------------------------------------------------------- fusion agent --bg bayrakları


@pytest.fixture
def launches(monkeypatch):
    calls: list[list[str]] = []

    def _fake(argv, cwd, log, err) -> int:
        calls.append(argv)
        return 4321

    monkeypatch.setattr(agent_tasks, "spawn_detached", _fake)
    return calls


@pytest.fixture
def cli_config(tmp_path, monkeypatch):
    from fusion_cli.cli import agent_commands
    from fusion_cli.cli import app as app_module

    config = make_config(memory_dir=tmp_path / "bellek")
    monkeypatch.setattr(agent_commands, "load_config", lambda: config)
    monkeypatch.setattr(app_module, "load_config", lambda: config)
    monkeypatch.setattr(app_module._SESSION, "overrides", ((), None))
    monkeypatch.chdir(tmp_path)
    return config


def _only_task(config):
    tasks = agent_tasks.task_store(config.memory_dir).tasks()
    assert len(tasks) == 1
    return tasks[0]


def test_fusion_agent_bg_kisit_bayraklarini_iscide_uygulanacak_bicimde_tasir(
    cli_config, launches, tmp_path
):
    from fusion_cli.cli.app import app

    extra = tmp_path / "ek"
    extra.mkdir()
    result = CliRunner().invoke(
        app,
        [
            "agent",
            "--bg",
            "--disallowed-tools",
            "Bash",
            "--allowed-tools",
            "read_file,write_file",
            "--max-budget-usd",
            "1",
            "--add-dir",
            str(extra),
            "--append-system-prompt",
            "kısa yaz",
            "--no-memory",
            "refactor",
        ],
    )

    assert result.exit_code == 0, result.output
    options = _only_task(cli_config).options
    assert "run_shell" in options.denied_tools
    assert options.allowed_tools == ("read_file", "write_file")
    assert options.max_budget_usd == 1.0
    assert options.extra_roots == (str(extra.resolve()),)
    assert options.extra_system == "kısa yaz"
    assert options.memory is False
    assert launches


def test_fusion_agent_bg_oturumluk_ayarlari_tasir(cli_config, launches):
    from fusion_cli.cli.app import app

    result = CliRunner().invoke(
        app, ["--set", "runtime.max_tokens=1000", "agent", "--bg", "rapor yaz"]
    )

    assert result.exit_code == 0, result.output
    assert _only_task(cli_config).options.config_overrides == ("runtime.max_tokens=1000",)


@pytest.mark.parametrize(
    "flags",
    [["--output-format", "json"], ["--json"], ["--permission-channel", "stdin"]],
)
def test_fusion_agent_bg_anlamsiz_bayragi_acik_hatayla_reddeder(cli_config, launches, flags):
    from fusion_cli.cli.app import app

    result = CliRunner().invoke(app, ["agent", "--bg", *flags, "rapor"])

    assert result.exit_code == 2
    assert "--bg ile kullanılamaz" in result.output
    assert launches == []


def test_fusion_agent_bg_calisma_agacini_gorev_koku_yapar(cli_config, launches, tmp_path):
    from fusion_cli.cli.app import app

    git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    subprocess.run([*git, "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run([*git, "commit", "-qm", "ilk"], cwd=tmp_path, check=True)

    result = CliRunner().invoke(app, ["agent", "--bg", "--worktree", "deneme", "refactor"])

    assert result.exit_code == 0, result.output
    task = _only_task(cli_config)
    assert Path(task.root) != tmp_path.resolve()
    assert "deneme" in task.root and Path(task.root, "a.txt").exists()


# ------------------------------------------------------- işçide kısıt uygulama


def _task(tmp_path: Path, **kwargs) -> BackgroundTask:
    store = BackgroundTaskStore(tmp_path / "arka-plan", SystemClock())
    return store.create("iş", root=tmp_path, **kwargs)


def test_isci_arac_kumesini_yalniz_daraltir(tmp_path):
    task = _task(
        tmp_path,
        options=TaskOptions(allowed_tools=("read_file", "write_file"), denied_tools=("web_*",)),
    )

    allowed, denied = background_worker.task_tool_limits(
        task, {"read_file", "grep"}, frozenset({"run_shell"})
    )

    assert allowed == {"read_file"}
    assert denied >= {"run_shell", "web_*"}


def test_yazma_alanli_gorevde_kabuk_kapanir_duzenleme_kalir(tmp_path):
    task = _task(tmp_path, options=TaskOptions(write_scope=(str(tmp_path / "docs"),)))

    _allowed, denied = background_worker.task_tool_limits(task, None, frozenset())
    context = background_worker.task_tool_context(task, make_config())

    assert "run_shell" in denied and "write_file" not in denied
    assert context.write_scope == (tmp_path / "docs",)


def test_isci_baglami_kok_disi_engelleri_yapilandirmadan_alir(tmp_path):
    config = make_config(runtime={"block_writes_outside_root": True})
    task = _task(tmp_path, read_only=True)

    context = background_worker.task_tool_context(task, config)

    assert context.block_writes_outside_root is True
    assert context.write_scope == ()


def test_isci_yapilandirmasi_butce_ve_oturum_ayarlarini_uygular(tmp_path):
    task = _task(
        tmp_path,
        options=TaskOptions(max_budget_usd=2.5, config_overrides=("runtime.max_tokens=1234",)),
    )

    config = background_worker.task_config(task, make_config())

    assert config.runtime.agent_max_cost_usd == 2.5
    assert config.runtime.max_tokens == 1234


async def test_isci_turu_kisitlari_motor_cagrisina_gecirir(tmp_path, monkeypatch):
    from fusion_cli.cli import session
    from fusion_cli.config import loader

    seen: dict[str, object] = {}

    async def _fake_run(prompt, config, **kwargs):
        seen.update(kwargs, prompt=prompt, config=config)
        return SimpleNamespace(final_text="bitti", ok=True)

    monkeypatch.setattr(session, "run_agent_task", _fake_run)
    monkeypatch.setattr(loader, "load_config", lambda: make_config(memory_dir=tmp_path / "m"))
    store = BackgroundTaskStore(tmp_path / "arka-plan", SystemClock())
    task = store.create(
        "iş",
        root=tmp_path,
        mode="plan",
        options=TaskOptions(denied_tools=("run_shell",), extra_system="ek not", memory=False),
    )

    run = background_worker.agent_turn_runner(5.0, store)
    text, ok = await run(task, "iş", [])

    assert (text, ok) == ("bitti", True)
    assert "run_shell" in seen["denied_tools"]
    assert str(seen["mode"]) in {"plan", "ApprovalMode.PLAN"}
    assert "ek not" in str(seen["extra_system"])
    assert seen["conversation_id"] == f"arka-{task.id}"
    assert seen["tool_context"].root == tmp_path

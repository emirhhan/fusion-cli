"""`fusion agents` tablosu ve temizlik komutları (P-048)."""

from __future__ import annotations

from rich.console import Console
from typer.testing import CliRunner

from fusion_cli.cli import agent_commands
from fusion_cli.cli.repl.background_commands import tasks_command
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.background_tasks import TaskStatus
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools import agent_tasks
from fusion_cli.ui.background_view import task_table

from .fakes import make_config


def test_tablo_model_metnindeki_koseli_parantezi_markup_saymaz(tmp_path):
    # Ölçüldü (31 Ekim): özetteki `[/etc/hosts]` MarkupError ile `fusion agents`'ı çökertiyor,
    # `[OK]` sessizce siliniyordu.
    store = agent_tasks.task_store(tmp_path)
    task = store.create("iş", root=tmp_path, name="[ad]")
    done = store.update(
        task.id, status=TaskStatus.COMPLETED, summary="bakın [/etc/hosts] dosyası [OK]"
    )
    console = Console(record=True, width=200)

    console.print(task_table([done]))

    output = console.export_text()
    assert "[/etc/hosts]" in output and "[OK]" in output


def _two_projects(tmp_path, config):
    store = agent_tasks.task_store(config.memory_dir)
    here, there = tmp_path / "a", tmp_path / "b"
    here.mkdir()
    there.mkdir()
    for root in (here, there):
        task = store.create("iş", root=root)
        store.update(task.id, status=TaskStatus.COMPLETED)
    return store, here, there


def test_fusion_agents_temizle_varsayilan_yalniz_bu_proje(tmp_path, monkeypatch):
    config = make_config(memory_dir=tmp_path / "bellek")
    monkeypatch.setattr(agent_commands, "load_config", lambda: config)
    store, here, there = _two_projects(tmp_path, config)
    monkeypatch.chdir(here)

    result = CliRunner().invoke(agent_commands.app, ["temizle"])

    assert result.exit_code == 0, result.output
    assert [task.root for task in store.tasks()] == [str(there.resolve())]
    every = CliRunner().invoke(agent_commands.app, ["temizle", "--tum"])
    assert every.exit_code == 0 and store.tasks() == ()


def test_repl_tasks_clean_yalniz_bu_proje_all_ile_tumu(tmp_path):
    config = make_config(memory_dir=tmp_path / "bellek")
    store, here, there = _two_projects(tmp_path, config)
    state = ReplState(config=config, memory=null_memory(), root=here, home=tmp_path / "ev")

    tasks_command(state, "clean")
    assert [task.root for task in store.tasks()] == [str(there.resolve())]
    tasks_command(state, "clean all")
    assert store.tasks() == ()


def test_ctrl_b_kesilen_turun_dokundugu_dosyalari_devir_istemine_ekler(tmp_path, monkeypatch):
    # Ölçüldü (31 Ekim): Ctrl+B turu iptal edip görevi baştan başlatıyordu; kesilen turun
    # düzenlediği dosyalar devredilmediği için işçi aynı değişikliği tekrarlayabiliyordu.
    from fusion_cli.cli.repl.background_commands import interrupted_to_background
    from fusion_cli.core.changeset import ChangeSet

    monkeypatch.setattr(agent_tasks, "spawn_detached", lambda *args: 1)
    config = make_config(memory_dir=tmp_path / "bellek")
    state = ReplState(config=config, memory=null_memory(), root=tmp_path, home=tmp_path / "ev")
    changes = ChangeSet()
    changes.record(tmp_path / "src" / "app.py")
    state.last_changes = changes

    notice = interrupted_to_background(state, "testleri düzelt")

    prompt = agent_tasks.task_store(config.memory_dir).tasks()[0].prompt
    assert "src/app.py" in prompt and "yeniden" in prompt
    assert "baştan" in notice

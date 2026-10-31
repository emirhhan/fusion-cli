"""`fusion agents` tablosu ve temizlik komutları (P-048)."""

from __future__ import annotations

from rich.console import Console

from fusion_cli.core.background_tasks import TaskStatus
from fusion_cli.tools import agent_tasks
from fusion_cli.ui.background_view import task_table


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

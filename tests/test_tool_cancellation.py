"""Senkron araç iptali coroutine değil gerçek worker temizliğini bekler."""

from __future__ import annotations

import asyncio
import os
import threading
from contextlib import suppress

import pytest

from fusion_cli.core.tools import Tool, ToolContext, ToolResult
from fusion_cli.tools.registry import ToolRegistry


async def test_sync_tool_cancel_waits_for_worker_cleanup(tmp_path):
    entered, cleaning, release, finished = (threading.Event() for _ in range(4))

    def operation(args, context):
        entered.set()
        context.cancelled.wait()
        cleaning.set()
        release.wait()
        finished.set()
        return ToolResult("temizlendi")

    registry = ToolRegistry()
    registry.register(Tool("offline", "", {}, operation))
    context = ToolContext(root=tmp_path)
    task = asyncio.create_task(registry.execute("offline", {}, context))
    await asyncio.to_thread(entered.wait, 1)
    task.cancel()
    try:
        assert await asyncio.to_thread(cleaning.wait, 1)
        assert not task.done(), "Worker temizlenmeden iptal tamamlanmış sayıldı."
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(finished.wait, 1)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not context.cancelled.is_set(), "Tek çağrının iptali parent bağlamını zehirlememeli."


@pytest.mark.skipif(os.name == "nt", reason="POSIX süreç grubu smoke; Windows kabulü ayrı.")
async def test_shell_cancel_reaps_owned_tree_and_keeps_independent_process(tmp_path):
    import json
    import os
    import shlex
    import signal
    import sys

    from fusion_cli.tools.shell import run_shell

    ready = tmp_path / "ready.json"
    script = tmp_path / "owned.py"
    script.write_text("""import json, os, signal, subprocess, sys, time
from pathlib import Path
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
def stop(*_):
    child.terminate()
    child.wait()
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
Path(sys.argv[1]).write_text(json.dumps([os.getpid(), child.pid]))
while True: time.sleep(0.1)
""")
    independent = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(60)"
    )
    registry = ToolRegistry()
    registry.register(Tool("run_shell", "", {}, run_shell, mutating=True))
    command = " ".join(shlex.quote(str(value)) for value in (sys.executable, script, ready))
    task = asyncio.create_task(
        registry.execute("run_shell", {"command": command}, ToolContext(root=tmp_path))
    )
    pids = []
    try:
        async with asyncio.timeout(5):
            while not ready.exists():  # noqa: ASYNC110 — süreç dışı hazır dosyası; üstte 5s sınır.
                await asyncio.sleep(0.01)
        pids = json.loads(ready.read_text())
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(task), timeout=5)
        assert independent.returncode is None
        for pid in pids:
            with pytest.raises(ProcessLookupError):
                os.kill(pid, 0)
    finally:
        for pid in pids:
            with suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        independent.terminate()
        await asyncio.wait_for(independent.wait(), 5)


@pytest.mark.skipif(os.name == "nt", reason="POSIX süreç grubu doğrulaması.")
async def test_cancel_kills_term_resistant_child_with_closed_pipes(tmp_path):
    import json
    import shlex
    import signal
    import sys

    from fusion_cli.core.errors import CleanupFailedError, ProcessCancelledError
    from fusion_cli.core.process_control import run_foreground

    ready = tmp_path / "resistant.json"
    script = tmp_path / "resistant.py"
    script.write_text("""import json, os, signal, subprocess, sys, time
from pathlib import Path
child_code = (
    "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
    "print('ready', flush=True); time.sleep(60)"
)
child = subprocess.Popen(
    [sys.executable, "-c", child_code],
    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
)
child.stdout.readline()
child.stdout.close()
Path(sys.argv[1]).write_text(json.dumps([os.getpid(), child.pid]))
while True: time.sleep(0.1)
""")
    cancelled = threading.Event()
    command = " ".join(shlex.quote(str(value)) for value in (sys.executable, script, ready))
    task = asyncio.create_task(
        asyncio.to_thread(
            run_foreground,
            command,
            cwd=tmp_path,
            env=dict(os.environ),
            cancelled=cancelled,
            timeout_s=30,
        )
    )
    pids = []
    try:
        async with asyncio.timeout(5):
            while not ready.exists():  # noqa: ASYNC110 — süreç dışı hazır dosyası; üstte 5s sınır.
                await asyncio.sleep(0.01)
        pids = json.loads(ready.read_text())
        cancelled.set()
        with pytest.raises((ProcessCancelledError, CleanupFailedError)):
            await asyncio.wait_for(asyncio.shield(task), 5)
        # Orphan zombies may await OS reaping, but no live child may remain.

        probe = await asyncio.create_subprocess_exec(
            "ps", "-o", "stat=", "-p", str(pids[1]), stdout=asyncio.subprocess.PIPE
        )
        output, _ = await probe.communicate()
        state = output.decode().strip()
        assert not state or state.startswith("Z"), f"Child survived cancellation: {state}"
    finally:
        cancelled.set()
        for pid in pids:
            with suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
        await asyncio.gather(task, return_exceptions=True)

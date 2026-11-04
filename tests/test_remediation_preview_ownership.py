"""Önizleme sahipliği readiness ve install beklerken de korunur."""

from __future__ import annotations

import asyncio
import sys

import pytest

from fusion_cli.core.process_control import terminate_async_process_tree
from fusion_cli.tools import preview_launch, preview_server


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [asyncio.CancelledError, RuntimeError])
@pytest.mark.parametrize("named", [False, True])
async def test_preview_start_failure_reaps_owned_process(tmp_path, monkeypatch, failure, named):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(60)",
        start_new_session=True,
    )
    log_path = tmp_path / "server.log"
    log_path.write_text("başlatıldı")

    async def spawn(*args, **kwargs):
        return process, log_path

    async def probe(*args, **kwargs):
        raise failure()

    monkeypatch.setattr(preview_server, "spawn_logged", spawn)
    monkeypatch.setattr(preview_server, "wait_until_serving", probe)
    try:
        with pytest.raises(failure):
            if named:
                config = preview_launch.LaunchConfig(
                    "web", sys.executable, (), 18770, None, trusted=True
                )
                await preview_launch.start_launch(tmp_path, config)
            else:
                await preview_server.start(
                    tmp_path, preview_server.PreviewKind.PHP, 18770, php="php"
                )
        await asyncio.sleep(0.02)
        assert process.returncode is not None, "başlatma başarısızlığında süreç sahipsiz kalamaz"
        assert preview_server.running(tmp_path) is None
        assert not log_path.exists()
    finally:
        if process.returncode is None:
            await terminate_async_process_tree(process)
        preview_server._RUNNING.pop(tmp_path, None)


@pytest.mark.asyncio
async def test_cancel_during_npm_install_reaps_owned_process(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text('{"scripts":{"dev":"node app.js"}}')
    spawned = []
    spawned_event = asyncio.Event()

    async def spawn(*args, **kwargs):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
            start_new_session=True,
        )
        spawned.append(process)
        spawned_event.set()
        return process

    monkeypatch.setattr(preview_server, "_spawn", spawn)
    task = asyncio.create_task(preview_server._node_command(tmp_path, 18770))
    try:
        await spawned_event.wait()
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert spawned[0].returncode is not None
    finally:
        if spawned and spawned[0].returncode is None:
            await terminate_async_process_tree(spawned[0])


@pytest.mark.asyncio
async def test_cancellation_while_spawn_returns_still_owns_process(tmp_path, monkeypatch):
    original_spawn = asyncio.create_subprocess_exec
    created = asyncio.Event()
    release = asyncio.Event()
    spawned = []

    async def delayed_spawn(*args, **kwargs):
        process = await original_spawn(
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
            start_new_session=True,
        )
        spawned.append(process)
        created.set()
        await release.wait()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    task = asyncio.create_task(preview_server._spawn(["ignored"], tmp_path))
    try:
        await created.wait()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert spawned[0].returncode is not None
    finally:
        release.set()
        if spawned and spawned[0].returncode is None:
            await terminate_async_process_tree(spawned[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["ready", "failed", "cancelled"])
async def test_concurrent_preview_start_joins_same_readiness(tmp_path, monkeypatch, outcome):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(60)",
        start_new_session=True,
    )
    log_path = tmp_path / "server.log"
    log_path.write_text("hazırlanıyor")
    probing = asyncio.Event()
    release = asyncio.Event()

    async def spawn(*args, **kwargs):
        return process, log_path

    async def probe(*args, **kwargs):
        probing.set()
        await release.wait()
        return outcome == "ready"

    monkeypatch.setattr(preview_server, "spawn_logged", spawn)
    monkeypatch.setattr(preview_server, "wait_until_serving", probe)
    first = asyncio.create_task(
        preview_server.start(tmp_path, preview_server.PreviewKind.PHP, 18770, php="php")
    )
    second = None
    try:
        await probing.wait()
        second = asyncio.create_task(
            preview_server.start(tmp_path, preview_server.PreviewKind.PHP, 18771, php="php")
        )
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(second), timeout=0.1)
        if outcome == "cancelled":
            first.cancel()
        release.set()
        if outcome == "ready":
            assert await first is await second
        else:
            expected = (
                asyncio.CancelledError if outcome == "cancelled" else preview_server.PreviewError
            )
            with pytest.raises(expected):
                await first
            with pytest.raises(expected):
                await second
            assert process.returncode is not None
    finally:
        release.set()
        for task in (first, second):
            if task is not None:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        if process.returncode is None:
            await terminate_async_process_tree(process)
        preview_server._RUNNING.pop(tmp_path.resolve(), None)

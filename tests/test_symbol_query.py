"""Sembol aracını gerçek, yalnız yerel JSON-RPC süreciyle doğrula."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from pathlib import Path

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import build_registry

SERVER = r"""
import json, os, sys, time
from pathlib import Path
root = Path(sys.argv[1])
root.joinpath("pid").write_text(str(os.getpid()))
mode = sys.argv[2]
uri = ""
def send(payload):
    body = json.dumps(payload).encode()
    sys.stdout.buffer.write(b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
    sys.stdout.buffer.flush()
while True:
    length = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            sys.exit()
        if line == b"\r\n":
            break
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":")[1])
    message = json.loads(sys.stdin.buffer.read(length))
    method = message.get("method")
    with root.joinpath("calls").open("a") as log:
        log.write(json.dumps(message) + "\n")
    if method == "textDocument/didOpen":
        uri = message["params"]["textDocument"]["uri"]
        if mode.startswith("push"):
            report = {"uri": uri, "version": 1,
                      "diagnostics": [{"message": "kontrollu push"}]}
            if mode == "push_missing_list":
                report.pop("diagnostics")
            if mode == "push_missing_version":
                report.pop("version")
                report["diagnostics"] = []
            if mode == "push_wrong_version":
                report["version"] = 0
            if mode == "push_invalid_list":
                report["diagnostics"] = {}
            if mode == "push_empty":
                report["diagnostics"] = []
            send({"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics",
                  "params": report})
        if mode == "write_request":
            send({"jsonrpc": "2.0", "id": 900, "method": "workspace/applyEdit",
                  "params": {"edit": {"changes": {uri: [{"newText": "silindi"}]}}}})
    if "id" not in message:
        if method == "exit":
            sys.exit()
        continue
    if mode == "hang" and method != "initialize":
        time.sleep(60)
    if "method" not in message:
        continue
    if method == "initialize":
        result = {"capabilities": {"diagnosticProvider": {
            "interFileDependencies": False, "workspaceDiagnostics": False}}}
        if mode.startswith("push"):
            result = {"capabilities": {}}
    elif method in ("textDocument/definition", "textDocument/references"):
        if mode in ("oversized", "header", "malformed", "flood"):
            bodies = {"oversized": b"Content-Length: 999999999\r\n\r\n",
                      "header": b"X: " + b"a" * 9000 + b"\r\n\r\n",
                      "malformed": b"Content-Length: 1\r\n\r\nx",
                      "flood": b"Content-Length: 200000\r\n\r\n" + b"a" * 200000}
            sys.stdout.buffer.write(bodies[mode])
            sys.stdout.buffer.flush()
            continue
        target = {"remote": "https://example.invalid/sample.py",
                  "outside": root.parent.joinpath("outside.py").as_uri(),
                  "secret": root.joinpath(".env").as_uri()}.get(mode, uri)
        result = [{"uri": target, "range": {"start": {"line": 0, "character": 4},
                                          "end": {"line": 0, "character": 10}}}]
        if mode == "many":
            result *= 110
    elif method == "textDocument/diagnostic":
        result = {"kind": "full", "items": [{"range": {"start": {"line": 0}},
                  "message": "kontrollu bulgu", "severity": 2}]}
        if mode == "long":
            result["items"][0]["message"] *= 3000
        if mode == "bad_diagnostics":
            result = {"kind": "unchanged", "resultId": "cached"}
        if mode == "pull_missing_kind":
            result = {"items": []}
        if mode == "pull_missing_items":
            result = {"kind": "full"}
        if mode == "pull_empty":
            result = {"kind": "full", "items": []}
    else:
        result = None
    send({"jsonrpc": "2.0", "id": message["id"], "result": result})
"""


def _settings(tmp_path: Path, *, mode: str = "normal", timeout: float = 2.0):
    from fusion_cli.tools.symbol_query import SymbolQuerySettings

    server = tmp_path / "server.py"
    server.write_text(SERVER, encoding="utf-8")
    return SymbolQuerySettings(
        command=(sys.executable, "-I", str(server), str(tmp_path), mode), timeout_s=timeout
    )


def _args(action: str = "definition") -> dict[str, object]:
    return {"action": action, "path": "sample.py", "line": 0, "character": 4, "symbol": "sample"}


def _source(tmp_path: Path) -> ToolContext:
    (tmp_path / "sample.py").write_text("def sample():\n    return 1\n", encoding="utf-8")
    return ToolContext(tmp_path, restrict_to_root=True)


def _assert_stopped(tmp_path: Path) -> None:
    pid = int((tmp_path / "pid").read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_varsayilanda_sema_ve_surec_yok(tmp_path):
    assert build_registry().get("symbol_query") is None
    assert not (tmp_path / "pid").exists()


def test_sunucu_ayari_var_ama_bayrak_kapaliysa_arac_sunulmaz(tmp_path, monkeypatch):
    async def forbidden_start(*args, **kwargs):
        pytest.fail("Kapalı LSP sunucu başlatamaz.")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_start)
    registry = build_registry(symbol_query_settings=_settings(tmp_path))
    assert registry.get("symbol_query") is None
    assert not (tmp_path / "pid").exists()


def test_sembol_araci_mevcut_izin_ve_mutasyon_filtresini_kullanir(tmp_path):
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.engines.agent.loop import _permitted

    registry = build_registry(symbol_query_enabled=True, symbol_query_settings=_settings(tmp_path))
    policy = ExecutionPolicy(is_web=False, allow_mutation=False)
    permitted = _permitted({"symbol_query"}, registry, policy)
    assert "symbol_query" in permitted
    denied = _permitted({"symbol_query"}, registry, policy, denied=("symbol_query",))
    assert "symbol_query" not in denied
    assert not registry.get("symbol_query").mutating
    assert not (tmp_path / "pid").exists()


async def test_lexical_iptali_sonraki_arac_cagrisini_zehirlemez(tmp_path, monkeypatch):
    from fusion_cli.core.tools import ToolResult
    from fusion_cli.tools import symbol_query

    context = _source(tmp_path)
    started = threading.Event()
    stopped = threading.Event()

    def controlled_search(args, invocation, *, source=None):
        started.set()
        invocation.cancelled.wait(2)
        stopped.set()
        return ToolResult("iptal")

    monkeypatch.setattr(symbol_query, "search_code", controlled_search)
    registry = build_registry(symbol_query_enabled=True)
    task = asyncio.create_task(registry.execute("symbol_query", _args(), context))
    assert await asyncio.to_thread(started.wait, 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set() and not context.cancelled.is_set()
    assert (await registry.execute("read_file", {"path": "sample.py"}, context)).ok


async def test_sunucu_yazma_istegi_reddedilir(tmp_path):
    context = _source(tmp_path)
    registry = build_registry(
        symbol_query_enabled=True, symbol_query_settings=_settings(tmp_path, mode="write_request")
    )
    result = await registry.execute("symbol_query", _args(), context)
    assert result.ok, result.output
    calls = [json.loads(line) for line in (tmp_path / "calls").read_text().splitlines()]
    rejected = next(call for call in calls if call.get("id") == 900)
    assert rejected["error"]["code"] == -32601
    assert (tmp_path / "sample.py").read_text().startswith("def sample")
    _assert_stopped(tmp_path)


async def test_gecmis_diagnostics_yaniti_temiz_sonuc_sayilmaz(tmp_path):
    context = _source(tmp_path)
    registry = build_registry(
        symbol_query_enabled=True, symbol_query_settings=_settings(tmp_path, mode="bad_diagnostics")
    )
    result = await registry.execute("symbol_query", _args("diagnostics"), context)
    assert not result.ok
    _assert_stopped(tmp_path)


@pytest.mark.parametrize("action", ["definition", "references", "diagnostics"])
async def test_registry_uc_eylemi_gercek_lsp_surecine_iletir(tmp_path, action):
    context = _source(tmp_path)
    registry = build_registry(symbol_query_enabled=True, symbol_query_settings=_settings(tmp_path))
    result = await registry.execute("symbol_query", _args(action), context)
    assert result.ok, result.output
    assert "LSP" in result.output
    assert "sample.py" in result.output
    calls = [json.loads(line) for line in (tmp_path / "calls").read_text().splitlines()]
    methods = [call["method"] for call in calls]
    expected = "textDocument/diagnostic" if action == "diagnostics" else f"textDocument/{action}"
    assert methods == [
        "initialize",
        "initialized",
        "textDocument/didOpen",
        expected,
        "textDocument/didClose",
        "shutdown",
        "exit",
    ]
    assert calls[0]["params"]["rootUri"] == tmp_path.as_uri()
    assert calls[2]["params"]["textDocument"]["text"].startswith("def sample")
    _assert_stopped(tmp_path)


async def test_sunucu_yoksa_lexical_fallback_diagnostics_iddiasi_tasimaz(tmp_path):
    context = _source(tmp_path)
    result = await build_registry(symbol_query_enabled=True).execute(
        "symbol_query", _args(), context
    )
    assert result.ok and "lexical fallback" in result.output
    assert "sample.py:1" in result.output
    diagnostics = await build_registry(symbol_query_enabled=True).execute(
        "symbol_query", _args("diagnostics"), context
    )
    assert not diagnostics.ok and "lexical fallback" in diagnostics.output
    assert diagnostics.structured["source"] == "lexical"


async def test_lexical_cikti_kirpildiginda_kismi_sonuc_bildirilir(tmp_path):
    from fusion_cli.core.constants import MAX_OUTPUT_CHARS

    context = _source(tmp_path)
    (tmp_path / "sample.py").write_text(("sample " + "x" * 15000 + "\n") * 3, encoding="utf-8")
    result = await build_registry(symbol_query_enabled=True).execute(
        "symbol_query", _args(), context
    )
    assert result.ok and len(result.output) <= MAX_OUTPUT_CHARS
    assert "sonuç kısmidir" in result.output


async def test_timeout_sunucuyu_kapatir(tmp_path):
    context = _source(tmp_path)
    registry = build_registry(
        symbol_query_enabled=True,
        symbol_query_settings=_settings(tmp_path, mode="hang", timeout=0.3),
    )
    result = await registry.execute("symbol_query", _args(), context)
    assert not result.ok and "süre" in result.output
    _assert_stopped(tmp_path)


@pytest.mark.parametrize("event_cancel", [False, True])
async def test_iptal_sunucuyu_kapatir(tmp_path, event_cancel):
    context = _source(tmp_path)
    registry = build_registry(
        symbol_query_enabled=True, symbol_query_settings=_settings(tmp_path, mode="hang")
    )
    task = asyncio.create_task(registry.execute("symbol_query", _args(), context))
    async with asyncio.timeout(2):
        while (  # noqa: ASYNC110 - süreç günlüğü yoklanır
            not (tmp_path / "calls").exists()
            or "textDocument/definition" not in (tmp_path / "calls").read_text()
        ):
            await asyncio.sleep(0.01)
    if event_cancel:
        context.cancelled.set()
        result = await task
        assert not result.ok and "iptal" in result.output
    else:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    _assert_stopped(tmp_path)


@pytest.mark.parametrize(
    "extra",
    [
        {"command": "bad"},
        {"line": -1},
        {"action": "rename"},
        {"path": "../outside.py"},
        {"path": ".env"},
    ],
)
async def test_girdi_ve_kok_siniri_surec_baslatmadan_reddedilir(tmp_path, extra):
    context = _source(tmp_path)
    registry = build_registry(symbol_query_enabled=True, symbol_query_settings=_settings(tmp_path))
    result = await registry.execute("symbol_query", _args() | extra, context)
    assert not result.ok
    assert not (tmp_path / "pid").exists()


async def test_push_tanilari_gercek_lsp_surecinden_alinir(tmp_path):
    context = _source(tmp_path)
    registry = build_registry(
        symbol_query_enabled=True, symbol_query_settings=_settings(tmp_path, mode="push")
    )
    result = await registry.execute("symbol_query", _args("diagnostics"), context)
    assert result.ok and "kontrollu push" in result.output
    _assert_stopped(tmp_path)


@pytest.mark.parametrize(
    "mode", ["oversized", "header", "malformed", "flood", "remote", "outside", "secret"]
)
async def test_guvensiz_ve_bozuk_lsp_yaniti_reddedilir_ve_surec_kapanir(tmp_path, mode):
    context = _source(tmp_path)
    registry = build_registry(
        symbol_query_enabled=True, symbol_query_settings=_settings(tmp_path, mode=mode)
    )
    result = await registry.execute("symbol_query", _args(), context)
    assert not result.ok
    assert "beklenmedik hata" not in result.output
    _assert_stopped(tmp_path)


@pytest.mark.parametrize("mode,action", [("many", "references"), ("long", "diagnostics")])
async def test_lsp_ciktisi_sinirlidir_ve_kismi_sonuc_bildirilir(tmp_path, mode, action):
    from fusion_cli.core.constants import MAX_OUTPUT_CHARS

    context = _source(tmp_path)
    registry = build_registry(
        symbol_query_enabled=True, symbol_query_settings=_settings(tmp_path, mode=mode)
    )
    result = await registry.execute("symbol_query", _args(action), context)
    assert result.ok and len(result.output) <= MAX_OUTPUT_CHARS
    assert "sonuç kısmidir" in result.output
    _assert_stopped(tmp_path)


async def test_kurulmamis_komut_lexical_yola_doner(tmp_path):
    from fusion_cli.tools.symbol_query import SymbolQuerySettings

    context = _source(tmp_path)
    settings = SymbolQuerySettings(command=(str(tmp_path / "missing-server"),))
    registry = build_registry(symbol_query_enabled=True, symbol_query_settings=settings)
    result = await registry.execute("symbol_query", _args(), context)
    assert result.ok and "lexical fallback" in result.output
    assert not (tmp_path / "pid").exists()


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_gecersiz_sure_siniri_yapilandirmada_reddedilir(timeout):
    from fusion_cli.tools.symbol_query import SymbolQuerySettings

    with pytest.raises(ValueError):
        SymbolQuerySettings(timeout_s=timeout)


async def test_yinelenen_iptal_surec_temizligini_kesmez(tmp_path, monkeypatch):
    from fusion_cli.tools import lsp_client

    context = _source(tmp_path)
    started = asyncio.Event()
    release = asyncio.Event()
    close_process = lsp_client._close_process
    processes = []

    async def controlled_close(process):
        processes.append(process)
        started.set()
        await release.wait()
        await close_process(process)

    monkeypatch.setattr(lsp_client, "_close_process", controlled_close)
    registry = build_registry(
        symbol_query_enabled=True,
        symbol_query_settings=_settings(tmp_path, mode="hang", timeout=0.2),
    )
    task = asyncio.create_task(registry.execute("symbol_query", _args(), context))
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    try:
        _assert_stopped(tmp_path)
    finally:
        await close_process(processes[0])


async def test_lsp_sureci_gizli_ortam_degiskenlerini_almaz(tmp_path, monkeypatch):
    from dataclasses import replace

    context = replace(_source(tmp_path), hidden_env=frozenset({"FUSION_TEST_HIDDEN"}))
    monkeypatch.setenv("FUSION_TEST_HIDDEN", "yalniz-test-degeri")
    settings = _settings(tmp_path)
    server = tmp_path / "server.py"
    server.write_text(
        SERVER.replace(
            "mode = sys.argv[2]",
            'assert "FUSION_TEST_HIDDEN" not in os.environ\nmode = sys.argv[2]',
        ),
        encoding="utf-8",
    )
    registry = build_registry(symbol_query_enabled=True, symbol_query_settings=settings)
    result = await registry.execute("symbol_query", _args(), context)
    assert result.ok, result.output
    _assert_stopped(tmp_path)


async def test_kimlik_deposu_kaynak_uzantili_olsa_da_acilmaz(tmp_path):
    context = _source(tmp_path)
    private = tmp_path / ".ssh"
    private.mkdir()
    (private / "private.py").write_text("sample = 1\n", encoding="utf-8")
    registry = build_registry(symbol_query_enabled=True, symbol_query_settings=_settings(tmp_path))
    result = await registry.execute("symbol_query", _args() | {"path": ".ssh/private.py"}, context)
    assert not result.ok
    assert not (tmp_path / "pid").exists()


@pytest.mark.parametrize("component", ["leaf", "parent"])
async def test_kaynak_dogrulamadan_sonra_degistirilirse_yasak_bayt_sunucuya_gitmez(
    tmp_path, monkeypatch, component
):
    from fusion_cli.tools import symbol_query

    root = tmp_path / "project"
    root.mkdir()
    context = _source(root)
    source = root / "src" / "sample.py" if component == "parent" else root / "sample.py"
    source.parent.mkdir(exist_ok=True)
    source.write_text("def sample():\n    return 1\n", encoding="utf-8")
    excluded = tmp_path / "excluded"
    excluded.mkdir()
    marker = "FORBIDDEN_SOURCE_BYTES"
    (excluded / "sample.py").write_text(f"def sample():\n    return '{marker}'\n", encoding="utf-8")
    settings = _settings(root)
    original_filter = symbol_query.is_searchable_source
    was_changed = False

    def change_after_validation(path, search_root):
        nonlocal was_changed
        is_allowed = original_filter(path, search_root)
        if path == source and not was_changed:
            was_changed = True
            if component == "leaf":
                source.unlink()
                source.symlink_to(excluded / "sample.py")
            else:
                source.parent.rename(root / "original")
                source.parent.symlink_to(excluded, target_is_directory=True)
        return is_allowed

    monkeypatch.setattr(symbol_query, "is_searchable_source", change_after_validation)
    registry = build_registry(symbol_query_enabled=True, symbol_query_settings=settings)
    result = await registry.execute(
        "symbol_query", _args() | {"path": str(source.relative_to(root))}, context
    )
    assert was_changed and not result.ok
    calls = root / "calls"
    messages = (
        [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
    )
    opened_texts = [
        message["params"]["textDocument"]["text"]
        for message in messages
        if message.get("method") == "textDocument/didOpen"
    ]
    assert all(marker not in text for text in opened_texts)
    if (root / "pid").exists():
        _assert_stopped(root)


@pytest.mark.parametrize(
    "mode",
    [
        "push_missing_list",
        "push_missing_version",
        "push_wrong_version",
        "push_invalid_list",
        "pull_missing_kind",
        "pull_missing_items",
    ],
)
async def test_eksik_veya_guncelligi_bilinmeyen_tani_temiz_sonuc_sayilmaz(tmp_path, mode):
    context = _source(tmp_path)
    registry = build_registry(
        symbol_query_enabled=True, symbol_query_settings=_settings(tmp_path, mode=mode, timeout=0.5)
    )
    result = await registry.execute("symbol_query", _args("diagnostics"), context)
    assert not result.ok
    _assert_stopped(tmp_path)


@pytest.mark.parametrize("mode", ["push_empty", "pull_empty"])
async def test_acik_guncel_tam_bos_tani_gecerlidir(tmp_path, mode):
    context = _source(tmp_path)
    registry = build_registry(
        symbol_query_enabled=True, symbol_query_settings=_settings(tmp_path, mode=mode)
    )
    result = await registry.execute("symbol_query", _args("diagnostics"), context)
    assert result.ok, result.output
    assert result.structured["source"] == "lsp"
    _assert_stopped(tmp_path)


async def test_lexical_yedek_guvenli_belgeyi_yeniden_acmaz(tmp_path, monkeypatch):
    context = _source(tmp_path)
    source = tmp_path / "sample.py"
    real_open = Path.open
    later_reads = []

    def forbid_source_reopen(path, *args, **kwargs):
        if path == source:
            later_reads.append(path)
            raise AssertionError("Doğrulanmış kaynak ikinci kez açılmamalı.")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", forbid_source_reopen)
    result = await build_registry(symbol_query_enabled=True).execute(
        "symbol_query", _args(), context
    )
    assert result.ok and "sample.py:1" in result.output
    assert later_reads == []

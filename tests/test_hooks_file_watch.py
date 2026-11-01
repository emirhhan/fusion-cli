"""`ConfigChange` ve `FileChanged` kancaları (#90, #121, #126): oturum boyu dosya izleyicisi."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from fusion_cli.config import hooks as hook_config
from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core.hooks.decision import verdict_from_run
from fusion_cli.core.hooks.events import CLAUDE_ONLY_EVENTS, HookEvent, HookRun, HookSet
from fusion_cli.engines.hooks import watch
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.engines.hooks.watch import HookWatcher, ensure_watcher


def _script(tmp_path: Path, name: str, *, output: str = "", exit_code: int = 0) -> str:
    log = tmp_path / f"{name}.jsonl"
    script = tmp_path / f"{name}.py"
    script.write_text(
        "import json, os, sys\n"
        "data = json.load(sys.stdin)\n"
        "data['_env_file'] = os.environ.get('CLAUDE_ENV_FILE', '')\n"
        f"open(r'{log}', 'a').write(json.dumps(data) + '\\n')\n"
        f"print({output!r})\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    return f"{sys.executable} {script}"


def _payloads(tmp_path: Path, name: str) -> list[dict[str, object]]:
    log = tmp_path / f"{name}.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def _hooks(block: dict[str, object]) -> HookSet:
    commands, skipped = parse_hooks_block(block, source="kullanici", path=Path("settings.json"))
    assert not skipped
    return HookSet(commands)


class _Loader:
    def __init__(self, hooks: HookSet) -> None:
        self.hooks = hooks
        self.calls = 0

    def __call__(self) -> HookSet:
        self.calls += 1
        return self.hooks


def _session(tmp_path: Path, block: dict[str, object], **kwargs: object) -> HookSession:
    root = tmp_path / "proje"
    root.mkdir(exist_ok=True)
    return HookSession(root=root, loader=_Loader(_hooks(block)), home=tmp_path / "ev", **kwargs)  # type: ignore[arg-type]


def _no_managed(monkeypatch, tmp_path: Path) -> Path:
    managed = tmp_path / "yonetilen" / "managed-settings.json"
    monkeypatch.setattr(hook_config, "managed_settings_file", lambda: managed)
    monkeypatch.setattr(watch, "managed_settings_file", lambda: managed)
    return managed


def test_olaylar_artik_tetikleniyor():
    assert "ConfigChange" not in CLAUDE_ONLY_EVENTS
    assert "FileChanged" not in CLAUDE_ONLY_EVENTS


def test_proje_ayari_degisince_config_change_ve_tanimlar_tazelenir(tmp_path, monkeypatch):
    _no_managed(monkeypatch, tmp_path)
    command = _script(tmp_path, "config")
    session = _session(
        tmp_path,
        {
            "ConfigChange": [
                {"matcher": "project_settings", "hooks": [{"type": "command", "command": command}]}
            ]
        },
    )
    watcher = HookWatcher(session)
    watcher.prime()
    loader = session.loader
    assert isinstance(loader, _Loader)
    before = loader.calls
    settings = session.root / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text('{"hooks": {}}', encoding="utf-8")

    asyncio.run(watcher.check())

    (payload,) = _payloads(tmp_path, "config")
    assert payload["hook_event_name"] == "ConfigChange"
    assert payload["source"] == "project_settings"
    assert payload["file_path"] == str(settings)
    assert loader.calls == before + 1  # tur beklenmeden uygulandı (#121)
    assert not session.hooks_pinned


def test_cikis_iki_degisikligi_uygulamaz_tanimlar_sabit_kalir(tmp_path, monkeypatch):
    _no_managed(monkeypatch, tmp_path)
    command = _script(tmp_path, "config", exit_code=2)
    session = _session(
        tmp_path, {"ConfigChange": [{"hooks": [{"type": "command", "command": command}]}]}
    )
    watcher = HookWatcher(session)
    watcher.prime()
    loader = session.loader
    assert isinstance(loader, _Loader)
    local = session.root / ".claude" / "settings.local.json"
    local.parent.mkdir(parents=True)
    local.write_text("{}", encoding="utf-8")
    calls = loader.calls

    asyncio.run(watcher.check())
    session.refresh()

    assert _payloads(tmp_path, "config")[0]["source"] == "local_settings"
    assert session.hooks_pinned
    # Dosya engelden önceki haliyle (burada: yoktu) okunur; diskteki yeni içerik değil.
    assert session.pinned_settings == {local: None}
    assert loader.calls == calls + 1


def test_json_block_ve_mesaj_gosterilmez(tmp_path):
    session = _session(tmp_path, {})
    command = session.current().commands  # boş
    assert command == ()
    run = HookRun(
        command=_hooks(
            {"ConfigChange": [{"hooks": [{"type": "command", "command": "x"}]}]}
        ).commands[0],
        exit_code=0,
        stdout='{"decision": "block", "reason": "yönetici onayı", "systemMessage": "gizli"}',
    )
    verdict = verdict_from_run(HookEvent.CONFIG_CHANGE, run, "user_settings")
    assert verdict.blocked
    assert verdict.system_messages == ()


def test_policy_settings_engellenemez(tmp_path, monkeypatch):
    managed = _no_managed(monkeypatch, tmp_path)
    command = _script(tmp_path, "config", exit_code=2)
    session = _session(
        tmp_path, {"ConfigChange": [{"hooks": [{"type": "command", "command": command}]}]}
    )
    watcher = HookWatcher(session)
    watcher.prime()
    managed.parent.mkdir(parents=True)
    managed.write_text("{}", encoding="utf-8")

    asyncio.run(watcher.check())

    assert _payloads(tmp_path, "config")[0]["source"] == "policy_settings"
    assert not session.hooks_pinned


def test_beceri_dosyasi_skills_kaynagiyla(tmp_path, monkeypatch):
    _no_managed(monkeypatch, tmp_path)
    command = _script(tmp_path, "config")
    session = _session(
        tmp_path,
        {
            "ConfigChange": [
                {"matcher": "skills", "hooks": [{"type": "command", "command": command}]}
            ]
        },
    )
    skill = session.root / ".claude" / "skills" / "deneme" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: deneme\n---\n", encoding="utf-8")
    watcher = HookWatcher(session)
    watcher.prime()
    skill.write_text("---\nname: deneme\ndescription: yeni\n---\n", encoding="utf-8")

    asyncio.run(watcher.check())

    (payload,) = _payloads(tmp_path, "config")
    assert payload["source"] == "skills"
    assert payload["file_path"] == str(skill)


def test_file_changed_add_change_unlink_ve_env_file(tmp_path, monkeypatch):
    _no_managed(monkeypatch, tmp_path)
    command = _script(tmp_path, "dosya")
    session = _session(
        tmp_path,
        {
            "FileChanged": [
                {"matcher": ".envrc|.env", "hooks": [{"type": "command", "command": command}]}
            ]
        },
        transcript_dir=tmp_path / "dokum",
    )
    watcher = HookWatcher(session)
    watcher.prime()
    envrc = session.root / ".envrc"
    assert envrc in watcher.watched_files()
    assert session.root / ".env" in watcher.watched_files()

    envrc.write_text("export A=1\n", encoding="utf-8")
    asyncio.run(watcher.check())
    envrc.write_text("export A=12345\n", encoding="utf-8")
    asyncio.run(watcher.check())
    envrc.unlink()
    asyncio.run(watcher.check())

    payloads = _payloads(tmp_path, "dosya")
    assert [p["event"] for p in payloads] == ["add", "change", "unlink"]
    assert payloads[0]["hook_event_name"] == "FileChanged"
    assert payloads[0]["file_path"] == str(envrc)
    assert str(payloads[0]["_env_file"]).endswith("-env.sh")


def test_watch_paths_dinamik_listeyi_degistirir_bos_dizi_temizler(tmp_path, monkeypatch):
    _no_managed(monkeypatch, tmp_path)
    target = tmp_path / "izlenen.txt"
    target.write_text("a", encoding="utf-8")
    start = json.dumps(
        {"hookSpecificOutput": {"hookEventName": "SessionStart", "watchPaths": [str(target)]}}
    )
    clear = json.dumps({"hookSpecificOutput": {"hookEventName": "CwdChanged", "watchPaths": []}})
    dosya = _script(tmp_path, "dosya")
    session = _session(
        tmp_path,
        {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": _script(tmp_path, "s", output=start)}]}
            ],
            "CwdChanged": [
                {"hooks": [{"type": "command", "command": _script(tmp_path, "c", output=clear)}]}
            ],
            "FileChanged": [{"hooks": [{"type": "command", "command": dosya}]}],
        },
    )

    async def run() -> None:
        await session.start()
        watcher = watch.watcher_of(session)
        assert watcher is not None and watcher.task is not None
        watcher.prime()
        assert target in watcher.watched_files()
        target.write_text("bcd", encoding="utf-8")
        await watcher.check()
        session.defer_cwd_changed(session.root, session.root)
        await session.flush_deferred()
        assert session.watch_paths == ()
        session.ended = True

    asyncio.run(run())
    (payload,) = _payloads(tmp_path, "dosya")
    assert payload["file_path"] == str(target)
    assert payload["event"] == "change"


def test_ensure_watcher_tek_izleyici_kurar(tmp_path):
    session = _session(tmp_path, {})

    async def run() -> None:
        first = ensure_watcher(session, poll_s=0.01)
        second = ensure_watcher(session, poll_s=0.01)
        assert first is second
        await asyncio.sleep(0.03)
        session.ended = True
        assert first.task is not None
        await asyncio.wait_for(first.task, 1)

    asyncio.run(run())


def test_beceri_taramasi_sinirli_skill_md_once_node_modules_atlanir(tmp_path):
    # #121: büyük varlık ağacı SKILL.md'yi 500 sınırının dışına itmemeli; node_modules taranmaz.
    root = tmp_path / "skills"
    assets = root / "a-varliklar" / "resimler"
    assets.mkdir(parents=True)
    for index in range(watch.MAX_SKILL_FILES + 50):
        (assets / f"{index:04d}.png").write_bytes(b"")
    modules = root / "b-beceri" / "node_modules" / "paket"
    modules.mkdir(parents=True)
    (modules / "index.js").write_text("x", encoding="utf-8")
    skill = root / "z-beceri" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: z\n---\n", encoding="utf-8")

    found = watch._files_under(root, watch.MAX_SKILL_FILES)

    assert skill in found
    assert len(found) == watch.MAX_SKILL_FILES
    assert not any("node_modules" in path.parts for path in found)

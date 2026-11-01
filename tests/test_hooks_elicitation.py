"""`Elicitation`/`ElicitationResult` kancaları ve elicitation bildirimleri (#90, #125).

Claude Code: MCP sunucusu görev ortasında girdi isteyince `Elicitation` kancası soruyu
kullanıcıya göstermeden yanıtlayabilir (`action`/`content`, çıkış 2 = decline); kullanıcı
yanıtlayınca `ElicitationResult` yanıtı sunucuya gitmeden değiştirebilir. Ölçüldü (1 Kasım):
iki olay "Fusion bu olayı tetiklemiyor" diye atlanıyordu.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import types

from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core.hooks.events import HookSet
from fusion_cli.engines.hooks.elicitation import SessionElicitationHooks
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.mcp_bridge import elicitation_hooks
from fusion_cli.mcp_bridge.elicitation_hooks import (
    register_elicitation_hooks,
    with_elicitation_hooks,
)

FORM = types.ElicitRequestFormParams(
    message="Hangi ortam?",
    requestedSchema={"type": "object", "properties": {"env": {"type": "string"}}},
)


def _script(tmp_path: Path, name: str, output: object, exit_code: int = 0) -> str:
    script = tmp_path / f"{name}.py"
    body = json.dumps(output) if output is not None else ""
    script.write_text(
        "import sys, pathlib\n"
        f"pathlib.Path(r'{tmp_path / (name + '.json')}').write_text(sys.stdin.read())\n"
        f"print({body!r})\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    return f"{sys.executable} {script}"


def _session(tmp_path: Path, block: dict[str, object]) -> HookSession:
    commands, skipped = parse_hooks_block(block, source="kullanici", path=Path("settings.json"))
    assert not skipped
    return HookSession(root=tmp_path, loader=lambda: HookSet(commands))


def _entry(command: str, matcher: str = "") -> list[dict[str, object]]:
    return [{"matcher": matcher, "hooks": [{"type": "command", "command": command}]}]


def _output(event: str, action: str, **content: object) -> dict[str, object]:
    specific: dict[str, object] = {"hookEventName": event, "action": action}
    if content:
        specific["content"] = content
    return {"hookSpecificOutput": specific}


class _Asker:
    def __init__(self, result: types.ElicitResult) -> None:
        self.result = result
        self.asked = 0

    async def __call__(self, context: object, params: object) -> types.ElicitResult:
        self.asked += 1
        return self.result


def _call(session: HookSession, inner=None, params=FORM, server="db") -> types.ElicitResult:
    async def run() -> types.ElicitResult:
        register_elicitation_hooks(SessionElicitationHooks(session))
        try:
            result = await with_elicitation_hooks(server, inner)(None, params)
            await asyncio.sleep(0.5)  # arka plan bildirimleri
            return result
        finally:
            register_elicitation_hooks(None)

    return asyncio.run(run())


def _read(tmp_path: Path, name: str) -> dict[str, object]:
    return json.loads((tmp_path / f"{name}.json").read_text())


def test_elicitation_kancasi_soruyu_sormadan_yanitlar_girdi_claude_seklinde(tmp_path):
    hook = _script(tmp_path, "once", _output("Elicitation", "accept", env="prod"))
    session = _session(tmp_path, {"Elicitation": _entry(hook, matcher="db")})
    asker = _Asker(types.ElicitResult(action="decline"))
    result = _call(session, asker)
    assert result.action == "accept" and result.content == {"env": "prod"}
    assert asker.asked == 0
    girdi = _read(tmp_path, "once")
    assert girdi["hook_event_name"] == "Elicitation"
    assert girdi["mcp_server_name"] == "db"
    assert girdi["mode"] == "form" and girdi["message"] == "Hangi ortam?"
    assert girdi["requested_schema"]["properties"]["env"]["type"] == "string"


def test_cikis_iki_istegi_reddeder(tmp_path):
    hook = _script(tmp_path, "once", None, exit_code=2)
    session = _session(tmp_path, {"Elicitation": _entry(hook)})
    asker = _Asker(types.ElicitResult(action="accept", content={"env": "x"}))
    assert _call(session, asker).action == "decline"
    assert asker.asked == 0


def test_action_siz_cikti_yok_sayilir_soru_kullaniciya_gider(tmp_path):
    hook = _script(tmp_path, "once", {"hookSpecificOutput": {"hookEventName": "Elicitation"}})
    session = _session(tmp_path, {"Elicitation": _entry(hook)})
    asker = _Asker(types.ElicitResult(action="accept", content={"env": "dev"}))
    result = _call(session, asker)
    assert asker.asked == 1 and result.content == {"env": "dev"}


def test_eslesmeyen_sunucu_kancayi_calistirmaz(tmp_path):
    hook = _script(tmp_path, "once", _output("Elicitation", "decline"))
    session = _session(tmp_path, {"Elicitation": _entry(hook, matcher="github")})
    asker = _Asker(types.ElicitResult(action="accept", content={"env": "dev"}))
    assert _call(session, asker).action == "accept"
    assert not (tmp_path / "once.json").exists()


def test_result_kancasi_kullanici_yanitini_degistirir_bildirimler_calisir(tmp_path):
    after = _script(tmp_path, "sonra", _output("ElicitationResult", "decline"))
    notice = _script(tmp_path, "bildirim", None)
    session = _session(
        tmp_path,
        {
            "ElicitationResult": _entry(after),
            "Notification": _entry(notice, matcher="elicitation_dialog"),
        },
    )
    asker = _Asker(types.ElicitResult(action="accept", content={"env": "dev"}))
    result = _call(session, asker)
    assert asker.asked == 1 and result.action == "decline" and result.content is None
    girdi = _read(tmp_path, "sonra")
    assert girdi["hook_event_name"] == "ElicitationResult"
    assert girdi["action"] == "accept" and girdi["content"] == {"env": "dev"}
    bildirim = _read(tmp_path, "bildirim")
    assert bildirim["notification_type"] == "elicitation_dialog"
    assert bildirim["title"] == "Fusion" and "db" in bildirim["message"]


def test_url_kipi_alanlari(tmp_path):
    hook = _script(tmp_path, "once", _output("Elicitation", "cancel"))
    session = _session(tmp_path, {"Elicitation": _entry(hook)})
    params = types.ElicitRequestURLParams(
        message="Giriş yap", url="https://ornek.test/giris", elicitationId="e1"
    )
    assert _call(session, _Asker(types.ElicitResult(action="accept")), params).action == "cancel"
    girdi = _read(tmp_path, "once")
    assert girdi["mode"] == "url" and girdi["url"] == "https://ornek.test/giris"
    assert girdi["elicitation_id"] == "e1" and "requested_schema" not in girdi


def test_soracak_taraf_yoksa_cancel_result_kancasi_calismaz(tmp_path, monkeypatch):
    monkeypatch.setattr(
        elicitation_hooks, "_asking_callback", lambda server: elicitation_hooks._cancel
    )
    after = _script(tmp_path, "sonra", _output("ElicitationResult", "accept"))
    session = _session(tmp_path, {"ElicitationResult": _entry(after)})
    assert _call(session).action == "cancel"
    assert not (tmp_path / "sonra.json").exists()


def test_kanca_danismani_yoksa_ic_geri_cagirim_aynen_calisir():
    asker = _Asker(types.ElicitResult(action="accept", content={"env": "dev"}))
    result = asyncio.run(with_elicitation_hooks("db", asker)(None, FORM))
    assert result.action == "accept" and asker.asked == 1


def test_kok_tur_kanca_oturumunu_elicitation_danismani_olarak_kaydeder(tmp_path):
    from types import SimpleNamespace

    from fusion_cli.engines.agent.hook_services import bind_hook_services
    from fusion_cli.mcp_bridge.elicitation_hooks import registered_elicitation_hooks

    session = _session(tmp_path, {})
    deps = SimpleNamespace(hooks=session, publisher=None, config=None, base_registry=None)
    try:
        bind_hook_services(deps, run_agent=lambda *a, **k: None)
        assert isinstance(registered_elicitation_hooks(), SessionElicitationHooks)
    finally:
        register_elicitation_hooks(None)

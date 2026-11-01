"""SessionStart `initialUserMessage` (#111): istemsiz etkileşimsiz koşuda ilk istem olur."""

from __future__ import annotations

from fusion_cli.core.hooks.events import HookEvent

from .fakes import model_result
from .test_hooks_loop import _kanca, _oturum, _tur

_INITIAL = (
    "print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart',"
    " 'initialUserMessage': 'depoyu özetle'}}))\n"
)


async def test_istemsiz_koşuda_ilk_istem_kancadan_gelir(monkeypatch, tmp_path):
    session = _oturum(tmp_path, _kanca(tmp_path, HookEvent.SESSION_START, _INITIAL))
    outcome, provider, _p, _s = await _tur(
        monkeypatch, tmp_path, [model_result("özet")], session, task=""
    )
    assert outcome.ok
    user = [m.content for m in provider.seen_messages[0] if m.role == "user"]
    assert any("depoyu özetle" in (text or "") for text in user)


async def test_istem_varsa_initial_user_message_kullanilmaz(monkeypatch, tmp_path):
    session = _oturum(tmp_path, _kanca(tmp_path, HookEvent.SESSION_START, _INITIAL))
    _o, provider, _p, _s = await _tur(
        monkeypatch, tmp_path, [model_result("tamam")], session, task="testleri koş"
    )
    user = " ".join(m.content or "" for m in provider.seen_messages[0] if m.role == "user")
    assert "testleri koş" in user and "depoyu özetle" not in user


async def test_istemsiz_ve_mesajsiz_kosu_engellenir(monkeypatch, tmp_path):
    session = _oturum(tmp_path, _kanca(tmp_path, HookEvent.SESSION_START, "print('bağlam')\n"))
    outcome, provider, _p, _s = await _tur(monkeypatch, tmp_path, [], session, task="")
    assert not outcome.ok
    assert "boş" in outcome.final_text


def test_cli_istemsiz_kosuya_yalniz_sessionstart_kancasi_varken_izin_verir(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from fusion_cli.cli import app as cli_app
    from fusion_cli.config import trust

    from .fakes import make_config

    home = tmp_path / "ev"
    home.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(trust, "trust_store_file", lambda: home / "guven.json")
    monkeypatch.delenv("FUSION_HOOKS", raising=False)
    project = tmp_path / "proje"
    project.mkdir()
    config = make_config()
    assert cli_app._session_start_may_prompt(project, config) is False
    settings = home / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    hook = {"hooks": [{"type": "command", "command": "true"}]}
    settings.write_text(json.dumps({"hooks": {"SessionStart": [hook]}}))
    assert cli_app._session_start_may_prompt(project, config) is True

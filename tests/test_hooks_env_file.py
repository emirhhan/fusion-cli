"""`CLAUDE_ENV_FILE` (#109, #126): SessionStart/CwdChanged kancası `export` yazar, sonraki
her kabuk komutu dosyayı komuttan önce kabuk kodu olarak çalıştırır (Claude Code ile aynı).
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.hooks.events import HookEvent, HookSet
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.tools.shell import run_shell

from .fakes import model_result, tool_call
from .test_hooks_loop import _arac_mesajlari, _kanca, _tur

_YAZ_ENV = (
    "import os\n"
    "yol = os.environ.get('CLAUDE_ENV_FILE')\n"
    "open(yol, 'a', encoding='utf-8').write('export FUSION_KANCA_DEGER=merhaba\\n')\n"
)


def _oturum(tmp_path: Path, *commands) -> HookSession:
    return HookSession(
        root=tmp_path, loader=lambda: HookSet(tuple(commands)), transcript_dir=tmp_path / "dokum"
    )


def test_kabuk_env_dosyasini_komuttan_once_calistirir(tmp_path):
    env_file = tmp_path / "env.sh"
    env_file.write_text('export FUSION_KANCA_DEGER="a b"\n', encoding="utf-8")
    context = ToolContext(root=tmp_path, shell_env_files=[env_file])
    result = run_shell({"command": "echo deger=$FUSION_KANCA_DEGER"}, context)
    assert "deger=a b" in result.output


def test_env_dosyasi_yoksa_komut_degismez(tmp_path):
    context = ToolContext(root=tmp_path, shell_env_files=[tmp_path / "yok.sh"])
    result = run_shell({"command": "echo tamam"}, context)
    assert result.ok and "tamam" in result.output


async def test_sessionstart_kancasi_env_dosyasi_ile_kabuga_aktarir(monkeypatch, tmp_path):
    session = _oturum(tmp_path, _kanca(tmp_path, HookEvent.SESSION_START, _YAZ_ENV))
    kabuk = model_result(tool_calls=[tool_call("run_shell", command="echo d=$FUSION_KANCA_DEGER")])
    outcome, _, _, _ = await _tur(monkeypatch, tmp_path, [kabuk, model_result("ok")], session)
    assert "d=merhaba" in _arac_mesajlari(outcome)[0]


async def test_claude_env_file_yalniz_izinli_olaylara_verilir(monkeypatch, tmp_path):
    kayit = tmp_path / "kayit.jsonl"
    olcum = (
        "import os\n"
        f"open({str(kayit)!r}, 'a').write(data['hook_event_name'] + '='"
        " + str(bool(os.environ.get('CLAUDE_ENV_FILE'))) + '\\n')\n"
    )
    session = _oturum(
        tmp_path,
        _kanca(tmp_path, HookEvent.SESSION_START, olcum),
        _kanca(tmp_path, HookEvent.USER_PROMPT_SUBMIT, olcum),
    )
    await _tur(monkeypatch, tmp_path, [model_result("ok")], session)
    satirlar = sorted(kayit.read_text(encoding="utf-8").split())
    assert satirlar == ["SessionStart=True", "UserPromptSubmit=False"]

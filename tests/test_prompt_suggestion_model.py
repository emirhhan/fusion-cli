"""`-p --prompt-suggestions` (#289): öneri Claude gibi modelle tahmin edilir.

Claude Agent SDK: `prompt_suggestion` "a predicted next user prompt" taşır; tur hatayla
bittiyse ya da plan kipindeyse öneri yoktur. Fusion'da tahmin hakem rolünün modeliyle
(`config.judge`) yapılır; model ulaşılamazsa turun kanıtından üretilen takip önerisi kalır.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import print_run, sdk_suggestions
from fusion_cli.core.errors import ProviderError
from fusion_cli.core.events import FollowupsSuggested
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import next_prompt
from fusion_cli.engines.agent.next_prompt import parse_next_prompt, predict_next_prompt

from .fakes import make_config

runner = CliRunner()
STREAM = ["-p", "selam", "--output-format", "stream-json", "--verbose", "--prompt-suggestions"]


def test_tahmin_metni_temizlenir():
    assert parse_next_prompt('"Testleri çalıştır"\nikinci satır') == "Testleri çalıştır"
    assert parse_next_prompt("<think>x</think> Şimdi commit et") == "Şimdi commit et"
    assert parse_next_prompt("YOK") is None
    assert parse_next_prompt("   ") is None
    assert len(parse_next_prompt("a" * 900) or "") <= next_prompt.MAX_SUGGESTION_CHARS


def test_tahmin_hakem_modeline_konusmayi_verir(monkeypatch):
    requests = []

    class Provider:
        async def complete(self, request):
            requests.append(request)
            return SimpleNamespace(ok=True, text="Testleri çalıştır")

    monkeypatch.setattr(next_prompt, "build_provider", lambda *a, **k: Provider())
    history = [Message("user", "hesap modülünü yaz"), Message("assistant", "yazdım")]
    assert asyncio.run(predict_next_prompt(history, make_config())) == "Testleri çalıştır"
    content = requests[0].messages[0].content
    assert "hesap modülünü yaz" in content and "yazdım" in content


def test_saglayici_hatasinda_tahmin_yok(monkeypatch):
    def _boom(*_a, **_k):
        raise ProviderError("anahtar yok")

    monkeypatch.setattr(next_prompt, "build_provider", _boom)
    assert asyncio.run(predict_next_prompt([Message("user", "x")], make_config())) is None


def _run(monkeypatch, args, *, predicted, ok=True, items=(("a", "kanıt önerisi"),)):
    asked: list[object] = []

    async def _predict(history, config, **_kwargs):
        asked.append(history)
        return predicted

    async def _fake(task, config, **kwargs):
        for sink in kwargs["sinks"]:
            sink.handle(FollowupsSuggested(items))
        return SimpleNamespace(
            final_text="tamam" if ok else "",
            ok=ok,
            stop_reason=None,
            model_calls_made=1,
            hit_step_limit=False,
            messages=[Message("user", task), Message("assistant", "tamam")],
        )

    monkeypatch.setattr(sdk_suggestions, "predict_next_prompt", _predict)
    monkeypatch.setattr(print_run, "run_agent_task", _fake)
    return asked, runner.invoke(app_module.app, args)


def _suggestions(stdout: str) -> list[dict[str, object]]:
    rows = [json.loads(line) for line in stdout.splitlines() if line.startswith("{")]
    return [row for row in rows if row.get("type") == "prompt_suggestion"]


def test_model_tahmini_kanit_onerisinin_onune_gecer(monkeypatch):
    asked, result = _run(monkeypatch, STREAM, predicted="Şimdi testleri çalıştır")
    assert result.exit_code == 0, result.output
    assert [row["suggestion"] for row in _suggestions(result.stdout)] == ["Şimdi testleri çalıştır"]
    assert asked and asked[0][-1].content == "tamam"


def test_model_tahmin_vermezse_kanit_onerisi_kalir(monkeypatch):
    _asked, result = _run(monkeypatch, STREAM, predicted=None)
    assert [row["suggestion"] for row in _suggestions(result.stdout)] == ["kanıt önerisi"]


def test_hatali_turda_ve_plan_kipinde_oneri_yok(monkeypatch):
    asked, result = _run(monkeypatch, STREAM, predicted="x", ok=False)
    assert not _suggestions(result.stdout) and not asked
    asked, result = _run(monkeypatch, [*STREAM, "--permission-mode", "plan"], predicted="x")
    assert result.exit_code == 0, result.output
    assert not _suggestions(result.stdout) and not asked


def test_bayraksiz_model_cagrilmaz(monkeypatch):
    asked, result = _run(monkeypatch, STREAM[:-1], predicted="x")
    assert result.exit_code == 0 and not asked and not _suggestions(result.stdout)

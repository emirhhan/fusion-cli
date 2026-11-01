"""İnsan referanslarını yalnız sağlayıcı sınırında betikleyen çevrimdışı yardımcılar."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

from fusion_cli.core.model_capability import ToolSupport
from fusion_cli.core.types import CompletionRequest, Message
from fusion_cli.providers.web_session import WebProviderAdapter, WebSessionCredential, WebTurn
from tests.fakes import ScriptedProvider, model_result, tool_call


def _reference_actions(fixture: Path) -> list[dict[str, object]]:
    """Mevcut betik veya insan referans baytlarını aynı araç çağrısı yoluna bağla."""
    scripted = fixture / "reference.json"
    if scripted.is_file():
        return json.loads(scripted.read_text())
    actions = []
    for source in sorted((fixture / "reference").rglob("*.asset")):
        relative = source.relative_to(fixture / "reference").with_suffix("")
        path = relative.as_posix()
        if (fixture / "seed" / source.relative_to(fixture / "reference")).is_file():
            actions.append({"name": "read_file", "arguments": {"path": path}})
        seed = fixture / "seed" / source.relative_to(fixture / "reference")
        if seed.is_file() and seed.stat().st_size == 0:
            # Boş dosya tam-okuma kaydı üretmez; onaylı shell aracı baytları yazar.
            script = (
                f"from pathlib import Path; Path({path!r}).write_bytes({source.read_bytes()!r})"
            )
            actions.append(
                {
                    "name": "run_shell",
                    "arguments": {
                        "command": f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}",
                    },
                }
            )
        else:
            actions.append(
                {
                    "name": "write_file",
                    "arguments": {
                        "path": path,
                        "content": source.read_bytes().decode("utf-8"),
                    },
                }
            )
    return actions


async def reference_provider(fixture: Path) -> ScriptedProvider:
    actions = _reference_actions(fixture)
    results = []
    from dataclasses import replace

    for index, action in enumerate(actions):
        if "raw" in action:

            async def transport(credential, messages, model, raw=action["raw"]):
                return WebTurn(raw)

            provider = WebProviderAdapter(
                model="test",
                credential=WebSessionCredential(),
                transport=transport,
                tool_support=ToolSupport.EMULATED,
            )
            results.append(
                await provider.complete(
                    CompletionRequest(
                        messages=(Message("user", "İşi tamamla"),),
                        temperature=0,
                        max_tokens=1000,
                        timeout_s=1,
                    )
                )
            )
        elif "error" in action:
            results.append(model_result("", ok=False, error=action["error"]))
        else:
            results.append(
                model_result(
                    tool_calls=(
                        replace(
                            tool_call(action["name"], **action["arguments"]),
                            id=f"reference-{index}",
                        ),
                    )
                )
            )
    results.extend(model_result((fixture / "response.txt").read_text()) for _ in range(4))
    return ScriptedProvider(results)


async def countercontrol(task, execution, workspace, destination):
    """Doğru aday dosyalarıyla bile ihlal edilen süreç kontrolü kırmızı kalır."""
    import shutil
    from dataclasses import replace

    from evals.executor import AgentRunObservation, AgentTaskExecutor

    from fusion_cli.core.clock import SystemClock

    receipt = execution.runtime_receipt
    rows = [json.loads(line) for line in receipt.events_jsonl.splitlines()]
    blocked_event = "LessonOutcome" if task.id in {"T21", "T22", "T23"} else "ToolExecuted"
    changed = replace(
        receipt,
        events_jsonl="\n".join(json.dumps(row) for row in rows if row["event"] != blocked_event),
    )
    response = execution.output_text
    if task.id == "T04":
        response = "İş yapıldı."

    class BrokenRunner:
        async def run(self, request, *, root, **kwargs):
            for source in workspace.rglob("*"):
                if source.is_file() and not source.name.startswith("_"):
                    target = root / source.relative_to(workspace)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
            return AgentRunObservation(response, execution.model_calls, runtime_receipt=changed)

    result = await AgentTaskExecutor(
        BrokenRunner(), workspace_root=destination, clock=SystemClock()
    ).run(task)
    assert result.exit_code != 0, task.id


async def scripted_runner(task, tmp_path, monkeypatch, use_reference):
    from evals.profiles import EvalProfile, build_runner

    from fusion_cli.engines.agent import loop
    from tests.fakes import ScriptedProvider, make_config, model_result, patch_providers

    provider = (
        await reference_provider(
            Path(__file__).parents[1] / "evals/fixtures/fusion_research" / task.id
        )
        if use_reference
        else ScriptedProvider([model_result("İş tamamlanmadı; kanıt yok.")] * 6)
    )
    patch_providers(
        monkeypatch, loop, dict.fromkeys(("agent", "a", "b", "c", "hakem", "secilen"), provider)
    )
    import importlib
    import socket

    from tests.fakes import ScriptedProvider, model_result

    for name in (
        "learning",
        "narration",
        "liveness",
        "compaction",
        "goal_judge",
        "risk_classifier",
    ):
        module = importlib.import_module("fusion_cli.engines.agent." + name)
        utility = ScriptedProvider([model_result("Çıkarılacak yeni ders yok.")] * 20)
        patch_providers(
            monkeypatch,
            module,
            dict.fromkeys(("agent", "a", "b", "c", "hakem", "secilen"), utility),
        )

    def no_network(*args, **kwargs):
        raise AssertionError("Bu fixture ağ erişimi yapamaz")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    config = make_config(
        memory_dir=tmp_path / "memory",
        source=tmp_path / "config.yaml",
        runtime={"self_review": False, "lessons": False, "auto_web_fallback": False},
    )
    runner = build_runner(EvalProfile.FUSION_FULL, config, task=task)
    return runner

"""Missing local inventory can recover after a read-only retry."""

import json
from dataclasses import replace

import pytest

from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    RetrySafety,
    VerificationCheck,
    VerificationCheckKind,
)
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_runner import run_execution_plan
from tests.test_plan_repair import _deps
from tests.test_plan_runner import _step


@pytest.mark.parametrize(
    "safety,external,expected",
    [(RetrySafety.OBSERVE_FIRST, False, True), (RetrySafety.OBSERVE_FIRST, True, False)],
)
@pytest.mark.parametrize("manifest_exists", [False, True])
async def test_observed_missing_inventory_gets_only_local_repair(
    tmp_path, safety, external, expected, manifest_exists
):
    deps = _deps(tmp_path)
    if manifest_exists:
        (tmp_path / "ASSETS.json").write_text(json.dumps({"missing.txt": {"license": "CC0"}}))
    step = replace(
        _step("assets", expected_effects=("file:ASSETS.json",)),
        retry_safety=safety,
        attempts=3,
        allowed_tool_families=("files", "web", "browser") if external else ("files", "web"),
        success_criteria=("assets",),
        verification_checks=(
            VerificationCheck("assets", VerificationCheckKind.FILE_EXISTS, "ASSETS.json"),
        ),
    )
    calls = []

    async def agent(task, turn_deps, **kwargs):
        calls.append(kwargs["plan_mode"])
        if not kwargs["plan_mode"]:
            assert "download_file" in kwargs["allowed_tools"]
            assert "run_shell" not in kwargs["allowed_tools"]
            assert "browser_click" not in kwargs["allowed_tools"]
            for name, text in [
                ("sound.txt", "real asset"),
                (
                    "ASSETS.json",
                    json.dumps(
                        {
                            "sound.txt": {
                                "source_url": "https://example.com/source",
                                "license": "CC0",
                            }
                        }
                    ),
                ),
            ]:
                path = tmp_path / name
                if path.exists():
                    turn_deps.tool_context.changes.record(path)
                else:
                    turn_deps.tool_context.changes.record_created(path)
                path.write_text(text)
                turn_deps.tool_context.touched.add(path)
        return AgentOutcome(
            final_text="observed" if kwargs["plan_mode"] else "done",
            messages=[],
            model_calls_made=1,
        )

    result = await run_execution_plan(
        "assets",
        deps,
        agent,
        plan=ExecutionPlan("asset-repair", "assets", (step,)),
        self_review=False,
    )
    assert result.ok is expected
    assert calls == ([True, False] if expected else [True])


@pytest.mark.parametrize(
    "change",
    [
        {"retry_safety": RetrySafety.NEVER},
        {"revision": 1},
        {"expected_effects": ("git_push",)},
        {"expected_effects": ("file:../outside",)},
        {"allowed_tool_families": ("files", "shell")},
    ],
)
def test_inventory_repair_preserves_safety_boundaries(tmp_path, change):
    from fusion_cli.engines.agent.recovery import can_repair_local_inventory

    step = replace(
        _step("assets", expected_effects=("file:ASSETS.json",)),
        retry_safety=RetrySafety.OBSERVE_FIRST,
        verification_checks=(
            VerificationCheck("assets", VerificationCheckKind.FILE_EXISTS, "ASSETS.json"),
        ),
    )
    assert not can_repair_local_inventory(replace(step, **change), tmp_path)


async def test_son_kurtarma_hakki_gozlem_turuna_harcanmaz(tmp_path):
    """Gözlem turu YAZMAZ; son hakkı ona vermek adımı çaresiz kapatır.

    Ölçüldü (13 Eylül, Godot koşusu): `fetch-and-setup-assets` ilk denemede
    manifesti dosyasız yazıp düştü. Kalan tek kurtarma hakkı gözlem turuna gitti,
    model "bu aşamada dosya yazma ve indirme kapalı" diyerek yalnız planı anlattı
    ve adım hiç asset indirilmeden duraklatıldı. Tek hak, işi YAPABİLEN tura gider.
    """
    deps = _deps(tmp_path, recovery=1)
    step = replace(
        _step("assets", expected_effects=("file:ASSETS.json",)),
        retry_safety=RetrySafety.OBSERVE_FIRST,
        attempts=3,
        allowed_tool_families=("files", "web"),
        success_criteria=("assets",),
        verification_checks=(
            VerificationCheck("assets", VerificationCheckKind.FILE_EXISTS, "ASSETS.json"),
        ),
    )
    gozlem_mi: list[bool] = []

    async def agent(task, turn_deps, **kwargs):
        gozlem_mi.append(kwargs["plan_mode"])
        if not kwargs["plan_mode"]:
            for name, text in [
                ("sound.txt", "real asset"),
                (
                    "ASSETS.json",
                    json.dumps(
                        {
                            "sound.txt": {
                                "source_url": "https://example.com/source",
                                "license": "CC0",
                            }
                        }
                    ),
                ),
            ]:
                path = tmp_path / name
                turn_deps.tool_context.changes.record_created(path)
                path.write_text(text)
                turn_deps.tool_context.touched.add(path)
        return AgentOutcome(final_text="done", messages=[], model_calls_made=1)

    result = await run_execution_plan(
        "assets",
        deps,
        agent,
        plan=ExecutionPlan("asset-single-chance", "assets", (step,)),
        self_review=False,
    )

    assert gozlem_mi == [False]
    assert result.ok is True
    assert (tmp_path / "sound.txt").exists()


async def test_onarim_turunda_arsiv_acma_araci_aciktir(tmp_path):
    """İndirilen paket ZIP gelir; açamıyorsa indirmenin faydası yok.

    Ölçüldü (13 Eylül, Godot koşusu): onarım turunda `download_file` açıktı ama
    `extract_archive` kapalıydı; model bir python betiği yazıp `run_shell` denedi,
    o da kapsam dışıydı ve adım hiç asset açmadan düştü.
    """
    deps = _deps(tmp_path)
    (tmp_path / "ASSETS.json").write_text(json.dumps({"missing.txt": {"license": "CC0"}}))
    step = replace(
        _step("assets", expected_effects=("file:ASSETS.json",)),
        retry_safety=RetrySafety.OBSERVE_FIRST,
        attempts=3,
        allowed_tool_families=("files", "web"),
        success_criteria=("assets",),
        verification_checks=(
            VerificationCheck("assets", VerificationCheckKind.FILE_EXISTS, "ASSETS.json"),
        ),
    )
    araclar: list[set[str]] = []

    async def agent(task, turn_deps, **kwargs):
        araclar.append(set(kwargs["allowed_tools"]))
        if not kwargs["plan_mode"]:
            for name, text in [
                ("sound.txt", "real asset"),
                (
                    "ASSETS.json",
                    json.dumps(
                        {
                            "sound.txt": {
                                "source_url": "https://example.com/source",
                                "license": "CC0",
                            }
                        }
                    ),
                ),
            ]:
                path = tmp_path / name
                turn_deps.tool_context.changes.record_created(path)
                path.write_text(text)
                turn_deps.tool_context.touched.add(path)
        return AgentOutcome(final_text="done", messages=[], model_calls_made=1)

    await run_execution_plan(
        "assets",
        deps,
        agent,
        plan=ExecutionPlan("asset-repair-tools", "assets", (step,)),
        self_review=False,
    )

    yazan_tur = [item for item in araclar if "download_file" in item]
    assert yazan_tur, "onarım turu hiç açılmadı"
    assert "extract_archive" in yazan_tur[-1]

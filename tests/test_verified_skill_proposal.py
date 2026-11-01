"""Doğrulanmış rutin önerisi; kurulum ve sağlayıcı olmadan yerel kalıcılık."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest


def _routine():
    from fusion_cli.core.memory import RoutineSpec

    return RoutineSpec(
        routine_id="testleri-calistir",
        description="Testleri çalıştır.",
        input_schema='{"type":"object","properties":{"target":{"type":"string"}}}',
        preconditions=("python projesi",),
        checks=("pytest {target}",),
    )


@pytest.mark.asyncio
async def test_uc_ayri_dogrulanmis_kosum_oneri_olur_otomatik_kurulmaz(tmp_path):
    from fusion_cli.core.memory import RoutineObservation
    from fusion_cli.memory.skill_proposals import SkillProposalStore

    store = SkillProposalStore(tmp_path / "proposals.json")
    routine = _routine()
    for index in range(3):
        observation = RoutineObservation(
            run_id=f"run-{index}",
            success=True,
            verified=True,
            evidence_refs=(f"check:{index}",),
            source_split="development",
        )
        proposal = await store.observe(routine, observation)
    assert proposal is not None
    assert len(proposal.observations) == 3
    assert await store.list() == (proposal,)
    assert await store.get(proposal.id) == proposal
    assert await SkillProposalStore(tmp_path / "proposals.json").get(proposal.id) == proposal
    assert not list(tmp_path.rglob("SKILL.md"))
    assert json.loads(proposal.routine.input_schema) == json.loads(routine.input_schema)


@pytest.mark.asyncio
async def test_tekrar_basarisiz_altyapi_ve_kanitsiz_kosum_sayilmaz(tmp_path):
    from fusion_cli.core.memory import RoutineObservation
    from fusion_cli.core.repair_ledger import FailureOrigin
    from fusion_cli.memory.skill_proposals import SkillProposalStore

    store = SkillProposalStore(tmp_path / "proposals.json")
    good = RoutineObservation(
        run_id="one",
        success=True,
        verified=True,
        evidence_refs=("check:one",),
        source_split="development",
    )
    for observation in (
        good,
        good,
        replace(good, run_id="two", success=False),
        replace(good, run_id="three", failure_origin=FailureOrigin.INFRASTRUCTURE),
        replace(good, run_id="four", evidence_refs=()),
        replace(good, run_id="five", verified=False),
    ):
        assert await store.observe(_routine(), observation) is None
    assert await store.list() == ()


@pytest.mark.asyncio
async def test_normalize_rutin_kimligi_ve_splitler_birlesmez(tmp_path):
    from fusion_cli.core.memory import RoutineObservation
    from fusion_cli.memory.skill_proposals import SkillProposalStore

    store = SkillProposalStore(tmp_path / "proposals.json")
    routine = _routine()
    for index in range(3):
        observation = RoutineObservation(
            run_id=f"run-{index}",
            success=True,
            verified=True,
            evidence_refs=(f"check:{index}",),
            source_split="blind" if index == 2 else "development",
        )
        assert await store.observe(routine, observation) is None
    assert await store.list() == ()
    assert await store.list(source_split="blind") == ()


@pytest.mark.asyncio
async def test_ayni_kaniti_farkli_kosum_adiyla_saymaz(tmp_path):
    from fusion_cli.core.memory import RoutineObservation
    from fusion_cli.memory.skill_proposals import SkillProposalStore

    store = SkillProposalStore(tmp_path / "proposals.json")
    for index in range(3):
        observation = RoutineObservation(
            run_id=f"run-{index}", success=True, verified=True, evidence_refs=("check:replayed",)
        )
        assert await store.observe(_routine(), observation) is None
    assert await store.list() == ()


@pytest.mark.asyncio
async def test_bicim_farki_ayni_rutine_baglanir_ama_parametre_semasi_ayrilir(tmp_path):
    from fusion_cli.core.memory import RoutineObservation
    from fusion_cli.memory.skill_proposals import SkillProposalStore

    store = SkillProposalStore(tmp_path / "proposals.json")
    routine = _routine()
    for index in range(3):
        formatted = replace(
            routine,
            preconditions=("  python projesi  ",),
            checks=(" pytest {target} ",),
            input_schema=json.dumps(json.loads(routine.input_schema), indent=index),
        )
        proposal = await store.observe(
            formatted,
            RoutineObservation(
                run_id=f"run-{index}",
                success=True,
                verified=True,
                evidence_refs=(f"check:{index}",),
            ),
        )
    assert proposal is not None
    other = replace(
        routine, input_schema='{"type":"object","properties":{"target":{"type":"integer"}}}'
    )
    assert (
        await store.observe(
            other,
            RoutineObservation(
                run_id="other", success=True, verified=True, evidence_refs=("check:other",)
            ),
        )
        is None
    )
    assert len(await store.list()) == 1


@pytest.mark.asyncio
async def test_gecersiz_sema_ve_sir_kaydedilmez(tmp_path):
    from fusion_cli.core.memory import RoutineObservation
    from fusion_cli.memory.skill_proposals import SkillProposalError, SkillProposalStore

    store = SkillProposalStore(tmp_path / "proposals.json")
    observation = RoutineObservation(
        run_id="one", success=True, verified=True, evidence_refs=("check:one",)
    )
    for schema in ("{", "[]", '{"type":"array"}'):
        with pytest.raises(SkillProposalError):
            await store.observe(replace(_routine(), input_schema=schema), observation)
    with pytest.raises(SkillProposalError):
        await store.observe(
            replace(_routine(), description="password: synthetic-only"), observation
        )
    assert (
        await store.observe(
            _routine(), replace(observation, evidence_refs=("password: synthetic-only",))
        )
        is None
    )
    assert not (tmp_path / "proposals.json").exists()


@pytest.mark.asyncio
async def test_kosum_kimligi_boslukla_cogaltilemez(tmp_path):
    from fusion_cli.core.memory import RoutineObservation
    from fusion_cli.memory.skill_proposals import SkillProposalStore

    store = SkillProposalStore(tmp_path / "proposals.json")
    for index, run_id in enumerate(("one", " one", "one ")):
        assert (
            await store.observe(
                _routine(),
                RoutineObservation(
                    run_id=run_id, success=True, verified=True, evidence_refs=(f"check:{index}",)
                ),
            )
            is None
        )
    assert await store.list() == ()


async def _stored_payload(path):
    from fusion_cli.core.memory import RoutineObservation
    from fusion_cli.memory.skill_proposals import SkillProposalStore

    store = SkillProposalStore(path)
    for index in range(3):
        await store.observe(
            _routine(),
            RoutineObservation(
                run_id=f"run-{index}",
                success=True,
                verified=True,
                evidence_refs=(f"check:{index}",),
            ),
        )
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        "same_reference",
        "spaced_reference",
        "duplicated_reference",
        "spaced_run_id",
        "blank_reference",
    ],
)
async def test_fix1_kalici_tekrarlar_uc_bagimsiz_kanit_sayilmaz(tmp_path, mode):
    from fusion_cli.memory.skill_proposals import SkillProposalError, SkillProposalStore

    path = tmp_path / "proposals.json"
    payload = await _stored_payload(path)
    observations = payload["proposals"][0]["observations"]
    for index, observation in enumerate(observations):
        if mode == "spaced_run_id":
            observation["run_id"] = "run-zero" + " " * index
        elif mode == "blank_reference":
            observation["evidence_refs"] = ["  "]
        else:
            reference = "check:zero" + (" " * index if mode == "spaced_reference" else "")
            observation["evidence_refs"] = [reference] * (
                index + 1 if mode == "duplicated_reference" else 1
            )
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SkillProposalError):
        await SkillProposalStore(path).list()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["preconditions", "checks"])
@pytest.mark.parametrize("malformed", [[42], "tek metin", None, {"kontrol": "metin"}])
async def test_fix1_kalici_rutin_metin_listesi_sinirini_dogrular(tmp_path, field, malformed):
    from fusion_cli.memory.skill_proposals import SkillProposalError, SkillProposalStore

    path = tmp_path / "proposals.json"
    payload = await _stored_payload(path)
    payload["proposals"][0]["routine"][field] = malformed
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SkillProposalError):
        await SkillProposalStore(path).list()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["preconditions", "checks"])
async def test_fix1_kalici_gecerli_metin_listesi_ve_kanit_normalizasyonu_korunur(tmp_path, field):
    from fusion_cli.memory.skill_proposals import SkillProposalStore

    path = tmp_path / "proposals.json"
    payload = await _stored_payload(path)
    proposal = payload["proposals"][0]
    original = proposal["routine"][field][0]
    proposal["routine"][field] = [f" {original} ", original]
    for index, observation in enumerate(proposal["observations"]):
        observation["run_id"] = f" run-{index} "
        observation["evidence_refs"] = [f" check:{index} ", f"check:{index}", " shared:check "]
    path.write_text(json.dumps(payload), encoding="utf-8")
    published = await SkillProposalStore(path).list()
    assert len(published) == 1
    assert getattr(published[0].routine, field) == (original,)
    assert tuple(item.run_id for item in published[0].observations) == ("run-0", "run-1", "run-2")
    assert tuple(item.evidence_refs for item in published[0].observations) == tuple(
        (f"check:{index}", "shared:check") for index in range(3)
    )


@pytest.mark.asyncio
async def test_fix1_yeniden_okunan_kanit_yazmada_da_ayni_normalizasyondan_gecer(tmp_path):
    from fusion_cli.core.memory import RoutineObservation
    from fusion_cli.memory.skill_proposals import SkillProposalStore

    path = tmp_path / "proposals.json"
    payload = await _stored_payload(path)
    proposal = payload["proposals"][0]
    proposal["observations"] = proposal["observations"][:1]
    proposal["observations"][0]["run_id"] = " run-0 "
    proposal["observations"][0]["evidence_refs"] = [" check:0 ", "check:0"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    store = SkillProposalStore(path)
    for run_id, reference in (("run-0", "check:new"), ("new-run", "check:0")):
        assert (
            await store.observe(
                _routine(),
                RoutineObservation(
                    run_id=run_id,
                    success=True,
                    verified=True,
                    evidence_refs=(reference,),
                ),
            )
            is None
        )
    assert await store.list() == ()
    stored = json.loads(path.read_text(encoding="utf-8"))["proposals"][0]["observations"]
    assert len(stored) == 1
    assert stored[0]["run_id"] == "run-0" and stored[0]["evidence_refs"] == ["check:0"]


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", [None, 42, ["run-id"]])
async def test_fix1_kalici_kosum_kimligi_metin_olmali(tmp_path, malformed):
    from fusion_cli.memory.skill_proposals import SkillProposalError, SkillProposalStore

    path = tmp_path / "proposals.json"
    payload = await _stored_payload(path)
    payload["proposals"][0]["observations"][0]["run_id"] = malformed
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SkillProposalError):
        await SkillProposalStore(path).list()

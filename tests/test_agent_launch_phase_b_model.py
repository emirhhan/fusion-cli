"""Ajan model önceliği, FORCE, aile ve yapılandırılmış izin listesi."""

from __future__ import annotations

import dataclasses

import pytest

from fusion_cli.config.agent_launch_settings import AgentLaunchConfig
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.team import GENERIC_PERSONA
from fusion_cli.engines.agent.team_settings import child_model

PARENT = ModelSpec("üst", "anthropic/claude-opus-4-6[1m]")
HAIKU = ModelSpec("haiku", "anthropic/claude-haiku-4-5")
SONNET = ModelSpec("sonnet", "anthropic/claude-sonnet-4-6")


@pytest.mark.parametrize(
    ("frontmatter", "invocation", "forced", "expected"),
    (
        ("opus", "sonnet", False, SONNET.model),
        ("sonnet", "", False, SONNET.model),
        ("", "", False, HAIKU.model),
        ("sonnet", "sonnet", True, HAIKU.model),
    ),
)
def test_model_onceligi_cagri_tanim_ortam_ust_ve_force(frontmatter, invocation, forced, expected):
    launch = AgentLaunchConfig(subagent_model="haiku", force_subagent_model=forced)
    persona = dataclasses.replace(GENERIC_PERSONA, model=frontmatter)
    chosen = child_model(
        persona, PARENT, candidates=(HAIKU, SONNET), launch=launch, invocation_model=invocation
    )
    assert chosen is not None and chosen.model == expected


def test_ortam_aliasi_ayni_ailede_ustun_surumunu_devralmaz():
    parent = ModelSpec("üst", "anthropic/claude-haiku-old")
    chosen = child_model(
        GENERIC_PERSONA,
        parent,
        candidates=(HAIKU,),
        launch=AgentLaunchConfig(subagent_model="haiku"),
    )
    assert chosen is not None and chosen.model == HAIKU.model


def test_force_tek_basina_ustun_tam_kimligini_korur():
    chosen = child_model(
        dataclasses.replace(GENERIC_PERSONA, model="haiku"),
        PARENT,
        candidates=(HAIKU,),
        launch=AgentLaunchConfig(force_subagent_model=True),
    )
    assert chosen is PARENT


@pytest.mark.parametrize("provider", ("anthropic", "mantle", "bedrock"))
def test_yasak_alias_yalniz_desteklenen_saglayicida_izinli_aile_surumune_gecer(provider):
    allowed = ModelSpec("eski", "anthropic/claude-haiku-3-5")
    launch = AgentLaunchConfig(available_models=("claude-haiku-3-5",), provider=provider)
    chosen = child_model(
        dataclasses.replace(GENERIC_PERSONA, model="haiku"),
        PARENT,
        candidates=(HAIKU, allowed),
        launch=launch,
    )
    assert chosen is not None
    assert chosen.model == (PARENT.model if provider == "bedrock" else allowed.model)


def test_yasak_tam_model_ortam_tercihine_sonra_uste_duser():
    persona = dataclasses.replace(GENERIC_PERSONA, model="anthropic/claude-sonnet-blocked")
    launch = AgentLaunchConfig(subagent_model="haiku", available_models=("haiku",))
    chosen = child_model(persona, PARENT, candidates=(HAIKU,), launch=launch)
    assert chosen is not None and chosen.model == HAIKU.model
    chosen = child_model(
        persona, PARENT, candidates=(HAIKU,), launch=dataclasses.replace(launch, subagent_model="")
    )
    assert chosen is PARENT


def test_bedrock_cozulemeyen_ustte_opus_istisnasi_ozel_eslemeyi_ezmez():
    parent = ModelSpec("üst", "bedrock/arn:aws:bedrock:profile:custom")
    persona = dataclasses.replace(GENERIC_PERSONA, model="opus")
    launch = AgentLaunchConfig(provider="bedrock", unresolved_parent_family=True)
    assert child_model(persona, parent, launch=launch) is parent
    launch = dataclasses.replace(launch, model_aliases=(("opus", "bedrock/explicit-profile"),))
    chosen = child_model(persona, parent, launch=launch)
    assert chosen is not None and chosen.model == "bedrock/explicit-profile"

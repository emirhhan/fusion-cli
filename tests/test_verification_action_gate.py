from types import SimpleNamespace

from fusion_cli.engines.agent.loop import _never_acted, _State


def _execution():
    return SimpleNamespace(
        complex_task=True,
        offer_tools=True,
        max_evidence_reprompts=0,
    )


def test_normal_internal_tur_aracsiz_bitebilir():
    state = _State(internal=True)
    assert _never_acted(state, _execution()) is False


def test_blocking_correction_local_mutation_ister():
    state = _State(
        internal=True,
        require_local_mutation=True,
    )
    assert _never_acted(state, _execution()) is True


def test_blocking_correction_read_only_ile_yetinemaz():
    state = _State(
        internal=True,
        require_local_mutation=True,
    )
    state.tool_calls_made = 1

    assert _never_acted(state, _execution()) is True


def test_blocking_correction_mutation_sonrasi_kapanabilir():
    state = _State(
        internal=True,
        require_local_mutation=True,
    )
    state.tool_calls_made = 2
    state.mutating_tool_calls_made = 1

    assert _never_acted(state, _execution()) is False


def test_blocking_correction_ilk_bos_deneme_sonrasi_bir_sans_daha_alir():
    state = _State(
        internal=True,
        require_local_mutation=True,
    )
    state.never_acted_prompts = 1

    assert _never_acted(state, _execution()) is True


def test_blocking_correction_iki_bos_denemeden_sonra_donguye_girmez():
    state = _State(
        internal=True,
        require_local_mutation=True,
    )
    state.never_acted_prompts = 2

    assert _never_acted(state, _execution()) is False

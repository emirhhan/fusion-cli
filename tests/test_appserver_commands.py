"""Slash komutlarının uygulama protokolü köprüsü."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.appserver.commands import command_choices, list_commands, run_command
from fusion_cli.cli.repl import model_flows
from fusion_cli.cli.repl.commands import SlashCommand, build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.credentials import FernetSecretStore
from fusion_cli.config.loader import load_config
from fusion_cli.memory.factory import null_memory
from fusion_cli.providers.catalog import CatalogEntry
from fusion_cli.ui import messages


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    """Gerçek kademeleri olan, yazmaları geçici dizine giden oturum."""
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return ReplState(
        config=load_config(source),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
    )


def test_liste_kayit_defteriyle_birebir_ortusur() -> None:
    registry = build_registry()
    rows = list_commands(registry)
    assert len(rows) == len(registry.all())
    assert {row["ad"] for row in rows} == {command.name for command in registry.all()}
    assert all(row["aciklama"] for row in rows)


def test_liste_grup_ve_kullanim_tasir() -> None:
    rows = {row["ad"]: row for row in list_commands(build_registry())}
    assert rows["skills"]["grup"] == "Bilgi"
    assert rows["skills"]["kullanim"] == "[arama]"


def test_etkilesimsiz_komut_calisir_ve_metin_doner(state: ReplState) -> None:
    result = run_command(build_registry(), state, "thinking", "")
    assert result["ok"] is True
    assert isinstance(result["metin"], str)


def test_bilinmeyen_komut_ham_girdiyi_yansitmaz(state: ReplState) -> None:
    secret = "SIR-BILINMEYEN-42"
    result = run_command(build_registry(), state, secret, "ARGUMAN-SIRRI")
    assert result == {"ok": False, "metin": messages.APP_COMMAND_UNKNOWN}
    assert secret not in result["metin"]
    assert "ARGUMAN-SIRRI" not in result["metin"]


def test_isleyici_istisnasi_ayrintisini_yansitmaz(state: ReplState) -> None:
    secret = "SIR-ISTISNA-99"
    registry = build_registry()

    def explode(_state: ReplState, _argument: str) -> str:
        raise RuntimeError(f"altyapi ayrintisi: {secret}")

    registry.register(SlashCommand("patla", "test", explode))
    result = run_command(registry, state, "patla", secret)
    assert result == {"ok": False, "metin": messages.APP_COMMAND_FAILED}
    assert secret not in result["metin"]


@pytest.mark.parametrize(
    ("name", "argument", "step", "kind"),
    (
        ("level", "", "kademe", "secim"),
        ("mode", "", "profil", "secim"),
        ("effort", "", "yogunluk", "secim"),
        ("model", "", "model_eylemi", "secim"),
        ("provider", "", "saglayici", "secim"),
        ("development", "", "kaynak", "secim"),
        ("profiles", "edit", "profil", "secim"),
        ("providers", "add", "saglayici", "secim"),
    ),
)
def test_sekiz_secici_yuzeyi_tam_telli_yuk_dondurur(
    state: ReplState, name: str, argument: str, step: str, kind: str
) -> None:
    payload = command_choices(state, name, argument)
    assert payload is not None
    assert payload["adim"] == step
    assert payload["tur"] == kind
    assert set(payload) == {
        "adim",
        "tur",
        "baslik",
        "secenekler",
        "devam",
        "serbest_metin",
    }
    assert payload["baslik"] and payload["secenekler"]
    assert all(set(choice) == {"deger", "etiket", "aciklama"} for choice in payload["secenekler"])
    assert payload["devam"]["komut"] == name


def test_secici_acmayan_komut_none_doner(state: ReplState) -> None:
    assert command_choices(state, "thinking") is None


def test_model_secenekleri_isleyicinin_kabul_ettigi_guncel_eylemlerdir(
    state: ReplState,
) -> None:
    payload = command_choices(state, "model")
    assert payload is not None
    values = {choice["deger"] for choice in payload["secenekler"]}
    assert f"agent {state.config.agent.model}" in values
    assert f"judge {state.config.judge.model}" in values
    assert all(
        f"cand {candidate.name} {candidate.model}" in values
        for candidate in state.config.candidates
    )
    result = run_command(build_registry(), state, "model", f"agent {state.config.agent.model}")
    assert result["ok"] is True


def test_etkilesimli_komutlar_terminal_girdisine_inmez(
    state: ReplState, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("terminal girdisi çağrıldı")

    monkeypatch.setattr("builtins.input", forbidden)
    monkeypatch.setattr("getpass.getpass", forbidden)
    monkeypatch.setattr("fusion_cli.ui.picker._pick_interactive", forbidden)
    registry = build_registry()
    cases = (
        ("level", ""),
        ("mode", ""),
        ("effort", ""),
        ("model", ""),
        ("provider", ""),
        ("development", ""),
        ("profiles", "edit"),
        ("providers", "add"),
        ("development", "kaynak custom"),
        ("providers", "add openrouter"),
    )
    for name, argument in cases:
        result = run_command(registry, state, name, argument)
        assert result["ok"] is True and "secici" in result


def test_provider_secimi_mevcut_akisla_uygulanir(state: ReplState) -> None:
    result = run_command(build_registry(), state, "provider", "nvidia")
    assert result["ok"] is True
    assert state.config.runtime.provider == "nvidia"


def test_development_kaynak_ve_model_adimlari_uygulanir(
    state: ReplState, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_id = "openrouter/ornek/model:free"
    monkeypatch.setattr(
        model_flows.catalog,
        "fetch_openrouter_free",
        lambda: (CatalogEntry(model_id, "openrouter", 128_000),),
    )
    payload = command_choices(state, "development", "kaynak openrouter-free")
    assert payload is not None and payload["adim"] == "model"
    assert [choice["deger"] for choice in payload["secenekler"]] == [model_id]
    result = run_command(
        build_registry(), state, "development", f"uygula openrouter-free {model_id}"
    )
    assert result["ok"] is True
    assert state.config.agent.model == model_id
    assert state.config.judge.model == model_id
    assert {candidate.model for candidate in state.config.candidates} == {model_id}


def test_development_custom_serbest_metin_adimi_uygulanir(state: ReplState) -> None:
    payload = command_choices(state, "development", "kaynak custom")
    assert payload is not None and payload["tur"] == "metin"
    assert payload["serbest_metin"] == {
        "gizli": False,
        "yer_tutucu": "<sağlayıcı>/<model>",
    }
    model_id = "ollama/qwen2.5-coder:7b"
    result = run_command(build_registry(), state, "development", f"uygula custom {model_id}")
    assert result["ok"] is True
    assert state.config.agent.model == model_id


def test_profiles_tier_ve_aday_adimlari_uygulanir(state: ReplState) -> None:
    tier = state.config.tier_by_name("medium")
    assert tier is not None
    target = tier.candidates[-1]
    payload = command_choices(state, "profiles", "edit medium")
    assert payload is not None and payload["adim"] == "aday"
    assert target.name in {choice["deger"] for choice in payload["secenekler"]}
    result = run_command(build_registry(), state, "profiles", f"edit medium {target.name}")
    assert result["ok"] is True
    assert state.config.agent.name == target.name


def test_providers_add_sirri_yansitmadan_kaydeder(state: ReplState, tmp_path: Path) -> None:
    payload = command_choices(state, "providers", "add openrouter")
    assert payload is not None and payload["tur"] == "gizli_metin"
    assert payload["serbest_metin"] == {"gizli": True, "yer_tutucu": "API anahtarı"}
    secret = "SIR-PROVIDER-123"
    store = FernetSecretStore(tmp_path / "credentials.enc", secret_key="test-master")
    result = run_command(
        build_registry(), state, "providers", f"add openrouter {secret}", secret_store=store
    )
    assert result["ok"] is True
    assert secret not in repr(result)
    assert store.get("OPENROUTER_API_KEY") == secret


def test_secret_store_hatasi_sirri_ve_istisnayi_yansitmaz(
    state: ReplState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = "SIR-STORE-HATA"
    store = FernetSecretStore(tmp_path / "credentials.enc", secret_key="test-master")

    def explode(_env_name: str, value: str) -> None:
        raise RuntimeError(f"depo ayrintisi {value}")

    monkeypatch.setattr(store, "set", explode)
    result = run_command(
        build_registry(), state, "providers", f"add openrouter {secret}", secret_store=store
    )
    assert result == {"ok": False, "metin": messages.APP_COMMAND_FAILED}
    assert secret not in result["metin"]


def test_tamamlanmamis_secim_run_command_ile_yapisal_doner(state: ReplState) -> None:
    result = run_command(build_registry(), state, "development", "kaynak custom")
    assert result["ok"] is True and result["metin"] == ""
    assert result["secici"]["tur"] == "metin"


def test_secim_uretici_hatasi_guvenli_sonuca_cevrilir(
    state: ReplState, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode() -> tuple[CatalogEntry, ...]:
        raise RuntimeError("AG-AYRINTISI-SIZMAMALI")

    monkeypatch.setattr(model_flows.catalog, "fetch_openrouter_free", explode)
    result = run_command(build_registry(), state, "development", "kaynak openrouter-free")
    assert result == {"ok": False, "metin": messages.APP_COMMAND_FAILED}
    assert "AG-AYRINTISI" not in result["metin"]

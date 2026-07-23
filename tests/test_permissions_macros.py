"""İzin listesi, makrolar ve oturum içi model değişimi."""

from __future__ import annotations

import json

import pytest

from fusion_cli.cli.repl import macros
from fusion_cli.config import model_select
from fusion_cli.config.permissions import is_allowed, load_allowed_commands
from fusion_cli.core.errors import ConfigError

from .fakes import make_config

# --- İzin listesi -------------------------------------------------------------- #


def _yaz(tmp_path, data):
    path = tmp_path / ".claude"
    path.mkdir(exist_ok=True)
    (path / "settings.local.json").write_text(json.dumps(data), encoding="utf-8")


def test_bash_izinleri_okunur(tmp_path):
    _yaz(tmp_path, {"permissions": {"allow": ["Bash(pytest -q)", "Bash(git status *)"]}})

    assert load_allowed_commands(tmp_path) == {"pytest -q", "git status *"}


def test_bash_disi_izinler_atlanir(tmp_path):
    _yaz(tmp_path, {"permissions": {"allow": ["Read", "Edit(.claude)", "Bash(ls)"]}})

    assert load_allowed_commands(tmp_path) == {"ls"}


def test_dosya_yoksa_bos_liste(tmp_path):
    assert load_allowed_commands(tmp_path) == frozenset()


def test_bozuk_json_bos_liste(tmp_path):
    path = tmp_path / ".claude"
    path.mkdir()
    (path / "settings.local.json").write_text("{bozuk", encoding="utf-8")

    assert load_allowed_commands(tmp_path) == frozenset()


def test_beklenmedik_yapi_bos_liste(tmp_path):
    _yaz(tmp_path, {"permissions": "yanlis-tip"})

    assert load_allowed_commands(tmp_path) == frozenset()


def test_birebir_eslesme():
    assert is_allowed("pytest -q", frozenset({"pytest -q"}))
    assert not is_allowed("pytest -q --verbose", frozenset({"pytest -q"}))


def test_yildizla_on_ek_eslesmesi():
    allowed = frozenset({"git status *"})

    assert is_allowed("git status --short", allowed)
    assert not is_allowed("git push", allowed)


def test_yildizsiz_kalip_kismi_eslesmez():
    """Dar tutulur: 'rm' izni 'rm -rf /' anlamına gelmemeli."""
    assert not is_allowed("rm -rf /", frozenset({"rm"}))


# --- Onay politikası ile birlikte ---------------------------------------------- #


async def test_izinli_komut_security_modda_sorulmaz():
    from fusion_cli.core.tools import Tool
    from fusion_cli.engines.agent.approval import (
        ApprovalMode,
        Decision,
        build_policy,
        build_request,
    )

    from .fakes import AlwaysReject

    tool = Tool(
        name="run_shell", description="", parameters={}, run=lambda a, c: None, mutating=True
    )
    policy = build_policy(ApprovalMode.SECURITY, AlwaysReject())

    karar = await policy.decide(
        build_request(tool, {"command": "pytest -q"}, frozenset({"pytest -q"}))
    )

    assert karar is Decision.ALLOW


async def test_izinli_olsa_bile_yikici_komut_sorulur():
    """İzin listesi yıkıcı komutlar için istisna sağlamaz."""
    from fusion_cli.core.tools import Tool
    from fusion_cli.engines.agent.approval import (
        ApprovalMode,
        Decision,
        build_policy,
        build_request,
    )

    from .fakes import AlwaysReject

    tool = Tool(
        name="run_shell", description="", parameters={}, run=lambda a, c: None, mutating=True
    )
    policy = build_policy(ApprovalMode.SECURITY, AlwaysReject())

    karar = await policy.decide(
        build_request(tool, {"command": "rm -rf build"}, frozenset({"rm -rf build"}))
    )

    assert karar is Decision.DENIED


# --- Makrolar ------------------------------------------------------------------- #


def test_argumansiz_makro_varsayilan_gorevi_kullanir():
    macro = macros.get("bug")

    assert macro is not None
    assert "hata bul" in macro.build("").lower()


def test_argumanli_makro_sablonu_doldurur():
    macro = macros.get("bug")

    assert macro is not None
    assert "giris dogrulamasi" in macro.build("giris dogrulamasi")


def test_arguman_zorunlu_makrolar_isaretli():
    assert macros.get("grill-me").argument_required
    assert macros.get("browser").argument_required
    assert not macros.get("bug").argument_required


def test_hedef_kipi_prompt_uretir():
    assert "pes etmek yok" in macros.mode_prompt(macros.Mode.GOAL).lower()


def test_mulakat_kipi_prompt_uretir():
    assert "ask_user" in macros.mode_prompt(macros.Mode.GRILL)


def test_kipsiz_makro_prompt_uretmez():
    assert macros.mode_prompt(macros.Mode.NONE) == ""


def test_tum_makrolar_gorev_ya_da_sablon_tasir():
    for name, macro in macros.MACROS.items():
        assert macro.task or macro.template, name


# --- Oturum içi model değişimi -------------------------------------------------- #


def test_agent_modeli_degistirilir():
    config = make_config()

    updated = model_select.set_agent_model(config, "openrouter/a/b:free")

    assert updated.agent.model == "openrouter/a/b:free"
    assert config.agent.model == "sahte/agent"  # kaynak değişmedi


def test_aday_sirasiyla_degistirilebilir():
    updated = model_select.set_candidate_model(make_config(), "2", "ollama/x:7b")

    assert updated.candidates[1].model == "ollama/x:7b"


def test_aday_adiyla_degistirilebilir():
    updated = model_select.set_candidate_model(make_config(), "c", "ollama/x:7b")

    assert updated.candidate_by_name("c").model == "ollama/x:7b"


def test_aday_eklenir():
    updated = model_select.add_candidate(make_config(), "yeni", "ollama/q:7b", ("code",))

    assert len(updated.candidates) == 4
    assert updated.candidate_by_name("yeni").tags == ("code",)


def test_ayni_adla_aday_eklenemez():
    with pytest.raises(ConfigError, match="zaten var"):
        model_select.add_candidate(make_config(), "a", "ollama/q:7b")


def test_aday_cikarilir():
    assert len(model_select.remove_candidate(make_config(), "b").candidates) == 2


def test_son_aday_cikarilamaz():
    config = model_select.remove_candidate(make_config(), "b")
    config = model_select.remove_candidate(config, "c")

    with pytest.raises(ConfigError, match="En az bir aday"):
        model_select.remove_candidate(config, "a")


def test_olmayan_aday_hata_verir():
    with pytest.raises(ConfigError, match="adlı aday yok"):
        model_select.set_candidate_model(make_config(), "olmayan", "a/b")


def test_sira_disi_index_hata_verir():
    with pytest.raises(ConfigError, match="aralık dışı"):
        model_select.set_candidate_model(make_config(), "99", "a/b")


@pytest.mark.parametrize("gecersiz", ["bozuk", "  ", "modelsiz"])
def test_saglayici_oneki_olmayan_kimlik_reddedilir(gecersiz):
    with pytest.raises(ConfigError, match="Geçersiz model kimliği"):
        model_select.set_agent_model(make_config(), gecersiz)


def test_model_ozeti_tum_rolleri_gosterir():
    ozet = model_select.format_models(make_config())

    assert "agent :" in ozet and "hakem :" in ozet and "adaylar:" in ozet

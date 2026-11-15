"""Plan adımları ve alt ajanlar tarayıcı AYARLARINI taşır, oturum durumunu taşımaz (P-023).

Ölçüldü (31 Ekim): `plan_runner._step_context` ve `team_scope.derive_sub_context`
varsayılan kwargs'lı boş `BrowserSession()` kuruyordu: `browser.profiles_enabled: false`
kapısı plan adımında ve alt ajanda deliniyor, `default_profile`/`headless` yok sayılıyordu.
"""

from __future__ import annotations

from fusion_cli.core.browser_session import BrowserSession
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.plan_runner import _step_context
from fusion_cli.engines.agent.team_scope import derive_sub_context


def _ana_baglam(tmp_path) -> ToolContext:
    oturum = BrowserSession(profile_name="is", headless=False, profiles_enabled=False)
    oturum.page = object()  # açık oturum: KOPYALANMAMALI
    oturum.active_profile = "is"
    oturum.state_saver = lambda state: None
    return ToolContext(root=tmp_path, browser=oturum)


def test_turetilen_oturum_ayarlari_tasir_durumu_tasimaz():
    kaynak = BrowserSession(profile_name="is", headless=False, profiles_enabled=False)
    kaynak.page = object()
    kaynak.active_profile = "is"

    kopya = kaynak.derive()

    assert kopya is not kaynak
    assert (kopya.profile_name, kopya.headless, kopya.profiles_enabled) == ("is", False, False)
    assert kopya.page is None and kopya.active_profile == "" and kopya.state_saver is None


def test_plan_adimi_tarayici_ayarlarini_devralir(tmp_path):
    adim = _step_context(_ana_baglam(tmp_path))

    assert adim.browser is not _ana_baglam(tmp_path).browser
    assert adim.browser.profiles_enabled is False
    assert adim.browser.profile_name == "is" and adim.browser.headless is False
    assert adim.browser.page is None and adim.browser.active_profile == ""


def test_alt_ajan_tarayici_ayarlarini_devralir(tmp_path):
    ana = _ana_baglam(tmp_path)

    alt = derive_sub_context(ana)

    assert alt.browser is not ana.browser
    assert alt.browser.profiles_enabled is False
    assert alt.browser.profile_name == "is" and alt.browser.headless is False
    assert alt.browser.page is None

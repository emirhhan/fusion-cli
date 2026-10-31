"""Uygulama içi Tarayıcı paneli (P-045) ve öğe seçici (P-041 kalanı).

Ölçüldü (31 Ekim): ajanın `browser_*` araçları her turda görünmez bir Chromium açıp tur
sonunda kapatıyordu; kullanıcı ne olduğunu göremiyor, girişi kendisi yapıp ajana
devredemiyordu. Testler gerçek başsız Chromium ve yerel http sunucusuyla koşar.
"""

from __future__ import annotations

import asyncio
import http.server
import os
import threading
from pathlib import Path

import pytest

from fusion_cli.appserver.browser_panel import PANEL_PROFILE, BrowserPanel
from fusion_cli.config.browser_profiles import BrowserProfileStore
from fusion_cli.core.browser_session import BrowserSession
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.tools import browser as browser_tools
from fusion_cli.tools.browser_shared import SharedBrowser, control_gate

from .fakes import AlwaysApprove, RecordingSink, ScriptedProvider, make_config, model_result

_SAYFA = (
    "<!doctype html><title>Panel</title><body style='margin:0'>"
    "<input id='ad' style='position:absolute;left:10px;top:10px;width:200px;height:30px'>"
    "<button id='kaydet' style='position:absolute;left:10px;top:60px;width:120px;height:40px'"
    " onclick=\"document.title='tiklandi:'+document.getElementById('ad').value\">Kaydet</button>"
    "<script>console.error('panel-hata')</script></body>"
)


def _playwright_hazir() -> bool:
    try:
        import playwright.async_api  # noqa: F401
    except ImportError:
        return False
    cache = Path(
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or Path.home() / "Library/Caches/ms-playwright"
    )
    return any(cache.glob("chromium*")) if cache.is_dir() else False


gercek_tarayici = pytest.mark.skipif(not _playwright_hazir(), reason="Playwright/Chromium yok")


class _Sayfa(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        govde = _SAYFA.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def log_message(self, *_args: object) -> None:
        return None


@pytest.fixture
def site():
    sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Sayfa)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{sunucu.server_address[1]}/"
    sunucu.shutdown()
    sunucu.server_close()


@pytest.fixture
def depo(tmp_path):
    return BrowserProfileStore(tmp_path / "profiller", secret_key="test-anahtari")


@pytest.fixture
async def panel(tmp_path, depo):
    durum = {"tur": False}
    nesne = BrowserPanel(
        config=lambda: make_config(),
        root=lambda: tmp_path,
        turn_running=lambda: durum["tur"],
        store=lambda: depo,
    )
    nesne.durum = durum  # type: ignore[attr-defined]  # testin tur anahtarı
    yield nesne
    await nesne.close()


async def _kare(panel: BrowserPanel, son: int = 0, deneme: int = 40) -> dict:
    """İlk kare gelene kadar çek (ekran yayını ilk kareyi kısa sürede yollar)."""
    for _ in range(deneme):
        yanit = await panel.handle("tarayici_panel.kare", {"son": son})
        if "kare" in yanit:
            return yanit
        await asyncio.sleep(0.05)
    return yanit


async def _orta(panel: BrowserPanel, secici: str) -> tuple[float, float]:
    """Öğenin ortasının görünüme göre 0..1 konumu."""
    sayfa = panel.turn_browser().page
    kutu = await sayfa.locator(secici).bounding_box()
    boyut = sayfa.viewport_size
    return (
        (kutu["x"] + kutu["width"] / 2) / boyut["width"],
        (kutu["y"] + kutu["height"] / 2) / boyut["height"],
    )


# --- saf mantık -------------------------------------------------------------------- #


async def test_devralma_bırakilinca_bekleyen_ajan_araci_surer():
    oturum = BrowserSession()
    oturum.take_control()
    bekleyen = asyncio.ensure_future(control_gate(oturum, timeout_s=5))
    await asyncio.sleep(0.05)
    assert not bekleyen.done()
    oturum.release_control()
    assert await bekleyen == ""


async def test_devralma_suresi_dolarsa_ajana_kullaniciya_sor_der():
    oturum = BrowserSession()
    oturum.take_control()
    assert "devraldı" in await control_gate(oturum, timeout_s=0.05)


def test_paylasilan_oturum_kalici_ve_kendi_izin_kumesiyle_kurulur():
    paylasim = SharedBrowser(BrowserSession)
    oturum = paylasim.session()
    assert oturum.persistent and oturum.origins == set()
    assert paylasim.session() is oturum
    assert paylasim.detach() is oturum and paylasim.current is None


async def test_ajan_paylasilan_tarayiciyi_kapatamaz():
    oturum = SharedBrowser(BrowserSession).session()
    oturum.page = object()  # açık sayılır
    sonuc = await browser_tools.browser_close({}, ToolContext(root=Path(), browser=oturum))
    assert "açık bırakıldı" in sonuc.output and oturum.is_open


class _Yayinci:
    def __init__(self) -> None:
        self.sink = RecordingSink()

    def publish(self, olay: object) -> None:
        self.sink.handle(olay)


async def _tek_tur(monkeypatch, tmp_path, oturum: BrowserSession) -> None:
    saglayici = ScriptedProvider([model_result("tamam")])
    monkeypatch.setattr(agent_loop, "build_provider", lambda *a, **k: saglayici)
    deps = AgentDeps(
        config=make_config(),
        publisher=_Yayinci(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path, browser=oturum),
    )
    await run_agent("gorev", deps)


async def test_tur_sonu_paylasilan_tarayiciyi_kapatmaz_tur_basina_olani_kapatir(
    monkeypatch, tmp_path
):
    kapananlar: list[str] = []
    for ad, paylasimli in (("paylasimli", True), ("tur", False)):
        oturum = BrowserSession()
        oturum.persistent = paylasimli
        oturum.page = object()  # açık sayılır

        async def _kapat(ad: str = ad) -> None:
            kapananlar.append(ad)

        oturum.close = _kapat  # type: ignore[method-assign]
        await _tek_tur(monkeypatch, tmp_path, oturum)
    assert kapananlar == ["tur"]


async def test_kullanicinin_girisli_oturumu_onaysiz_ajana_verilmez(panel, depo, monkeypatch):
    async def _ac(oturum, origins, *, profile="", headed=False, store=None):
        oturum.page = object()
        oturum.active_profile = profile
        return oturum.page, ""

    monkeypatch.setattr("fusion_cli.appserver.browser_panel.start_session", _ac)
    assert panel.turn_browser() is not None  # temiz panel ajanla paylaşılır

    yanit = await panel.handle("tarayici_panel.profil", {"ad": PANEL_PROFILE})

    assert yanit["ok"] and yanit["kullanici_profili"] == PANEL_PROFILE
    assert depo.exists(PANEL_PROFILE)
    assert panel.turn_browser() is None and yanit["ajan_goruyor"] is False
    await panel.handle("tarayici_panel.ayar", {"anahtar": "profil_onayi", "deger": True})
    assert panel.turn_browser() is not None
    await panel.handle("tarayici_panel.ayar", {"anahtar": "ajan_paylasir", "deger": False})
    assert panel.turn_browser() is None


async def test_panel_kapaninca_girisli_profil_sonraki_ajan_turuna_kalmaz(panel, monkeypatch):
    # Ölçüldü (31 Ekim, inceleme): `_close_browser` `_user_profile`'ı sıfırlıyor ama
    # oturumun `profile_name`'ini bırakıyordu; sonraki tur onaysız girişli profili yüklüyordu.
    async def _ac(oturum, origins, *, profile="", headed=False, store=None):
        oturum.page = object()
        oturum.active_profile = profile
        return oturum.page, ""

    monkeypatch.setattr("fusion_cli.appserver.browser_panel.start_session", _ac)
    await panel.handle("tarayici_panel.profil", {"ad": PANEL_PROFILE})
    assert panel.turn_browser() is None

    await panel.handle("tarayici_panel.kapat", {})

    tur = panel.turn_browser()
    assert tur is not None and tur.profile_name == make_config().browser.default_profile
    assert tur.derive().profile_name != PANEL_PROFILE


async def test_profil_acilamazsa_secilen_profil_oturumda_kalmaz(panel, monkeypatch):
    async def _acilmaz(oturum, origins, *, profile="", headed=False, store=None):
        return None, "profil açılamadı"

    monkeypatch.setattr("fusion_cli.appserver.browser_panel.start_session", _acilmaz)
    yanit = await panel.handle("tarayici_panel.profil", {"ad": PANEL_PROFILE})

    assert yanit["ok"] is False
    tur = panel.turn_browser()
    assert tur is not None and tur.profile_name != PANEL_PROFILE


async def test_bilinmeyen_istek_ve_kapali_tarayici_girdisi_anlasilir_hata(panel):
    assert "Bilinmeyen" in (await panel.handle("tarayici_panel.uc", {}))["metin"]
    yanit = await panel.handle("tarayici_panel.tikla", {"x": 0.5, "y": 0.5})
    assert yanit["ok"] is False and "açık değil" in yanit["metin"]


# --- gerçek tarayıcı --------------------------------------------------------------- #


@gercek_tarayici
async def test_panel_acilir_kare_sekme_ve_yeni_kare_yalniz_degisince_gelir(panel, site):
    acilis = await panel.handle("tarayici_panel.ac", {"url": site})
    assert acilis["ok"] and acilis["acik"], acilis

    ilk = await _kare(panel)
    assert ilk["kare"]["mime"] == "image/jpeg" and len(ilk["kare"]["base64"]) > 100
    assert ilk["url"] == site and ilk["sekmeler"][0]["etkin"] is True

    tekrar = await panel.handle("tarayici_panel.kare", {"son": ilk["seq"]})
    assert "kare" not in tekrar  # sayfa değişmedi: kare tekrar gönderilmez

    await panel.handle("tarayici_panel.sekme_ac", {"url": site})
    ikinci = await _kare(panel, son=ilk["seq"])
    assert [sekme["etkin"] for sekme in ikinci["sekmeler"]] == [False, True]
    await panel.handle("tarayici_panel.sekme_kapat", {"no": 2})
    son = await panel.handle("tarayici_panel.kare", {"son": 0})
    assert len(son["sekmeler"]) == 1


@gercek_tarayici
async def test_panel_tiklama_ve_yazma_sayfaya_gider_konsol_okunur(panel, site):
    await panel.handle("tarayici_panel.ac", {"url": site})
    await _kare(panel)
    x, y = await _orta(panel, "#ad")
    await panel.handle("tarayici_panel.tikla", {"x": x, "y": y})
    await panel.handle("tarayici_panel.yaz", {"metin": "Ayşe"})
    x, y = await _orta(panel, "#kaydet")
    await panel.handle("tarayici_panel.tikla", {"x": x, "y": y})

    assert await panel.turn_browser().page.title() == "tiklandi:Ayşe"
    assert (await panel.handle("tarayici_panel.tus", {"tus": "rm -rf"}))["ok"] is False
    gunluk = await panel.handle("tarayici_panel.konsol", {})
    assert any("panel-hata" in satir["metin"] for satir in gunluk["konsol"])


@gercek_tarayici
async def test_konsol_temizlenince_sonraki_gezinmenin_kayitlari_gelir(panel, site):
    await panel.handle("tarayici_panel.ac", {"url": site})
    await _kare(panel)
    await panel.handle("tarayici_panel.konsol", {"temizle": True})

    await panel.handle("tarayici_panel.yenile", {})
    for _ in range(40):
        gunluk = await panel.handle("tarayici_panel.konsol", {})
        if gunluk["konsol"] and gunluk["ag"]:
            break
        await asyncio.sleep(0.05)

    assert any("panel-hata" in satir["metin"] for satir in gunluk["konsol"])
    assert gunluk["ag"] and gunluk["ag"][0]["url"].startswith(site)


@gercek_tarayici
async def test_tur_surerken_kullanici_tiklamasi_devralir_ajan_birakilinca_surer(panel, site):
    await panel.handle("tarayici_panel.ac", {"url": site})
    await _kare(panel)
    oturum = panel.turn_browser()
    panel.durum["tur"] = True
    x, y = await _orta(panel, "#ad")

    yanit = await panel.handle("tarayici_panel.tikla", {"x": x, "y": y})

    assert yanit["denetim"] == "kullanici" and oturum.user_control
    baglam = ToolContext(root=Path(), browser=oturum)
    ajan = asyncio.ensure_future(browser_tools.browser_read({}, baglam))
    await asyncio.sleep(0.2)
    assert not ajan.done()  # ajan kullanıcıyla yarışmaz, bekler
    await panel.handle("tarayici_panel.birak", {})
    sonuc = await asyncio.wait_for(ajan, 10)
    assert sonuc.ok and "Panel" in sonuc.output


@gercek_tarayici
async def test_tur_surerken_kaydirma_devralmaz_tur_bitince_kendiliginden_devralma_doner(
    panel, site
):
    # Ölçüldü (31 Ekim, inceleme): izlemek için tekerlekle kaydırmak denetimi kullanıcıya
    # geçiriyor, ajanın sonraki aracı 300 sn bekliyordu; denetim tur bitince de kullanıcıda
    # kaldığından sonraki turun ilk tarayıcı çağrısı da sessizce bekliyordu.
    await panel.handle("tarayici_panel.ac", {"url": site})
    await _kare(panel)
    oturum = panel.turn_browser()
    panel.durum["tur"] = True

    yanit = await panel.handle("tarayici_panel.kaydir", {"x": 0.5, "y": 0.5, "dy": 120})
    assert yanit["ok"] and yanit["denetim"] == "ajan" and not oturum.user_control

    x, y = await _orta(panel, "#ad")
    await panel.handle("tarayici_panel.tikla", {"x": x, "y": y})
    assert oturum.user_control
    baglam = ToolContext(root=Path(), browser=oturum)
    ajan = asyncio.ensure_future(browser_tools.browser_read({}, baglam))
    for _ in range(40):
        if (await panel.handle("tarayici_panel.durum", {}))["ajan_bekliyor"]:
            break
        await asyncio.sleep(0.05)
    assert (await panel.handle("tarayici_panel.durum", {}))["ajan_bekliyor"] is True

    panel.durum["tur"] = False
    panel.turn_finished()

    assert not oturum.user_control  # kendiliğinden devralınan denetim ajana döndü
    sonuc = await asyncio.wait_for(ajan, 10)
    assert sonuc.ok
    assert (await panel.handle("tarayici_panel.durum", {}))["ajan_bekliyor"] is False


async def test_acik_devral_tur_bitince_kullanicida_kalir(panel):
    await panel.handle("tarayici_panel.devral", {})
    panel.turn_finished()
    assert panel.turn_browser().user_control  # kullanıcı bilerek aldı: o bırakır


@gercek_tarayici
async def test_paylasilan_tarayicida_headed_ikinci_pencere_acmaz(panel, site, monkeypatch):
    # Ölçüldü (31 Ekim, inceleme): ajan `headed=true` verince paylaşılan oturum görünür
    # Chromium penceresiyle açılıyor, panelin yanında ikinci bir yerel pencere çıkıyordu.
    istenen: list[bool] = []
    gercek = browser_tools.start_session

    async def _izle(oturum, origins, **kw):
        istenen.append(kw.get("headed", False))
        return await gercek(oturum, origins, **kw)

    monkeypatch.setattr(browser_tools, "start_session", _izle)
    oturum = panel.turn_browser()
    baglam = ToolContext(
        root=Path(), browser=oturum, local_origins={site.removeprefix("http://").rstrip("/")}
    )

    sonuc = await browser_tools.browser_open({"url": site, "headed": True}, baglam)

    assert sonuc.ok and istenen == [False]
    assert "headed yok sayıldı" in sonuc.output


@gercek_tarayici
async def test_oge_secici_benzersiz_secici_ve_proje_ici_goruntu_doner(panel, site, tmp_path):
    await panel.handle("tarayici_panel.ac", {"url": site})
    await _kare(panel)
    x, y = await _orta(panel, "#kaydet")

    uzerinde = await panel.handle("tarayici_panel.oge", {"x": x, "y": y})
    secim = await panel.handle("tarayici_panel.oge_sec", {"x": x, "y": y})

    assert uzerinde["secici"] == "#kaydet" and 0 < uzerinde["kutu"]["w"] < 1
    assert secim["ok"] and secim["secici"] == "#kaydet" and secim["etiket"] == "button"
    assert secim["yol"].startswith(".fusion/secimler/oge-")
    assert (tmp_path / secim["yol"]).read_bytes().startswith(b"\x89PNG")
    assert "`#kaydet`" in secim["metin"] and "Kaydet" in secim["metin"]
    ekran = await panel.handle("tarayici_panel.ekran", {})
    assert ekran["ok"] and (tmp_path / ekran["yol"]).is_file()


@gercek_tarayici
async def test_oge_secici_parola_ve_alan_degerini_sohbete_yazmaz(panel, site):
    # Ölçüldü (31 Ekim, inceleme): seçici `el.innerText || el.value` okuyordu; parola alanı
    # seçilince değeri `metin` olarak sohbet taslağına düşüyordu.
    await panel.handle("tarayici_panel.ac", {"url": site})
    await _kare(panel)
    sayfa = panel.turn_browser().page
    await sayfa.evaluate(
        "() => { const a = document.getElementById('ad'); a.type = 'password';"
        " a.value = 'COK-GIZLI-123'; a.placeholder = 'Parola'; }"
    )
    x, y = await _orta(panel, "#ad")

    uzerinde = await panel.handle("tarayici_panel.oge", {"x": x, "y": y})
    secim = await panel.handle("tarayici_panel.oge_sec", {"x": x, "y": y})

    assert secim["ok"] and secim["secici"] == "#ad"
    assert "COK-GIZLI-123" not in str(uzerinde) and "COK-GIZLI-123" not in str(secim)
    assert "Parola" in secim["metin"]  # alanı tanıtan ipucu yine gider
    await sayfa.evaluate(
        "() => { const a = document.getElementById('ad'); a.type = 'text'; a.value = 'tc-123'; }"
    )
    secim = await panel.handle("tarayici_panel.oge_sec", {"x": x, "y": y})
    assert "tc-123" not in str(secim)


@gercek_tarayici
async def test_panel_ic_ag_adresine_gitmez_kullanicinin_yazdigi_yerel_adrese_gider(panel, site):
    await panel.handle("tarayici_panel.ac", {"url": site})
    yanit = await panel.handle("tarayici_panel.git", {"url": "http://169.254.169.254/latest/"})
    assert yanit["ok"] is False and "erişilemez" in yanit["metin"]
    # Panelde yazılan yerel adres paylaşılan izin kümesine girer: ajan da oraya gidebilir.
    assert panel.turn_browser().origins == {site.removeprefix("http://").rstrip("/")}


# --- masaüstü oturumu -------------------------------------------------------------- #


async def test_masaustu_turu_paneldeki_paylasilan_tarayiciyi_alir_ve_rpc_yonlenir(
    tmp_path, monkeypatch, depo
):
    import json

    from fusion_cli.appserver import session as app_session
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.cli import session as cli_session

    monkeypatch.setattr(app_session, "default_browser_profile_store", lambda: depo)
    goruldu: dict = {}

    async def _sahte_tur(_task, _config, **kwargs):
        goruldu.update(kwargs)
        from types import SimpleNamespace

        return SimpleNamespace(ok=True, final_text="bitti", messages=[])

    monkeypatch.setattr(cli_session, "run_agent_task", _sahte_tur)
    satirlar: list[str] = []
    oturum = app_session.AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")
    try:
        await oturum._chrome_turn("sayfayı oku")
        await oturum.handle(Request(id="d1", name="tarayici_panel.durum", data={}))
    finally:
        await oturum.close()

    assert goruldu["browser"] is not None and goruldu["browser"].persistent
    durum = next(
        json.loads(satir)["veri"]
        for satir in satirlar
        if json.loads(satir).get("id") == "d1" and json.loads(satir).get("tip") == "sonuc"
    )
    assert durum["ok"] and durum["acik"] is False and durum["ajan_goruyor"] is True


async def test_panel_agent_kapaliysa_tur_kendi_tarayicisini_acar(tmp_path, depo):
    from dataclasses import replace

    config = make_config()
    config = replace(config, browser=replace(config.browser, panel_agent=False))
    nesne = BrowserPanel(
        config=lambda: config, root=lambda: tmp_path, turn_running=lambda: False, store=lambda: depo
    )
    assert nesne.turn_browser() is None

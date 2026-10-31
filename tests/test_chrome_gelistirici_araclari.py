"""Chrome eklentisinin geliştirici ve yardımcı araçları (P-042, P-043, P-044, P-073).

Konsol/ağ okuma, erişilebilirlik ağacı, ağ boşta bekleme, GIF kaydı, kısayollar,
pencere/sekme grubu ve Windows/Linux Chrome açma komutu. Eklenti sahte köprüyle
karşılanır; GIF Pillow ile gerçekten yazılır.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from fusion_cli.appserver.chrome_bridge import chrome_launch_command
from fusion_cli.appserver.chrome_feed import control_channel, step_text
from fusion_cli.core.tools import ToolContext, ToolEffect
from fusion_cli.tools import chrome, chrome_inspect, chrome_record

EXTENSION = Path(__file__).resolve().parents[1] / "chrome-extension"


class _Kopru:
    def __init__(self, cevaplar: dict[str, object] | None = None) -> None:
        self.cagrilar: list[tuple[str, dict]] = []
        self._cevaplar = cevaplar or {}

    async def invoke(self, name, data):
        self.cagrilar.append((name, data))
        cevap = self._cevaplar.get(name, {"tamam": True})
        if callable(cevap):
            cevap = cevap(data)
        return {"ok": True, "veri": cevap}


def _baglam(kopru: _Kopru, root: Path | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        chrome=kopru,
        root=root or Path("/tmp/fusion-test-root"),
        restrict_to_root=False,
        extra_roots=(),
        write_scope=None,
        local_origins=set(),
    )


# --- P-042: konsol ve ağ ---------------------------------------------------------------


async def test_konsol_okuma_hata_filtresi_ve_desen_eklentiye_gider_sirlar_maskelenir():
    kopru = _Kopru(
        {
            "console": {
                "present": True,
                "total": 2,
                "matched": 1,
                "messages": [{"level": "error", "text": "token=sk-abcdef1234567890abcdef Hata"}],
            }
        }
    )
    baglam = _baglam(kopru)

    hepsi = await chrome.chrome_action({"action": "console"}, baglam)
    hatalar = await chrome.chrome_action({"action": "console", "value": "errors"}, baglam)
    desen = await chrome.chrome_action({"action": "console", "value": "errors:TypeError"}, baglam)
    serbest = await chrome.chrome_action({"action": "console", "value": "Uncaught"}, baglam)

    assert kopru.cagrilar == [
        ("console", {"limit": chrome.MONITOR_LIMIT}),
        ("console", {"limit": chrome.MONITOR_LIMIT, "only_errors": True}),
        ("console", {"limit": chrome.MONITOR_LIMIT, "only_errors": True, "pattern": "TypeError"}),
        ("console", {"limit": chrome.MONITOR_LIMIT, "pattern": "Uncaught"}),
    ]
    assert hepsi.ok and hatalar.ok and desen.ok and serbest.ok
    assert "sk-abcdef1234567890abcdef" not in hepsi.output and "Hata" in hepsi.output


async def test_ag_okuma_url_deseni_ve_istek_kimligi_eklentiye_gider():
    kopru = _Kopru({"network": {"present": True, "requests": [], "total": 0}})
    baglam = _baglam(kopru)

    assert (await chrome.chrome_action({"action": "network"}, baglam)).ok
    assert (await chrome.chrome_action({"action": "network", "value": "/api/"}, baglam)).ok
    assert (await chrome.chrome_action({"action": "network", "value": "id:17"}, baglam)).ok

    assert kopru.cagrilar == [
        ("network", {"limit": chrome.MONITOR_LIMIT}),
        ("network", {"limit": chrome.MONITOR_LIMIT, "url_pattern": "/api/"}),
        ("network", {"request_id": 17}),
    ]


async def test_izleyici_yoksa_ipucu_modele_aynen_iletilir():
    kopru = _Kopru({"console": {"present": False, "messages": [], "ipucu": "İzleme şimdi başladı"}})
    sonuc = await chrome.chrome_action({"action": "console"}, _baglam(kopru))
    assert sonuc.ok and "İzleme şimdi başladı" in sonuc.output


# --- P-043: ağaç ve ağ boşta bekleme -----------------------------------------------------


async def test_chrome_page_agac_kipi_derinlik_filtre_ve_alt_agac_tasir():
    kopru = _Kopru(
        {
            "tree": {
                "title": "Mağaza",
                "url": "https://magaza.test/",
                "tree": 'button "Sepete ekle" [e0]',
                "lines": 1,
                "truncated": False,
                "doc": "abc",
            }
        }
    )
    baglam = _baglam(kopru)

    tam = await chrome.chrome_page({"tree": "all"}, baglam)
    etkilesimli = await chrome.chrome_page({"tree": "interactive", "depth": 4, "ref": "e3"}, baglam)

    assert kopru.cagrilar == [
        ("tree", {"filter": "all"}),
        ("tree", {"filter": "interactive", "depth": 4, "ref": "e3"}),
    ]
    assert tam.ok and 'button "Sepete ekle" [e0]' in tam.output and "Mağaza" in tam.output
    assert etkilesimli.ok


async def test_chrome_page_agac_kirpildiysa_modele_soyler():
    kopru = _Kopru(
        {"tree": {"title": "T", "url": "u", "tree": "x", "lines": 600, "truncated": True}}
    )
    sonuc = await chrome.chrome_page({"tree": "all"}, _baglam(kopru))
    assert "kırpıldı" in sonuc.output and "ref" in sonuc.output


async def test_ag_bosta_bekleme_eklentiye_network_idle_ile_gider():
    kopru = _Kopru({"wait": {"idle": True, "waited_ms": 800}})
    baglam = _baglam(kopru)

    for deger in ("network_idle", " Network_Idle "):
        assert (await chrome.chrome_action({"action": "wait", "value": deger}, baglam)).ok
    # Ölçüldü (31 Ekim, bağımsız inceleme): "network", "ağ", "ag" da ağ beklemesi sayılıyordu;
    # "Network" bir sekme adı ya da sayfa başlığı olabilir ve eskiden metin olarak beklenirdi.
    # Yalnız `network_idle` ayrılmış anahtardır.
    for metin in ("Kaydedildi", "Network", "ağ", "ag"):
        assert (await chrome.chrome_action({"action": "wait", "value": metin}, baglam)).ok

    assert kopru.cagrilar[:2] == [("wait", {"network_idle": True, "timeout_ms": 20_000})] * 2
    assert kopru.cagrilar[2:] == [
        ("wait", {"text": metin, "timeout_ms": 20_000})
        for metin in ("Kaydedildi", "Network", "ağ", "ag")
    ]
    assert (
        step_text("chrome_action", {"action": "wait", "value": "Network"}) == "“Network” bekleniyor"
    )


# --- P-044: GIF kaydı ---------------------------------------------------------------------


def _jpeg(renk: tuple[int, int, int]) -> str:
    gorsel = Image.new("RGB", (24, 16), renk)
    tampon = io.BytesIO()
    gorsel.save(tampon, format="JPEG")
    return base64.b64encode(tampon.getvalue()).decode("ascii")


async def test_kayit_baslat_ve_bitir_kareleri_parca_parca_ceker_gif_yazar(tmp_path):
    kareler = [{"t": 0, "image": _jpeg((200, 0, 0))}, {"t": 500, "image": _jpeg((0, 200, 0))},
               {"t": 1000, "image": _jpeg((0, 0, 200))}]  # fmt: skip

    def _record(data):
        if data["op"] == "start":
            return {"recording": True, "interval_ms": 500, "max_frames": 120}
        if data["op"] == "stop":
            return {"frames": 3, "width": 24, "height": 16, "duration_ms": 1000}
        baslangic = data["from"]
        return {"from": baslangic, "frames": kareler[baslangic : baslangic + 2],
                "next": baslangic + 2 if baslangic + 2 < len(kareler) else None}  # fmt: skip

    kopru = _Kopru({"record": _record})
    baglam = ToolContext(root=tmp_path, chrome=kopru)

    baslat = await chrome.chrome_action({"action": "record", "value": "start"}, baglam)
    bitir = await chrome.chrome_action({"action": "record", "value": "stop"}, baglam)

    assert baslat.ok and "başladı" in baslat.output
    assert bitir.ok, bitir.output
    assert [c[1] for c in kopru.cagrilar] == [
        {"op": "start"}, {"op": "stop"}, {"op": "fetch", "from": 0}, {"op": "fetch", "from": 2},
    ]  # fmt: skip
    dosyalar = list((tmp_path / chrome_record.RECORD_DIR).glob("chrome-*.gif"))
    assert len(dosyalar) == 1 and str(dosyalar[0].relative_to(tmp_path)) in bitir.output
    with Image.open(dosyalar[0]) as gif:
        assert gif.format == "GIF" and gif.n_frames == 3
        gif.seek(1)
        assert gif.info["duration"] == 500


async def test_kayit_karesiz_biterse_gif_yazilmaz_ve_aciklanir(tmp_path):
    kopru = _Kopru({"record": lambda data: {"frames": 0, "error": "kare alınamadı"}})
    sonuc = await chrome.chrome_action(
        {"action": "record", "value": "stop"}, ToolContext(root=tmp_path, chrome=kopru)
    )
    assert not sonuc.ok and "kare" in sonuc.output
    assert not (tmp_path / chrome_record.RECORD_DIR).exists()


async def test_kayit_gecersiz_degerde_anlasilir_hata():
    sonuc = await chrome.chrome_action({"action": "record", "value": "pause"}, _baglam(_Kopru()))
    assert not sonuc.ok and "start" in sonuc.output and "stop" in sonuc.output


def test_gif_kare_sureleri_zaman_damgasindan_turer():
    kareler = [(0, base64.b64decode(_jpeg((1, 2, 3)))), (700, base64.b64decode(_jpeg((4, 5, 6))))]
    veri = chrome_record.build_gif(kareler)
    with Image.open(io.BytesIO(veri)) as gif:
        assert gif.n_frames == 2 and gif.info["duration"] == 700


# --- P-073: kısayollar, pencere, sekme grubu, Chrome açma ---------------------------------


async def test_kisayollar_listelenir_ve_calistirilan_kisayol_gorev_metni_olarak_doner():
    kopru = _Kopru(
        {
            "shortcuts": {"shortcuts": [{"ad": "ozet", "metin": "Bu sayfayı özetle."}]},
            "shortcut_run": {"ad": "ozet", "metin": "Bu sayfayı özetle."},
        }
    )
    baglam = _baglam(kopru)

    liste = await chrome.chrome_action({"action": "shortcuts"}, baglam)
    calistir = await chrome.chrome_action({"action": "shortcut", "value": "/ozet"}, baglam)
    eksik = await chrome.chrome_action({"action": "shortcut"}, baglam)

    assert liste.ok and "ozet" in liste.output
    assert calistir.ok and "Bu sayfayı özetle." in calistir.output and "şimdi" in calistir.output
    assert not eksik.ok
    assert kopru.cagrilar == [("shortcuts", {}), ("shortcut_run", {"name": "ozet"})]


async def test_pencere_ve_sekme_grubu_eklentiye_dogru_gider(monkeypatch):
    # Testte DNS yok: adres koruması sahte, ayrı testte gerçek koruma denenir.
    monkeypatch.setattr(chrome_inspect, "browser_block_reason", lambda _url, _origins: None)
    kopru = _Kopru()
    baglam = _baglam(kopru)

    assert (await chrome.chrome_action({"action": "window"}, baglam)).ok
    assert (await chrome.chrome_action({"action": "window", "value": "ornek.com"}, baglam)).ok
    assert (await chrome.chrome_action({"action": "group", "value": "12, 13:Araştırma"}, baglam)).ok
    assert (await chrome.chrome_action({"action": "group", "value": "7"}, baglam)).ok
    assert not (await chrome.chrome_action({"action": "group", "value": "a,b"}, baglam)).ok

    assert kopru.cagrilar == [
        ("window_new", {}),
        ("window_new", {"url": "https://ornek.com"}),
        ("tab_group", {"ids": [12, 13], "title": "Araştırma"}),
        ("tab_group", {"ids": [7], "title": ""}),
    ]


async def test_yeni_pencere_ic_ag_korumasindan_gecer():
    kopru = _Kopru()
    sonuc = await chrome.chrome_action(
        {"action": "window", "value": "http://169.254.169.254/"}, _baglam(kopru)
    )
    assert not sonuc.ok and kopru.cagrilar == []


async def test_yeni_eylemlerin_onay_etkisi():
    for islem in ("console", "network", "shortcuts", "shortcut", "window"):
        assert (
            await chrome.chrome_action_effect({"action": islem}, None) is ToolEffect.REMOTE_READ
        ), islem
    assert (
        await chrome.chrome_action_effect({"action": "group"}, None) is ToolEffect.REMOTE_INTERACT
    )
    # Ölçüldü (31 Ekim, bağımsız inceleme): `record` REMOTE_READ sayılıyordu; `stop` proje
    # köküne dosya yazar, `start` ekranı 60 sn boyunca yakalar. Tek karelik `screenshot`
    # ile aynı sınıfta olamaz.
    for deger in ("start", "stop", None):
        args = {"action": "record", **({"value": deger} if deger else {})}
        assert await chrome.chrome_action_effect(args, None) is ToolEffect.REMOTE_INTERACT, deger


async def test_ekran_kaydi_plan_kipinde_engellenir_manuel_kipte_sorulur():
    from fusion_cli.engines.agent.approval import (
        ApprovalMode,
        Decision,
        build_policy,
        build_request,
    )
    from fusion_cli.tools import build_registry

    from .fakes import AlwaysReject

    arac = build_registry().get("chrome_action")
    for deger in ("start", "stop"):
        args = {"action": "record", "value": deger}
        etki = await chrome.chrome_action_effect(args, None)
        istek = build_request(arac, args, effect=etki)
        assert istek.read_only is False, deger
        assert (
            await build_policy(ApprovalMode.PLAN, AlwaysReject()).decide(istek) is Decision.BLOCKED
        )
        assert (
            await build_policy(ApprovalMode.SECURITY, AlwaysReject()).decide(istek)
            is Decision.DENIED
        ), deger
    # Otomatik kipte sorulmaz: kalıcı iz yok, dosya proje kökünde ve `writable_path` denetiminde.
    istek = build_request(
        arac, {"action": "record", "value": "stop"}, effect=ToolEffect.REMOTE_INTERACT
    )
    assert await build_policy(ApprovalMode.AUTO, AlwaysReject()).decide(istek) is Decision.ALLOW


def test_chrome_acma_komutu_uc_platformda():
    assert chrome_launch_command("darwin", lambda _ad: None) == [
        "open",
        "-g",
        "-a",
        "Google Chrome",
    ]
    assert chrome_launch_command("win32", lambda _ad: None) == ["cmd", "/c", "start", "", "chrome"]
    assert chrome_launch_command(
        "linux", lambda ad: "/usr/bin/chromium" if ad == "chromium" else None
    ) == ["/usr/bin/chromium"]
    assert chrome_launch_command("linux", lambda _ad: None) is None


# --- Kayıt defteri, panel akışı ve kaynak güvenceleri --------------------------------------


def test_yeni_eylemler_semada_ve_aciklamada():
    from fusion_cli.tools import build_registry

    kayit = build_registry()
    eylemler = kayit.get("chrome_action").parameters["properties"]["action"]["enum"]
    for eylem in ("console", "network", "record", "shortcuts", "shortcut", "window", "group"):
        assert eylem in eylemler, eylem
    assert "network_idle" in kayit.get("chrome_action").description
    sayfa = kayit.get("chrome_page").parameters["properties"]
    assert sayfa["tree"]["enum"] == ["all", "interactive"] and "depth" in sayfa and "ref" in sayfa


def test_yeni_adimlar_panelde_insan_diliyle_ve_kanaliyla_gorunur():
    assert (
        step_text("chrome_action", {"action": "console", "value": "errors"})
        == "Konsol hataları okundu"
    )
    assert step_text("chrome_action", {"action": "console"}) == "Konsol iletileri okundu"
    assert step_text("chrome_action", {"action": "network"}) == "Ağ istekleri okundu"
    assert (
        step_text("chrome_action", {"action": "record", "value": "start"}) == "Ekran kaydı başladı"
    )
    assert (
        step_text("chrome_action", {"action": "record", "value": "stop"})
        == "Ekran kaydı GIF olarak kaydedildi"
    )
    assert (
        step_text("chrome_action", {"action": "wait", "value": "network_idle"})
        == "Ağın boşa düşmesi bekleniyor"
    )
    assert step_text("chrome_page", {"tree": "all"}) == "Sayfa ağacı okundu"
    assert control_channel("chrome_action", {"action": "record"}) == "ekran"


def test_manifest_debugger_izni_istemez_kisayol_ve_izleyici_tanimli():
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    assert "debugger" not in manifest["permissions"] and "webRequest" not in manifest["permissions"]
    assert "tabGroups" in manifest["permissions"]
    assert set(manifest["commands"]) == {"_execute_action", "fusion-stop"}
    core = (EXTENSION / "core.js").read_text(encoding="utf-8")
    assert 'world: "MAIN"' in core and 'js: ["pageMonitor.js"]' in core
    assert (EXTENSION / "pageMonitor.js").is_file() and (EXTENSION / "recorder.js").is_file()
    assert manifest["version"] != "0.3.12"

"""Masaüstü Ayarlar → Tarayıcı: konsol/ağ izleme anahtarı ve kısayol yönetimi RPC'leri.

Eklenti panelindeki iki ayar masaüstünden de yönetilir; köprü üzerinden eklentinin
`storage.local` deposu değişir (yarım yüzey kalmaz).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from fusion_cli.appserver.chrome_settings import CHROME_SETTINGS_ROUTES, dispatch_chrome_settings
from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession


class _Kopru:
    def __init__(self, cevaplar: dict[str, object] | None = None, *, bagli: bool = True) -> None:
        self.cagrilar: list[tuple[str, dict]] = []
        self._cevaplar = cevaplar or {}
        self._bagli = bagli

    async def invoke(self, name, data):
        if not self._bagli:
            raise ConnectionError("Chrome eklentisi bağlı değil.")
        self.cagrilar.append((name, data))
        cevap = self._cevaplar.get(name, {})
        return {"ok": True, "veri": cevap(data) if callable(cevap) else cevap}


async def test_izleme_anahtari_okunur_ve_degistirilir():
    kopru = _Kopru(
        {"monitor_get": {"enabled": True}, "monitor_set": lambda d: {"enabled": d["enabled"]}}
    )

    oku = await dispatch_chrome_settings(kopru, "chrome.izleme", {})
    kapat = await dispatch_chrome_settings(kopru, "chrome.izleme", {"acik": False})

    assert oku == {"ok": True, "acik": True}
    assert kapat == {"ok": True, "acik": False}
    assert kopru.cagrilar == [("monitor_get", {}), ("monitor_set", {"enabled": False})]


async def test_kisayollar_listelenir_kaydedilir_silinir_ve_girdi_denetlenir():
    liste = [{"ad": "ozet", "metin": "Özetle."}]
    kopru = _Kopru(
        {
            "shortcuts": lambda _d: {"shortcuts": liste},
            "shortcut_set": lambda d: {"shortcuts": [*liste, {"ad": d["ad"], "metin": d["metin"]}]},
            "shortcut_delete": lambda _d: {"shortcuts": []},
        }
    )

    assert await dispatch_chrome_settings(kopru, "chrome.kisayollar", {}) == {
        "ok": True,
        "kisayollar": liste,
    }
    kaydet = await dispatch_chrome_settings(
        kopru, "chrome.kisayol_kaydet", {"ad": "cevir", "metin": "Çevir."}
    )
    assert kaydet["ok"] is True and kaydet["kisayollar"][-1] == {"ad": "cevir", "metin": "Çevir."}
    assert await dispatch_chrome_settings(kopru, "chrome.kisayol_sil", {"ad": "ozet"}) == {
        "ok": True,
        "kisayollar": [],
    }
    # Girdi köprüye gitmeden denetlenir: boş ad/metin, ad biçimi, çok uzun görev.
    bozuk = (
        {"ad": "", "metin": "x"},
        {"ad": "iki kelime", "metin": "x"},
        {"ad": "a", "metin": ""},
        {"ad": "a", "metin": "x" * 2001},
        {"ad": 5, "metin": "x"},
    )
    for veri in bozuk:
        sonuc = await dispatch_chrome_settings(kopru, "chrome.kisayol_kaydet", veri)
        assert sonuc["ok"] is False and sonuc["metin"], veri
    assert len(kopru.cagrilar) == 3


async def test_eklenti_bagli_degilse_anlasilir_hata():
    sonuc = await dispatch_chrome_settings(_Kopru(bagli=False), "chrome.kisayollar", {})

    assert sonuc["ok"] is False and "bağlı değil" in sonuc["metin"]


async def test_oturum_chrome_ayar_isteklerini_kopruye_yonlendirir(tmp_path):
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")
    kopru = _Kopru({"monitor_get": {"enabled": False}})
    oturum._chrome = SimpleNamespace(invoke=kopru.invoke)  # köprü sahte: Chrome açılmaz

    assert "chrome.izleme" in CHROME_SETTINGS_ROUTES
    await oturum.handle(Request(id="iz", name="chrome.izleme", data={}))

    sonuc = json.loads(satirlar[-1])
    assert sonuc["id"] == "iz" and sonuc["veri"] == {"ok": True, "acik": False}

"""`/model` seçicisinin masaüstündeki adım adım akışı.

Gerçek hata: seçicinin ilk adımı rolleri MEVCUT model kimliğiyle birlikte
sunuyordu (`agent gemini_web/main/auto`); seçilince komut aynı modeli yeniden
uyguluyor, ikinci adım ise "Bilinmeyen komut." dönüyordu. Yani kullanıcı
"Ajan modelini değiştir" deyip yalnız zaten kullandığı modeli görüyordu.

Doğru akış üç adımdır: rol → kaynak → model.
"""

from __future__ import annotations

import json

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession


def _sonuc(satirlar, kimlik):
    for satir in reversed(satirlar):
        veri = json.loads(satir)
        if veri.get("tip") == "sonuc" and veri.get("id") == kimlik:
            return veri["veri"]
    raise AssertionError(kimlik)


async def _secici(oturum, satirlar, kimlik, arguman):
    await oturum.handle(Request(kimlik, "komut.secenekler", {"ad": "model", "arguman": arguman}))
    return _sonuc(satirlar, kimlik)


async def test_ilk_adim_rolleri_model_kimligi_olmadan_sunar(tmp_path):
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    veri = await _secici(oturum, satirlar, "1", "")

    assert veri["ok"] is True
    degerler = [secim["deger"] for secim in veri["secici"]["secenekler"]]
    assert "agent" in degerler
    assert "judge" in degerler
    # Değerler model kimliği TAŞIMAZ; taşısaydı seçim aynı modeli yeniden uygulardı.
    assert all("/" not in deger for deger in degerler)


async def test_rol_secilince_kaynaklar_listelenir(tmp_path):
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    veri = await _secici(oturum, satirlar, "2", "agent")

    assert veri["ok"] is True
    etiketler = [secim["etiket"] for secim in veri["secici"]["secenekler"]]
    assert len(etiketler) >= 3, etiketler


async def test_kaynak_secilince_o_kaynagin_modelleri_gelir(tmp_path, monkeypatch):
    from fusion_cli.providers.catalog import CatalogEntry

    monkeypatch.setattr(
        "fusion_cli.cli.repl.model_flows.catalog.fetch_nim",
        lambda *a, **k: (
            CatalogEntry(model_id="nvidia_nim/a", provider="nvidia_nim"),
            CatalogEntry(model_id="nvidia_nim/b", provider="nvidia_nim"),
        ),
    )
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    veri = await _secici(oturum, satirlar, "3", "agent kaynak nim-free")

    secici = veri["secici"]
    degerler = [secim["deger"] for secim in secici["secenekler"]]
    assert degerler == ["nvidia_nim/a", "nvidia_nim/b"]
    # Önek istemci tarafında eklenir; komut `model agent <model>` olarak tamamlanır.
    assert secici["devam"]["arguman_on_eki"] == "agent "


async def test_secilen_model_yalniz_o_role_uygulanir(tmp_path):
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")
    onceki_hakem = oturum._state.config.judge.model

    await oturum.handle(
        Request("4", "komut.calistir", {"ad": "model", "arguman": "agent nvidia_nim/yeni"})
    )

    assert _sonuc(satirlar, "4")["ok"] is True
    assert oturum._state.config.agent.model == "nvidia_nim/yeni"
    assert oturum._state.config.judge.model == onceki_hakem

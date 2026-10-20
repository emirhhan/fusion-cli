"""Sır değerleri tel üzerine sızmamalı."""

from __future__ import annotations

import json

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.cli.repl.commands import CommandRegistry, SlashCommand
from fusion_cli.cli.repl.state import ReplState

GIZLI = "sk-test-0123456789abcdefghijklmnop"


async def test_komut_argumani_sonuc_metnine_yansimaz(tmp_path):
    """Anahtar argüman olarak geçse bile sonuç satırında görünmemeli."""
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    await oturum.handle(
        Request(id="1", name="komut.calistir", data={"ad": "learn", "arguman": GIZLI})
    )

    assert all(GIZLI not in satir for satir in satirlar), "sır çıktı satırına sızdı"


async def test_bilinmeyen_istek_verisi_geri_yankilanmaz(tmp_path):
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    await oturum.handle(Request(id="2", name="olmayan", data={"token": GIZLI}))

    assert all(GIZLI not in satir for satir in satirlar)


async def test_providers_add_akisi_sirri_tele_yazmaz(tmp_path, monkeypatch):
    """`/providers add` gizli-metin akışı gerçek anahtar deposuyla uçtan uca çalışsa
    bile ne sonuç metnine ne de tel satırlarına sızmamalı.

    Depo, gerçek kullanıcı dizinlerine değil `tmp_path` altına yazılsın diye
    `XDG_DATA_HOME` bu test içinde geçici bir dizine yönlendirilir; ana anahtar
    da yalnız bu test için ortam değişkenine konur (conftest her testten önce
    siler).
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "veri"))
    monkeypatch.setenv("FUSION_SECRET_KEY", "test-master-anahtar")

    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    await oturum.handle(
        Request(id="1", name="komut.calistir", data={"ad": "providers", "arguman": "add"})
    )
    await oturum.handle(
        Request(
            id="2",
            name="komut.calistir",
            data={"ad": "providers", "arguman": "add openai"},
        )
    )
    await oturum.handle(
        Request(
            id="3",
            name="komut.calistir",
            data={"ad": "providers", "arguman": f"add openai {GIZLI}"},
        )
    )
    await oturum.handle(Request(id="4", name="oturum.durum", data={}))
    await oturum.handle(
        Request(id="5", name="komut.secenekler", data={"ad": "providers", "arguman": "add"})
    )

    assert all(GIZLI not in satir for satir in satirlar), "sır tel satırına sızdı"

    son_sonuc = json.loads(satirlar[2])
    assert son_sonuc["veri"]["ok"] is True

    # Depo dosyası şifrelidir; yine de düz metin anahtarın diskte GÖRÜNMEDİĞİ
    # doğrulanır (şifreleme zaten bunu garanti eder, bu ek bir güvenlik ağıdır).
    veri_dizini = tmp_path / "veri"
    sifreli_dosyalar = list(veri_dizini.rglob("*.enc")) if veri_dizini.exists() else []
    for dosya in sifreli_dosyalar:
        assert GIZLI.encode() not in dosya.read_bytes()


async def test_run_command_istisna_ham_argumani_sizdirmaz(tmp_path, monkeypatch):
    """`run_command`'ın istisna dalı, çöken işleyicinin ham argümanını (sırrı da
    içerebilecek bir dizgeyi) sonuç metnine ya da tel satırına yansıtmamalı."""

    def _patlayan_isleyici(_state: ReplState, argument: str) -> str:
        raise ValueError(f"beklenmeyen argüman: {argument}")

    def _sahte_registry(_home: object) -> CommandRegistry:
        registry = CommandRegistry()
        registry.register(SlashCommand(name="patlayan", summary="test", handler=_patlayan_isleyici))
        return registry

    monkeypatch.setattr("fusion_cli.appserver.session.build_registry", _sahte_registry)

    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    await oturum.handle(
        Request(id="1", name="komut.calistir", data={"ad": "patlayan", "arguman": GIZLI})
    )

    assert all(GIZLI not in satir for satir in satirlar), "istisna mesajı sırrı sızdırdı"
    sonuc = json.loads(satirlar[-1])
    assert sonuc["veri"]["ok"] is False

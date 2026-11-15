"""Şifreli sır deposu ve /providers add sihirbazı.

Depo diske yalnızca tmp_path altında yazar; gerçek anahtar kullanılmaz.
"""

from __future__ import annotations

import pytest

from fusion_cli.cli.repl import provider_flow
from fusion_cli.config.credentials import FernetSecretStore
from fusion_cli.core.errors import ConfigError
from fusion_cli.ui import messages

_KEY = "test-ana-anahtari"


def _store(tmp_path, key=_KEY):
    return FernetSecretStore(tmp_path / "secrets.enc", secret_key=key)


# --- depo ------------------------------------------------------------------ #


def test_yaz_oku_dongusu(tmp_path):
    store = _store(tmp_path)
    store.set("OPENAI_API_KEY", "sk-gizli")
    assert store.get("OPENAI_API_KEY") == "sk-gizli"


def test_diskteki_deger_sifrelidir(tmp_path):
    store = _store(tmp_path)
    store.set("OPENAI_API_KEY", "sk-gizli")
    ham = (tmp_path / "secrets.enc").read_bytes()
    # Şifreli metin, sırrı DÜZ olarak içermez.
    assert b"sk-gizli" not in ham


def test_yanlis_anahtar_cozemez(tmp_path):
    _store(tmp_path, key="dogru").set("K", "v")
    with pytest.raises(ConfigError, match="çözülemedi"):
        _store(tmp_path, key="yanlis").get("K")


def test_anahtarsiz_depo_kullanilamaz(tmp_path):
    store = FernetSecretStore(tmp_path / "s.enc", secret_key=None)
    assert store.available is False
    with pytest.raises(ConfigError, match="FUSION_SECRET_KEY"):
        store.set("K", "v")


def test_sil_ve_listele(tmp_path):
    store = _store(tmp_path)
    store.set("A", "1")
    store.set("B", "2")
    assert store.list_names() == ("A", "B")
    assert store.delete("A") is True
    assert store.list_names() == ("B",)


def test_liste_degerleri_dondurmez(tmp_path):
    store = _store(tmp_path)
    store.set("OPENAI_API_KEY", "sk-gizli")
    assert "sk-gizli" not in str(store.list_names())


# --- ortama uygulama ------------------------------------------------------- #


def test_ortama_uygular_ama_dolu_degiskeni_ezmez(tmp_path):
    store = _store(tmp_path)
    store.set("OPENAI_API_KEY", "depodan")
    store.set("GEMINI_API_KEY", "gemini-depodan")
    ortam: dict[str, str] = {"OPENAI_API_KEY": "elle-verilen"}
    uygulanan = store.apply_to_environ(ortam)
    # Zaten dolu olan ezilmez; boş/eksik olan uygulanır.
    assert ortam["OPENAI_API_KEY"] == "elle-verilen"
    assert ortam["GEMINI_API_KEY"] == "gemini-depodan"
    assert "GEMINI_API_KEY" in uygulanan
    assert "OPENAI_API_KEY" not in uygulanan


def test_anahtarsiz_depo_ortama_dokunmaz(tmp_path):
    store = FernetSecretStore(tmp_path / "s.enc", secret_key=None)
    assert store.apply_to_environ({}) == ()


# --- /providers add sihirbazı ---------------------------------------------- #


def _pick(value):
    def _p(choices, *, title, gradient_rows=False, stream=None):
        return value

    return _p


def test_wizard_secilen_saglayici_anahtarini_kaydeder(tmp_path):
    store = _store(tmp_path)
    mesaj = provider_flow.add_credential(
        store, picker=_pick("openai"), ask_secret=lambda prompt: "sk-yeni"
    )
    assert store.get("OPENAI_API_KEY") == "sk-yeni"
    assert "sk-yeni" not in mesaj  # anahtar mesajda GÖRÜNMEZ


def test_wizard_anahtarsiz_depoda_uyarir(tmp_path):
    store = FernetSecretStore(tmp_path / "s.enc", secret_key=None)
    mesaj = provider_flow.add_credential(
        store, picker=_pick("openai"), ask_secret=lambda prompt: "x"
    )
    assert mesaj == messages.CRED_NO_KEY


def test_wizard_bos_sirda_vazgecer(tmp_path):
    store = _store(tmp_path)
    mesaj = provider_flow.add_credential(
        store, picker=_pick("openai"), ask_secret=lambda prompt: ""
    )
    assert mesaj == messages.PICKER_CANCELLED
    assert store.list_names() == ()


def test_wizard_yerel_saglayiciyi_sunmaz(tmp_path):
    # Ollama (yerel, anahtarsız) ve web-session (framework) eklenebilir listede olmamalı.
    from fusion_cli.providers.registry import BUILTIN_PROVIDERS

    eklenebilir = provider_flow.addable_providers(BUILTIN_PROVIDERS)
    kimlikler = {p.id for p in eklenebilir}
    assert "ollama" not in kimlikler
    assert "chatgpt_web" not in kimlikler
    assert "openai" in kimlikler


# --- L2-04: atomik yazım, kilit, bozuk içerik ------------------------------ #


def test_yazma_yarida_cokerse_eski_depo_bozulmaz(tmp_path, monkeypatch):
    store = _store(tmp_path)
    store.set("A", "1")
    onceki = (tmp_path / "secrets.enc").read_bytes()

    def coker(*args, **kwargs):
        raise OSError("disk dolu")

    monkeypatch.setattr("fusion_cli.config.credentials.os.fsync", coker)
    with pytest.raises(ConfigError, match="yazılamadı"):
        store.set("B", "2")

    assert (tmp_path / "secrets.enc").read_bytes() == onceki
    assert store.get("A") == "1"
    assert not list(tmp_path.glob("*.tmp"))


def test_yazimdan_once_bak_kopyasi_alinir(tmp_path):
    store = _store(tmp_path)
    store.set("A", "1")
    ilk = (tmp_path / "secrets.enc").read_bytes()
    store.set("B", "2")

    assert (tmp_path / "secrets.enc.bak").read_bytes() == ilk


def test_eszamanli_yazimlar_birbirini_ezmez(tmp_path):
    import threading

    isimler = [f"K{i}" for i in range(12)]

    def yaz(isim):
        _store(tmp_path).set(isim, "v")

    kanallar = [threading.Thread(target=yaz, args=(isim,)) for isim in isimler]
    for kanal in kanallar:
        kanal.start()
    for kanal in kanallar:
        kanal.join()

    assert set(_store(tmp_path).list_names()) == set(isimler)


@pytest.mark.parametrize("icerik", [b"{bozuk", b"[1, 2]", b'"yazi"', b"\xff\xfe"])
def test_cozulen_icerik_bozuksa_config_error(tmp_path, icerik):
    store = _store(tmp_path)
    token = store._fernet().encrypt(icerik)  # type: ignore[attr-defined]
    (tmp_path / "secrets.enc").write_bytes(token)

    with pytest.raises(ConfigError, match="bozuk"):
        store.list_names()


def test_wizard_on_saved_ile_anahtar_ayni_oturumda_etkin_olur(tmp_path):
    """Ölçüldü (30 Ekim): eklenen anahtar 'sonraki oturumda' etkindi; aynı oturumda model
    çağıran kullanıcı kimlik doğrulama hatası alıyordu (L2-25)."""
    store = _store(tmp_path)
    uygulanan: list[tuple[str, str]] = []

    mesaj = provider_flow.add_credential(
        store,
        picker=_pick("openai"),
        ask_secret=lambda prompt: "sk-canli",
        on_saved=lambda ad, deger: uygulanan.append((ad, deger)),
    )

    assert uygulanan == [("OPENAI_API_KEY", "sk-canli")]
    assert "bu oturumda da etkin" in mesaj
    assert "sk-canli" not in mesaj


def test_wizard_vazgecilirse_on_saved_cagrilmaz(tmp_path):
    cagrildi = []

    provider_flow.add_credential(
        _store(tmp_path),
        picker=_pick("openai"),
        ask_secret=lambda prompt: "",
        on_saved=lambda ad, deger: cagrildi.append(ad),
    )

    assert cagrildi == []

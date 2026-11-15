"""Hata → eval taslağı hattı: kullanıcı düzeltmesi, tekrar ve başarısız tur taslağa döner.

Kayıtlar gerçek `TranscriptStore` ile yazılır: tur günlüğü biçimi değişirse bu test düşer.
"""

from __future__ import annotations

import json
from pathlib import Path

from evals.tasks import CriterionKind
from evals.taslak import TaslakKaynagi, taslak_kimligi, taslak_uret
from evals.taslak_maske import MAKS_METIN, maskele
from evals.taslak_olcut import dogrulama_komutu

from fusion_cli.cli.repl.transcript_store import TranscriptStore
from fusion_cli.core.events import (
    Channel,
    ErrorOccurred,
    FilesChanged,
    ModelCallFinished,
    ToolExecuted,
    ToolOutcome,
    TurnAnswered,
    TurnOutcome,
)
from fusion_cli.core.types import ModelResult

KOK = Path("/Users/ada/proje")
EV = Path("/Users/ada")
SIMDI = 1_800_000_000.0


def _kayitlar(tmp_path: Path, adimlar) -> list[dict[str, object]]:
    store = TranscriptStore(tmp_path, KOK, conversation_id="oturum-1")
    for adim in adimlar:
        if isinstance(adim, str):
            store.record_user(adim)
        else:
            store.handle(adim)
    satirlar = store.events_path.read_text(encoding="utf-8").splitlines()
    return [json.loads(satir) for satir in satirlar]


def _cevap(metin: str = "Tamam, yaptım."):
    return TurnAnswered(channel=Channel.MAIN, text=metin)


def _uret(kayitlar, **kw):
    return taslak_uret(kayitlar, kok=KOK, ev=EV, simdi=SIMDI, **kw)


def test_duzeltme_onceki_istegi_goreve_cevirir(tmp_path):
    kayitlar = _kayitlar(
        tmp_path,
        [
            "login.py içindeki parola kontrolünü düzelt",
            _cevap(),
            TurnOutcome(status="completed", elapsed_s=3.0),
            "hayır, yanlış yaptın; testler hâlâ düşüyor",
        ],
    )
    (taslak,) = _uret(kayitlar)
    assert taslak.kaynak is TaslakKaynagi.DUZELTME
    assert taslak.request == "login.py içindeki parola kontrolünü düzelt"
    assert any("yanlış yaptın" in satir for satir in taslak.kanit)
    assert taslak.id == taslak_kimligi(taslak.request)


def test_geri_alma_istegi_taslak_olur(tmp_path):
    kayitlar = _kayitlar(
        tmp_path,
        ["README'yi baştan yaz ve bölümleri sırala", _cevap(), "bunu geri al lütfen"],
    )
    (taslak,) = _uret(kayitlar)
    assert taslak.kaynak is TaslakKaynagi.GERI_ALMA


def test_ayni_istegin_tekrari_ilk_gonderimi_taslak_yapar(tmp_path):
    kayitlar = _kayitlar(
        tmp_path,
        [
            "ana sayfadaki başlığı mavi yap ve ortala",
            _cevap(),
            "ana sayfadaki başlığı mavi yap ve ortala!",
        ],
    )
    (taslak,) = _uret(kayitlar)
    assert taslak.kaynak is TaslakKaynagi.TEKRAR
    assert taslak.request == "ana sayfadaki başlığı mavi yap ve ortala"


def test_kismi_ve_basarisiz_tur_taslak_olur(tmp_path):
    kayitlar = _kayitlar(
        tmp_path,
        [
            "tüm modülleri yeni arayüze taşı",
            TurnOutcome(status="partial", elapsed_s=9.0),
            "veritabanı şemasını sıfırdan kur",
            TurnOutcome(status="failed", elapsed_s=2.0),
        ],
    )
    kaynaklar = {taslak.kaynak for taslak in _uret(kayitlar)}
    assert kaynaklar == {TaslakKaynagi.KISMI_TUR, TaslakKaynagi.BASARISIZ_TUR}


def test_yalniz_saglayici_arizasiyla_dusen_tur_taslak_olmaz(tmp_path):
    sonuc = ModelResult(name="m", model="x", text="", latency_ms=1, ok=False, error="429 limit")
    kayitlar = _kayitlar(
        tmp_path,
        [
            "büyük bir yeniden düzenleme yap lütfen",
            ModelCallFinished(role="m", result=sonuc),
            TurnOutcome(status="failed", elapsed_s=1.0),
        ],
    )
    assert _uret(kayitlar) == ()


def test_olumcul_hata_ile_dusen_tur_taslak_olur(tmp_path):
    kayitlar = _kayitlar(
        tmp_path,
        [
            "büyük bir yeniden düzenleme yap lütfen",
            ErrorOccurred(message="araç çöktü", fatal=True),
            TurnOutcome(status="failed", elapsed_s=1.0),
        ],
    )
    (taslak,) = _uret(kayitlar)
    assert any("teşhis" in satir for satir in taslak.kanit)


def test_soruya_verilen_hayir_duzeltme_degildir(tmp_path):
    kayitlar = _kayitlar(
        tmp_path,
        [
            "sunucuyu yeniden başlatayım mı diye sor",
            _cevap("Yeniden başlatayım mı?"),
            "hayır olmasın",
        ],
    )
    assert _uret(kayitlar) == ()


def test_tek_basina_kisa_mesaj_ve_ilk_mesaj_duzeltme_sayilmaz(tmp_path):
    assert _uret(_kayitlar(tmp_path, ["hayır yanlış bu", "tamam"])) == ()


def test_duzeltme_zinciri_duzeltmeyi_goreve_cevirmez(tmp_path):
    kayitlar = _kayitlar(
        tmp_path,
        [
            "login.py parola kontrolünü düzelt",
            _cevap(),
            "hayır yanlış oldu",
            _cevap(),
            "hayır yine olmadı",
        ],
    )
    taslaklar = _uret(kayitlar)
    assert [taslak.request for taslak in taslaklar] == ["login.py parola kontrolünü düzelt"]


def test_ayni_istek_iki_kanittan_gelirse_tek_taslakta_birlesir(tmp_path):
    kayitlar = _kayitlar(
        tmp_path,
        [
            "tüm modülleri yeni arayüze taşı",
            TurnOutcome(status="partial", elapsed_s=9.0),
            "hayır yanlış yaptın",
        ],
    )
    (taslak,) = _uret(kayitlar)
    assert taslak.kaynak is TaslakKaynagi.DUZELTME  # güçlü kanıt kazanır
    assert any("tur sonucu: partial" in satir for satir in taslak.kanit)


def test_sonra_filtresi_eski_mesajlari_atlar(tmp_path):
    kayitlar = _kayitlar(tmp_path, ["tüm modülleri yeni arayüze taşı", "hayır yanlış yaptın"])
    zaman = float(kayitlar[1]["timestamp"])  # type: ignore[arg-type]
    assert _uret(kayitlar, sonra=zaman + 10) == ()
    assert len(_uret(kayitlar, sonra=zaman - 10)) == 1


def test_maks_taslak_sinirlar(tmp_path):
    adimlar: list = []
    for numara in range(5):
        adimlar += [f"{numara} numaralı farklı bir iş yap ve bitir", TurnOutcome("failed", 1.0)]
    assert len(_uret(_kayitlar(tmp_path, adimlar), maks=2)) == 2


# --------------------------------------------------------------------------- #
# Ölçüt çıkarımı: yalnız kanıttan
# --------------------------------------------------------------------------- #


def _kabuk(komut: str):
    return ToolExecuted(
        name="run_shell", args={"command": komut}, outcome=ToolOutcome.FAILED, output="1 failed"
    )


def test_dogrulama_komutundan_exit_code_olcutu_cikar(tmp_path):
    kayitlar = _kayitlar(
        tmp_path,
        [
            "login testlerini geçir ve düzelt",
            _kabuk("python -m pytest -q tests/test_login.py"),
            _cevap(),
            "hayır, yanlış",
        ],
    )
    (taslak,) = _uret(kayitlar)
    assert taslak.olcut is not None
    assert taslak.olcut.kind is CriterionKind.EXIT_CODE
    assert taslak.olcut.command == "python -m pytest -q tests/test_login.py"
    assert taslak.olcut.expected_exit_code == 0


def test_dosya_degisikliginden_zayif_olcut_cikar(tmp_path):
    kayitlar = _kayitlar(
        tmp_path,
        [
            "başlık rengini değiştir lütfen",
            FilesChanged(paths=(f"{KOK}/src/baslik.css",)),
            "hayır, yanlış",
        ],
    )
    (taslak,) = _uret(kayitlar)
    assert taslak.olcut is not None
    assert taslak.olcut.kind is CriterionKind.FILE_CHANGED
    assert taslak.olcut.expected_path == "src/baslik.css"  # proje yolu göreli


def test_kanit_yoksa_olcut_uydurulmaz(tmp_path):
    kayitlar = _kayitlar(tmp_path, ["başlık rengini değiştir lütfen", _cevap(), "hayır, yanlış"])
    (taslak,) = _uret(kayitlar)
    assert taslak.olcut is None
    assert "ölçütü kabulde sen ver" in taslak.olcut_notu


def test_tehlikeli_komut_olcut_olamaz():
    assert dogrulama_komutu("pytest -q") == "pytest -q"
    assert dogrulama_komutu("pytest && rm -rf /") is None
    assert dogrulama_komutu("pytest $(curl x)") is None
    assert dogrulama_komutu("rm -rf build") is None
    assert dogrulama_komutu("pytest 'eksik") is None


# --------------------------------------------------------------------------- #
# Maskeleme
# --------------------------------------------------------------------------- #


def test_maske_sir_ve_yollari_temizler():
    metin = (
        "token=sk-abcdefghijklmnopqrstuvwx dosya /Users/ada/proje/src/a.py "
        "ve /Users/ada/Belgeler/x.txt ve ada@example.com"
    )
    temiz = maskele(metin, kok=KOK, ev=EV)
    assert "sk-abcdefghijklmnopqrstuvwx" not in temiz
    assert "ada@example.com" not in temiz
    assert "/Users/" not in temiz
    assert "src/a.py" in temiz
    assert "~/Belgeler/x.txt" in temiz


def test_maske_kardes_dizini_bozmaz():
    temiz = maskele("bak /Users/ada/proje-2/a.py ve /Users/ada/proje/b.py", kok=KOK, ev=EV)
    assert temiz == "bak ~/proje-2/a.py ve b.py"


def test_maske_uzun_metni_kirpar():
    assert len(maskele("a" * 10_000, kok=KOK, ev=EV)) <= MAKS_METIN


def test_taslak_isteginde_sir_yoktur(tmp_path):
    kayitlar = _kayitlar(
        tmp_path,
        [
            "anahtar api_key=sk-abcdefghijklmnopqrstuvwx ve /Users/ada/proje/a.py'yi düzelt",
            _cevap(),
            "hayır yanlış yaptın",
        ],
    )
    (taslak,) = _uret(kayitlar)
    assert "sk-abcdefghijklmnopqrstuvwx" not in taslak.request
    assert "/Users/" not in taslak.request

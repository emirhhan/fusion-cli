"""Sesli yanıtın sözleşmesi.

Fusion'ın konuşması BEDAVA ve ÇEVRİMDIŞI olmalı: işletim sisteminin kendi
sentezleyicisi kullanılır. macOS'ta `say`, Windows'ta PowerShell. Model
indirme, API anahtarı ve ağ erişimi YOKTUR.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from fusion_cli.appserver.voice import speak_argv, turkish_voice


def test_macos_turkce_sesle_konusur():
    """macOS'ta Türkçe ses `Yelda`dır ve sistemde kuruludur (ölçüldü)."""
    argv = speak_argv("Darwin", "Merhaba", voice="Yelda")

    assert argv[0] == "say"
    assert "-v" in argv and "Yelda" in argv
    assert argv[-1] == "Merhaba"


def test_windows_powershell_sentezleyicisini_kullanir():
    argv = speak_argv("Windows", "Merhaba", voice=None)

    assert argv[0].casefold().startswith("powershell")
    birlesik = " ".join(argv)
    assert "SpeechSynthesizer" in birlesik
    assert "Merhaba" in birlesik


def test_desteklenmeyen_platform_sessizce_gecilmez():
    with pytest.raises(ValueError):
        speak_argv("Linux", "Merhaba", voice=None)


def test_metin_kabuga_kacis_karakteri_sizdirmaz():
    """Metin kullanıcıdan/modelden gelir; komut enjeksiyonuna kapalı olmalı."""
    argv = speak_argv("Darwin", 'ba"; rm -rf /; echo "', voice="Yelda")

    # Argüman listesi kabuktan geçmez; metin TEK argüman olarak kalır.
    assert argv[-1] == 'ba"; rm -rf /; echo "'
    assert len(argv) == 4


def test_turkce_ses_secimi_kurulu_olanlardan_yapilir():
    """Ses adı uydurulmaz: sistemde kurulu Türkçe seslerden seçilir."""
    assert turkish_voice(("Yelda tr_TR", "Alex en_US")) == "Yelda"
    assert turkish_voice(("Alex en_US",)) is None


def test_en_iyi_ses_secilir_compact_son_caredir():
    """Ses seçimi KALİTEYE göre yapılır; ilk bulunan alınmaz.

    Apple'ın `voice.compact` ailesi en düşük kademedir ve robotik duyulur —
    kullanıcı bunu bildirdi. `ttsbundle`/`premium`/`enhanced` aileleri belirgin
    biçimde daha doğaldır ve ücretsiz indirilebilir. Kurulu en iyi ses seçilir;
    compact yalnız başka seçenek yoksa kullanılır.
    """
    from fusion_cli.appserver.voice import best_voice

    kurulu = (
        ("Yelda", "tr-TR", "com.apple.voice.compact.tr-TR.Yelda"),
        ("Cem", "tr-TR", "com.apple.ttsbundle.Cem"),
    )
    assert best_voice(kurulu) == "Cem"

    yalniz_compact = (("Yelda", "tr-TR", "com.apple.voice.compact.tr-TR.Yelda"),)
    assert best_voice(yalniz_compact) == "Yelda"

    assert best_voice(()) is None


def test_daha_iyi_ses_kuruluysa_kullanici_bilgilendirilir():
    """Daha iyi ses varken sessizce kötüsüyle konuşmak yanlış olurdu."""
    from fusion_cli.appserver.voice import upgrade_hint

    yalniz_compact = (("Yelda", "tr-TR", "com.apple.voice.compact.tr-TR.Yelda"),)
    ipucu = upgrade_hint(yalniz_compact)
    assert ipucu is not None and "Cem" in ipucu

    iyi_ses_var = (("Cem", "tr-TR", "com.apple.ttsbundle.Cem"),)
    assert upgrade_hint(iyi_ses_var) is None


def test_piper_komutu_hizli_ve_ayarlanabilir():
    """Piper parametreleri sabit değil, ölçülerek seçilmiş varsayılanlardır.

    Kullanıcı "biraz hızlandıralım, robotik olsa da olur" dedi: bu yüzden
    varsayılan `length_scale` 1.0'ın ALTINDA (daha hızlı) seçildi.
    """
    from fusion_cli.appserver.voice import PIPER_DEFAULTS, piper_argv

    assert PIPER_DEFAULTS["length_scale"] < 1.0

    argv = piper_argv("/tmp/model.onnx", "/tmp/cikti.wav", PIPER_DEFAULTS)

    assert "--length-scale" in argv
    assert "--sentence-silence" in argv
    assert argv[argv.index("-m") + 1] == "/tmp/model.onnx"
    assert argv[argv.index("-f") + 1] == "/tmp/cikti.wav"


def test_piper_modeli_yoksa_sistem_sesine_dusulur_ve_sebep_soylenir():
    """Model indirilmemişse sessizce susmak yanlış olurdu."""
    from fusion_cli.appserver.voice import engine_for

    motor, sebep = engine_for(piper_model=None, system_voice="Cem")
    assert motor == "sistem"
    assert sebep and "indir" in sebep.casefold()

    motor, sebep = engine_for(piper_model="/tmp/model.onnx", system_voice="Cem")
    assert motor == "piper" and sebep is None

    motor, sebep = engine_for(piper_model=None, system_voice=None)
    assert motor is None and sebep


def test_piper_model_yolu_kullanici_verisinde_durur(tmp_path, monkeypatch):
    """Model uygulama paketine DEĞİL, kullanıcı veri dizinine iner.

    Paketin içine yazmak imzayı bozar ve güncellemede silinir; kullanıcı
    verisi ise güncellemeden etkilenmez.
    """
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)
    yol = voice.piper_model_path()

    assert yol.name.endswith(".onnx")
    assert tmp_path in yol.parents


def test_model_indirme_adresi_bilinen_depodan_gelir():
    from fusion_cli.appserver.voice import piper_download_urls

    onnx, config = piper_download_urls()
    for adres in (onnx, config):
        assert adres.startswith("https://huggingface.co/rhasspy/piper-voices/")
        assert "tr/tr_TR/dfki" in adres
    assert onnx.endswith(".onnx")
    assert config.endswith(".onnx.json")


def test_model_indirme_ilerlemeyi_bildirir(tmp_path, monkeypatch):
    """İndirme sessiz olmaz: 60 MB'lık dosyada kullanıcı ilerlemeyi görmeli."""
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)

    class SahteYanit:
        headers: ClassVar[dict[str, str]] = {"Content-Length": "8"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _n=None):
            # Yapılandırma dosyası `read()` ile argümansız okunur; sahte de
            # ikisini birden karşılamalı.
            veri = getattr(self, "_kalan", b"12345678")
            self._kalan = b""
            return veri

    monkeypatch.setattr(voice, "_open_url", lambda _u: SahteYanit())
    olaylar: list[dict] = []

    sonuc = voice.download_piper_model(olaylar.append)

    assert sonuc["ok"] is True
    assert voice.piper_model_path().is_file()
    assert olaylar, "ilerleme hiç bildirilmedi"
    assert olaylar[-1]["toplam"] > 0


def test_model_yarim_inerse_bozuk_dosya_birakilmaz(tmp_path, monkeypatch):
    """Yarım dosya "kurulu" sanılırsa Piper her açılışta çöker."""
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)

    def patlayan(_url):
        raise OSError("ağ koptu")

    monkeypatch.setattr(voice, "_open_url", patlayan)
    sonuc = voice.download_piper_model(lambda _e: None)

    assert sonuc["ok"] is False
    assert not voice.piper_model_path().exists()


def test_durum_yanlis_yukseltme_onermez(tmp_path, monkeypatch):
    """Kurulu olan sesi "indir" demek kullanıcıyı yanıltır.

    Ölçüldü: Cem kuruluyken ve motor Piper'ken durum yine "Cem'i indir" diyordu.
    Öneri yalnız GERÇEKTEN uygulanabilir olduğunda çıkar.
    """
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)
    model = voice.piper_model_path()
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"sahte model")

    durum = voice.status()

    assert durum["motor"] == "piper"
    # Piper devredeyken sistem sesi önerisi anlamsızdır.
    assert durum["yukseltme"] is None


def test_ses_ayarlari_hizi_ve_robotikligi_degistirir(tmp_path, monkeypatch):
    """Kullanıcı hızı ve robotikliği kendi ayarlayabilmeli.

    Piper'da hız `length_scale` ile TERS orantılıdır: küçük değer hızlı okur.
    Robotiklik ise hece süresi değişkenliğidir (`noise_w_scale`); küçüldükçe
    ses mekanikleşir.
    """
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)

    sonuc = voice.save_settings({"hiz": 1.4, "robotik": 0.8})

    assert sonuc["ok"] is True
    ayarlar = voice.load_settings()
    assert ayarlar["length_scale"] < voice.PIPER_DEFAULTS["length_scale"]
    assert ayarlar["noise_w_scale"] < voice.PIPER_DEFAULTS["noise_w_scale"]


def test_ses_ayarlari_araligin_disina_cikamaz(tmp_path, monkeypatch):
    """Uç değerler sesi anlaşılmaz yapar; aralık kırpılır."""
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)

    voice.save_settings({"hiz": 99.0, "robotik": -5.0})
    ayarlar = voice.load_settings()

    assert voice.HIZ_ARALIGI[0] <= ayarlar["hiz"] <= voice.HIZ_ARALIGI[1]
    assert 0.0 <= ayarlar["robotik"] <= 1.0


def test_kendi_ses_modeli_dosyasi_kullanilabilir(tmp_path, monkeypatch):
    """Kullanıcı kendi Piper modelini gösterebilmeli."""
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)
    kendi = tmp_path / "kendi-ses.onnx"
    kendi.write_bytes(b"onnx")
    # Piper modeli yapılandırmasıyla birlikte geçerlidir.
    (tmp_path / "kendi-ses.onnx.json").write_text("{}", encoding="utf-8")

    sonuc = voice.save_settings({"model": str(kendi)})

    assert sonuc["ok"] is True
    assert voice.active_model_path() == kendi


def test_olmayan_ses_modeli_kabul_edilmez(tmp_path, monkeypatch):
    """Var olmayan dosyayı kaydetmek, konuşmayı sessizce bozardı."""
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)

    sonuc = voice.save_settings({"model": str(tmp_path / "yok.onnx")})

    assert sonuc["ok"] is False
    assert "bulunamadı" in sonuc["metin"]


def test_ayarlar_bozuksa_varsayilana_dusulur(tmp_path, monkeypatch):
    """Elle bozulmuş ayar dosyası konuşmayı engellememelidir."""
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)
    voice.settings_path().parent.mkdir(parents=True, exist_ok=True)
    voice.settings_path().write_text("{bozuk", encoding="utf-8")

    ayarlar = voice.load_settings()

    assert ayarlar["length_scale"] == voice.PIPER_DEFAULTS["length_scale"]


def test_ses_modeli_onnx_olmali(tmp_path, monkeypatch):
    """Kullanıcının konuşma kaydı bir ses MODELİ değildir.

    Arayüzde "kendi ses dosyam" yazıyordu ve dosya seçici her şeyi kabul
    ediyordu; WAV yükleyen kullanıcı ses klonlandı sanıyor, Piper sonradan
    hata veriyordu. Kabul edilen tek şey Piper'ın `.onnx` modelidir.
    """
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)
    kayit = tmp_path / "sesim.wav"
    kayit.write_bytes(b"RIFF")

    sonuc = voice.save_settings({"model": str(kayit)})

    assert sonuc["ok"] is False
    assert ".onnx" in sonuc["metin"]


def test_ses_modeli_yapilandirma_dosyasini_da_ister(tmp_path, monkeypatch):
    """Piper modeli tek başına çalışmaz; yanındaki `.onnx.json` şarttır."""
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)
    model = tmp_path / "kendi.onnx"
    model.write_bytes(b"onnx")

    sonuc = voice.save_settings({"model": str(model)})

    assert sonuc["ok"] is False
    assert "yapılandırma" in sonuc["metin"]


def test_yapilandirmasi_olan_model_kabul_edilir(tmp_path, monkeypatch):
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)
    model = tmp_path / "kendi.onnx"
    model.write_bytes(b"onnx")
    (tmp_path / "kendi.onnx.json").write_text("{}", encoding="utf-8")

    sonuc = voice.save_settings({"model": str(model)})

    assert sonuc["ok"] is True
    assert voice.active_model_path() == model

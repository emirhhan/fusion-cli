"""Sesli yanıtın sözleşmesi.

Fusion'ın konuşması BEDAVA ve ÇEVRİMDIŞI olmalı: işletim sisteminin kendi
sentezleyicisi kullanılır. macOS'ta `say`, Windows'ta PowerShell. Model
indirme, API anahtarı ve ağ erişimi YOKTUR.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
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


def test_yalniz_fusionun_baslattigi_ses_sureci_beklenir_ve_durdurulur(monkeypatch):
    """Talk mikrofonu ancak gerçek TTS bittiğinde yeniden açabilmeli."""
    from fusion_cli.appserver import voice

    class FakeProcess:
        pid = 4242

        def __init__(self):
            self.waited = False
            self.terminated = False

        def wait(self, timeout=None):
            self.waited = True
            return 0

        def poll(self):
            return None if not self.terminated else 0

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.terminated = True

    process = FakeProcess()
    monkeypatch.setattr(voice, "active_model_path", lambda: voice.Path("/olmayan/model.onnx"))
    monkeypatch.setattr(voice, "installed_voice_records", lambda: ())
    monkeypatch.setattr(voice.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(voice.subprocess, "Popen", lambda *_a, **_kw: process)

    result = voice.speak("Merhaba")
    assert voice.wait_for_speech(result["pid"]) is True
    assert process.waited is True

    # Tamamlanmış/başkasına ait PID için sistemdeki genel `say` süreçleri
    # öldürülmez; Fusion yalnız kendi sahip olduğu süreci yönetir.
    assert voice.wait_for_speech(9999) is False


def test_ses_turu_kaydedilir_beklenir_ve_gecici_dosyasi_temizlenir(tmp_path, monkeypatch):
    """Tur sahibi normal bitiste kaydi ve Piper'in gecici WAV dosyasini birakir."""
    from fusion_cli.appserver import voice

    class FakeProcess:
        pid = 4545

        def wait(self, timeout=None):
            return 0

    temporary = tmp_path / "turn.wav"
    temporary.write_bytes(b"audio")
    monkeypatch.setattr(voice.subprocess, "Popen", lambda *_a, **_kw: FakeProcess())

    voice._register_speech_process(FakeProcess(), temporary, turn_id="turn-normal")

    assert voice.wait_for_speech("turn-normal") is True
    assert not temporary.exists()
    assert voice.stop("turn-normal") == {"ok": True, "durduruldu": False, "tur_id": "turn-normal"}


def test_ses_turu_iki_kez_durduruldugunda_oynatici_yalniz_bir_kez_kesilir(tmp_path, monkeypatch):
    """Idempotent iptal ayni oyuncuya ikinci terminate gondermez."""
    from fusion_cli.appserver import voice

    class FakeProcess:
        pid = 4646

        def __init__(self):
            self.terminate_count = 0

        def poll(self):
            return None

        def terminate(self):
            self.terminate_count += 1

        def wait(self, timeout=None):
            return 0

    process = FakeProcess()
    temporary = tmp_path / "interrupted.wav"
    temporary.write_bytes(b"audio")
    monkeypatch.setattr(voice.subprocess, "Popen", lambda *_a, **_kw: process)
    voice._register_speech_process(process, temporary, turn_id="turn-interrupted")

    first = voice.stop("turn-interrupted")
    second = voice.stop("turn-interrupted")

    assert first == {"ok": True, "durduruldu": True, "tur_id": "turn-interrupted"}
    assert second == {"ok": True, "durduruldu": False, "tur_id": "turn-interrupted"}
    assert process.terminate_count == 1
    assert not temporary.exists()


def test_ses_oynaticisi_500_msde_durmazsa_zorla_kapatilir(monkeypatch):
    """Barge-in iptal onayi urun sozlesmesindeki 500 ms ust sinirini asmaz."""
    from fusion_cli.appserver import voice

    class SlowProcess:
        pid = 4747

        def __init__(self):
            self.timeouts: list[float | None] = []
            self.killed = False

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            self.timeouts.append(timeout)
            if not self.killed:
                raise voice.subprocess.TimeoutExpired("player", timeout)
            return 0

        def kill(self):
            self.killed = True

    process = SlowProcess()
    monkeypatch.setattr(voice.subprocess, "Popen", lambda *_a, **_kw: process)
    voice._register_speech_process(process, turn_id="turn-slow")

    assert voice.stop("turn-slow")["ok"] is True
    assert 0 < process.timeouts[0] <= 0.5
    assert process.killed is True


def test_ses_iptali_terminate_ve_kill_icin_tek_500_ms_butce_kullanir(tmp_path, monkeypatch):
    """Kill sonrasi ikinci 500 ms bekleme toplam iptal suresini ikiye katlamamali."""
    from fusion_cli.appserver import voice

    class DeadlineProcess:
        pid = 4848

        def __init__(self):
            self.wait_timeouts: list[float | None] = []
            self.killed = False
            self.reaped = threading.Event()

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            self.wait_timeouts.append(timeout)
            if not self.killed:
                raise voice.subprocess.TimeoutExpired("player", timeout)
            self.reaped.set()
            return 0

        def kill(self):
            self.killed = True

    clock = iter((100.0, 100.0, 100.5, 100.5))
    monkeypatch.setattr(
        voice,
        "time",
        SimpleNamespace(monotonic=lambda: next(clock, 100.5)),
        raising=False,
    )
    process = DeadlineProcess()
    temporary = tmp_path / "deadline.wav"
    temporary.write_bytes(b"audio")
    voice._register_speech_process(process, temporary, turn_id="turn-deadline")

    result = voice.stop("turn-deadline")

    requested = [value for value in process.wait_timeouts if value is not None]
    assert sum(requested) <= 0.5
    assert result == {"ok": True, "durduruldu": True, "tur_id": "turn-deadline"}
    assert process.killed is True
    assert process.reaped.wait(1), "zorla kapatilan cocuk surec reap edilmedi"
    assert not temporary.exists()


def test_ardisik_speak_onceki_oynaticiyi_yenisini_spawn_etmeden_durdurur(monkeypatch):
    from fusion_cli.appserver import voice

    live = 0
    max_live = 0
    next_pid = 5000

    class Player:
        def __init__(self):
            nonlocal live, max_live, next_pid
            next_pid += 1
            self.pid = next_pid
            self.stopped = False
            live += 1
            max_live = max(max_live, live)

        def poll(self):
            return 0 if self.stopped else None

        def terminate(self):
            nonlocal live
            self.stopped = True
            live -= 1

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(voice, "active_model_path", lambda: voice.Path("/olmayan/model.onnx"))
    monkeypatch.setattr(voice, "installed_voice_records", lambda: ())
    monkeypatch.setattr(voice.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(voice.subprocess, "Popen", lambda *_a, **_kw: Player())
    voice.stop()

    first = voice.speak("birinci")
    second = voice.speak("ikinci")

    assert first["tur_id"] != second["tur_id"]
    assert max_live <= 1
    assert list(voice._SPEECH_PROCESSES) == [second["tur_id"]]
    voice.stop()


def test_eszamanli_speak_cagrilari_tek_canli_oynaticida_serilestirilir(monkeypatch):
    from fusion_cli.appserver import voice

    state_lock = threading.Lock()
    start = threading.Barrier(3)
    live = 0
    max_live = 0
    next_pid = 5100

    class Player:
        def __init__(self):
            nonlocal live, max_live, next_pid
            with state_lock:
                next_pid += 1
                self.pid = next_pid
                self.stopped = False
                live += 1
                max_live = max(max_live, live)
            time.sleep(0.03)

        def poll(self):
            return 0 if self.stopped else None

        def terminate(self):
            nonlocal live
            with state_lock:
                if not self.stopped:
                    self.stopped = True
                    live -= 1

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(voice, "active_model_path", lambda: voice.Path("/olmayan/model.onnx"))
    monkeypatch.setattr(voice, "installed_voice_records", lambda: ())
    monkeypatch.setattr(voice.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(voice.subprocess, "Popen", lambda *_a, **_kw: Player())
    voice.stop()
    results: list[dict] = []

    def worker(text: str):
        start.wait()
        results.append(voice.speak(text))

    threads = [threading.Thread(target=worker, args=(text,)) for text in ("bir", "iki")]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join()

    assert len(results) == 2
    assert max_live <= 1
    assert len(voice._SPEECH_PROCESSES) == 1
    assert next(iter(voice._SPEECH_PROCESSES)) in {result["tur_id"] for result in results}
    voice.stop()


def test_basarisiz_ses_sureci_tamamlanmis_sayilmaz(monkeypatch):
    from fusion_cli.appserver import voice

    class FailedProcess:
        pid = 4343

        def wait(self, timeout=None):
            return 7

    process = FailedProcess()
    voice._register_speech_process(process)  # type: ignore[arg-type]

    assert voice.wait_for_speech(process.pid) is False


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

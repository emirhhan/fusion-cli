"""Sesli yanıtın sözleşmesi.

Fusion'ın konuşması BEDAVA ve ÇEVRİMDIŞI olmalı: işletim sisteminin kendi
sentezleyicisi kullanılır. macOS'ta `say`, Windows'ta PowerShell. Model
indirme, API anahtarı ve ağ erişimi YOKTUR.
"""

from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

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
    monkeypatch.setattr(voice, "ema_ready", lambda: False)
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
    """Tur sahibi normal bitiste kaydi ve ses motorunun gecici WAV dosyasini birakir."""
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
    for _ in range(100):
        if not temporary.exists():
            break
        time.sleep(0.001)
    assert not temporary.exists(), "gecici dosya confirmed reap sonrasinda temizlenmedi"


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

    monkeypatch.setattr(voice, "ema_ready", lambda: False)
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

    monkeypatch.setattr(voice, "ema_ready", lambda: False)
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


def test_reaper_cikisi_dogrulayana_kadar_yeni_oynatici_spawn_edilmez(monkeypatch):
    from fusion_cli.appserver import voice

    release_reaper = threading.Event()
    reaped = threading.Event()
    popen_count = 0
    live = 0
    max_live = 0

    class StubbornPlayer:
        pid = 5201

        def __init__(self):
            nonlocal live, max_live
            live += 1
            max_live = max(max_live, live)

        def poll(self):
            return 0 if reaped.is_set() else None

        def terminate(self):
            return None

        def kill(self):
            return None

        def wait(self, timeout=None):
            nonlocal live
            if timeout is not None:
                raise voice.subprocess.TimeoutExpired("player", timeout)
            release_reaper.wait(1)
            live -= 1
            reaped.set()
            return 0

    class NextPlayer:
        pid = 5202

        def __init__(self):
            nonlocal live, max_live
            live += 1
            max_live = max(max_live, live)
            self.stopped = False

        def poll(self):
            return 0 if self.stopped else None

        def terminate(self):
            nonlocal live
            self.stopped = True
            live -= 1

        def wait(self, timeout=None):
            return 0

    stubborn = StubbornPlayer()

    def popen(*_args, **_kwargs):
        nonlocal popen_count
        popen_count += 1
        return stubborn if popen_count == 1 else NextPlayer()

    clock = iter((200.0, 200.0, 200.5, 200.5))
    monkeypatch.setattr(
        voice,
        "time",
        SimpleNamespace(monotonic=lambda: next(clock, 200.5)),
    )
    monkeypatch.setattr(voice, "ema_ready", lambda: False)
    monkeypatch.setattr(voice, "installed_voice_records", lambda: ())
    monkeypatch.setattr(voice.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(voice.subprocess, "Popen", popen)
    voice.stop()

    first = voice.speak("birinci")
    assert first["ok"] is True
    assert voice.stop(first["tur_id"])["ok"] is True

    busy = voice.speak("ikinci")

    assert busy["ok"] is False
    assert busy["mesgul"] is True
    assert "yeniden deneyin" in str(busy["metin"])
    assert popen_count == 1
    assert max_live == 1

    release_reaper.set()
    assert reaped.wait(1)
    for _ in range(100):
        resumed = voice.speak("ucuncu")
        if resumed.get("ok") is True:
            break
        time.sleep(0.001)
    else:
        raise AssertionError("reaper sonrasi TTS sahipligi serbest birakilmadi")

    assert popen_count == 2
    assert max_live == 1
    voice.stop()


def test_kilitli_gecici_ses_dosyasi_reap_sonrasina_ertelenir(monkeypatch):
    from fusion_cli.appserver import voice

    release_reaper = threading.Event()
    reaped = threading.Event()

    class LockedCleanup:
        def __init__(self):
            self.deleted = threading.Event()
            self.attempts = 0

        def unlink(self, *, missing_ok=False):
            self.attempts += 1
            if not reaped.is_set():
                raise PermissionError("dosya oynatici tarafindan kilitli")
            self.deleted.set()

    class LockedPlayer:
        pid = 5301

        def poll(self):
            return 0 if reaped.is_set() else None

        def terminate(self):
            return None

        def kill(self):
            return None

        def wait(self, timeout=None):
            if timeout is not None:
                raise voice.subprocess.TimeoutExpired("player", timeout)
            release_reaper.wait(1)
            reaped.set()
            return 0

    clock = iter((300.0, 300.0, 300.5, 300.5))
    monkeypatch.setattr(
        voice,
        "time",
        SimpleNamespace(monotonic=lambda: next(clock, 300.5)),
    )
    cleanup = LockedCleanup()
    voice.stop()
    voice._register_speech_process(  # type: ignore[arg-type]
        LockedPlayer(), cleanup, turn_id="turn-locked"
    )

    result = voice.stop("turn-locked")

    assert result == {"ok": True, "durduruldu": True, "tur_id": "turn-locked"}
    assert not cleanup.deleted.is_set()
    release_reaper.set()
    assert reaped.wait(1)
    assert cleanup.deleted.wait(1), "kilitli gecici dosya reap sonrasinda silinmedi"
    assert cleanup.attempts >= 1


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


def test_ema_yoksa_sistem_sesine_dusulur_ve_sebep_soylenir():
    """Model dosyaları eksikse sessizce kötü sesle konuşulmaz; sebep söylenir."""
    from fusion_cli.appserver.voice import engine_for

    motor, sebep = engine_for(ema_available=False, system_voice="Cem")
    assert motor == "sistem" and sebep

    motor, sebep = engine_for(ema_available=True, system_voice="Cem")
    assert motor == "ema" and sebep is None

    motor, sebep = engine_for(ema_available=False, system_voice=None)
    assert motor is None and sebep


def test_ema_modeli_pakete_dahildir_ve_eksiksizdir():
    from fusion_cli.appserver import ema_synthesis, voice

    assert voice.ema_ready() is True
    for name in ema_synthesis.MODEL_FILES:
        assert (ema_synthesis.model_directory() / name).is_file()


def test_model_indirme_istegi_gomulu_model_icin_zaten_der(monkeypatch):
    from fusion_cli.appserver import voice

    assert voice.download_voice_model(lambda _event: None) == {"ok": True, "zaten": True}
    monkeypatch.setattr(voice, "ema_ready", lambda: False)
    sonuc = voice.download_voice_model(lambda _event: None)
    assert sonuc["ok"] is False and "eksik" in sonuc["metin"]


def test_durum_ema_devredeyken_sistem_sesi_onermez(tmp_path, monkeypatch):
    """EMA kuruluyken durum "başka ses indir" demez; motor ve ses adı EMA'dır."""
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)
    monkeypatch.setattr(voice, "installed_voice_records", lambda: (("Cem", "tr-TR", "Cem"),))
    durum = voice.status()
    assert durum["motor"] == "ema" and durum["ses"] == voice.EMA_VOICE_NAME
    assert durum["model_kurulu"] is True and durum["yukseltme"] is None
    assert durum["ayar"] == {"hiz": 1.0}


def test_ses_hizi_kaydedilir_ve_araligin_disina_cikamaz(tmp_path, monkeypatch):
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)
    assert voice.save_settings({"hiz": 1.4})["ok"] is True
    assert voice.load_settings() == {"hiz": 1.4}
    voice.save_settings({"hiz": 99.0})
    assert voice.load_settings()["hiz"] == voice.HIZ_ARALIGI[1]
    voice.save_settings({"hiz": -3})
    assert voice.load_settings()["hiz"] == voice.HIZ_ARALIGI[0]
    assert voice.save_settings({"hiz": "hızlı"})["ok"] is False
    assert voice.save_settings("bozuk")["ok"] is False


def test_ayarlar_bozuksa_varsayilana_dusulur(tmp_path, monkeypatch):
    """Elle bozulmuş JSON konuşmayı susturmaz."""
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)
    (tmp_path / "voice-settings.json").write_text("{bozuk", encoding="utf-8")
    assert voice.load_settings() == {"hiz": 1.0}


def test_eski_robotik_ve_model_alanlari_yok_sayilir(tmp_path, monkeypatch):
    """Eski ayar dosyası okunur; desteklenmeyen alanlar sessizce geri yazılmaz."""
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path)
    (tmp_path / "voice-settings.json").write_text(
        json.dumps({"hiz": 1.2, "robotik": 0.9, "model": "/x/y.onnx"}), encoding="utf-8"
    )
    assert voice.load_settings() == {"hiz": 1.2}
    voice.save_settings({"hiz": 1.1})
    assert json.loads((tmp_path / "voice-settings.json").read_text()) == {"hiz": 1.1}


def test_sistem_ses_listesi_bosluklu_kaliteli_adi_korur(monkeypatch):
    """Enhanced adı bölününce Türkçe ses yanlışlıkla katalogdan düşmemeli."""
    from fusion_cli.appserver import voice

    monkeypatch.setattr(voice.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(voice.shutil, "which", lambda _name: "/usr/bin/say")
    monkeypatch.setattr(
        voice.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout=(
                "Cem                 tr_TR    # Merhaba.\nCem (Enhanced)      tr_TR    # Merhaba.\n"
            )
        ),
    )
    records = voice.installed_voice_records()
    assert ("Cem (Enhanced)", "tr-TR", "Cem (Enhanced)") in records
    assert voice.best_voice(records) == "Cem (Enhanced)"

"""CLI `/voice` yerel dikte (P-072).

Ölçüldü (31 Ekim): CLI/REPL'de ses yoktu; çekirdekte STT yoktu (yalnız masaüstü
arayüzü `fusion-listen` yardımcısını kullanıyordu). Testler gerçek mikrofona ya da
macOS izin diyaloğuna dokunmaz: yardımcının JSON satır sözleşmesini taklit eden sahte
betik kullanılır.
"""

from __future__ import annotations

import json
import stat
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from rich.console import Console

from fusion_cli.cli.repl import voice_command
from fusion_cli.cli.repl.commands import ASYNC_COMMANDS, build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.trust import without_execution_settings
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools import stt
from fusion_cli.ui import messages

from .fakes import make_config


def _sahte_dinleyici(tmp_path: Path, olaylar: list[dict], *, sonra_bekle: bool = True) -> Path:
    """Olayları basan, sonra SIGTERM'e kadar bekleyen yürütülebilir betik."""
    betik = tmp_path / "sahte-listen"
    satirlar = "\n".join(json.dumps(olay, ensure_ascii=False) for olay in olaylar)
    govde = (
        f"#!{sys.executable}\n"
        "import sys, time\n"
        f"open({str(tmp_path / 'dil.txt')!r}, 'w').write((sys.argv[1:] or [''])[0])\n"
        f"sys.stdout.write({satirlar!r} + '\\n')\n"
        "sys.stdout.flush()\n" + ("time.sleep(60)\n" if sonra_bekle else "")
    )
    betik.write_text(govde, encoding="utf-8")
    betik.chmod(betik.stat().st_mode | stat.S_IXUSR)
    return betik


def _olay(tur: str, metin: str = "", **ek: object) -> dict:
    return {"tur": tur, "metin": metin, "guven": None, "speech_ms": 0, "segment": 1, **ek}


async def test_dinleme_son_metni_doner_kismiyi_bildirir_ve_sureci_kapatir(tmp_path):
    betik = _sahte_dinleyici(
        tmp_path,
        [
            _olay("hazir", "tr-TR"),
            _olay("ses-basladi"),
            _olay("kismi", "testleri"),
            _olay("son", "testleri çalıştır"),
            _olay("ses-bitti"),
        ],
    )
    kismi: list[str] = []

    sonuc = await stt.listen_once([str(betik), "tr-TR"], on_partial=kismi.append, max_listen_s=10)

    assert sonuc.text == "testleri çalıştır"
    assert kismi == ["testleri"]
    assert (tmp_path / "dil.txt").read_text() == "tr-TR"


async def test_dikte_kapali_hatasi_eyleme_donuk_mesaj_verir(tmp_path):
    betik = _sahte_dinleyici(
        tmp_path, [_olay("hata", "Siri and Dictation are disabled", kod="dikte_kapali")]
    )
    with pytest.raises(stt.SpeechToTextError, match="Dikte"):
        await stt.listen_once([str(betik)], max_listen_s=10)


async def test_ses_gelmezse_bos_metinle_biter(tmp_path):
    betik = _sahte_dinleyici(tmp_path, [_olay("hazir", "tr-TR")])
    sonuc = await stt.listen_once([str(betik)], no_speech_timeout_s=0.3, max_listen_s=10)
    assert sonuc.text == ""


async def test_son_sonrasi_ses_bitti_gelmezse_kisa_sessizlikte_metni_doner(tmp_path):
    """Ölçüldü (31 Ekim): 'son' sonrası bekleme süresizdi; 'ses-bitti' üretmeyen yardımcıda
    (fusion-listen kısmi-durdu yolu) dikte 90 sn bekleyip tanınan metni atıyordu."""
    import time

    betik = _sahte_dinleyici(tmp_path, [_olay("ses-basladi"), _olay("son", "lint koş")])
    basla = time.monotonic()

    sonuc = await stt.listen_once([str(betik)], max_listen_s=10, final_silence_s=0.3)

    assert sonuc.text == "lint koş"
    assert time.monotonic() - basla < 5


async def test_ust_sure_dolunca_toplanan_metin_kaybolmaz(tmp_path):
    betik = _sahte_dinleyici(tmp_path, [_olay("ses-basladi"), _olay("son", "derle")])

    sonuc = await stt.listen_once([str(betik)], max_listen_s=0.5, final_silence_s=30)

    assert sonuc.text == "derle"


def test_dinleyici_ayardan_sonra_kurulu_uygulamadan_bulunur(tmp_path):
    klasor = tmp_path / "Resources"
    klasor.mkdir()
    (klasor / stt.LISTENER_NAME).write_text("x")
    assert stt.find_listener("", dirs=(tmp_path / "yok", klasor)) == klasor / stt.LISTENER_NAME
    assert stt.find_listener("", dirs=(tmp_path / "yok",)) is None
    assert stt.find_listener(str(tmp_path / "olmayan-komut"), dirs=(klasor,)) is None


def _state(tmp_path: Path, listener: str) -> ReplState:
    config = make_config()
    config = replace(config, runtime=replace(config.runtime, voice_listener=listener))
    return ReplState(config=config, memory=null_memory(), root=tmp_path, home=tmp_path)


async def test_voice_metni_bir_sonraki_isteme_yazar(tmp_path):
    betik = _sahte_dinleyici(tmp_path, [_olay("son", "readme'yi güncelle"), _olay("ses-bitti")])
    state = _state(tmp_path, str(betik))
    console = Console(record=True, width=120)

    await voice_command.run(state, "", console)

    assert state.take_pending_input() == "readme'yi güncelle"
    assert state.pending_task == ""
    assert "İsteme yazıldı" in console.export_text()


async def test_voice_gonder_metni_tur_olarak_hazirlar(tmp_path):
    betik = _sahte_dinleyici(tmp_path, [_olay("son", "lint düzelt"), _olay("ses-bitti")])
    state = _state(tmp_path, str(betik))

    await voice_command.run(state, "gonder", Console(record=True))

    assert state.take_pending() == ("lint düzelt", state.pending_mode)
    assert state.pending_input == ""


async def test_tanıyıcı_yoksa_acik_hata_verir(tmp_path, monkeypatch):
    monkeypatch.setattr(stt, "listener_dirs", lambda: (tmp_path / "yok",))
    state = _state(tmp_path, "")
    console = Console(record=True, width=200)

    await voice_command.run(state, "", console)

    assert "Yerel konuşma tanıma bulunamadı" in console.export_text()
    assert state.pending_input == "" and state.pending_task == ""


def test_voice_asenkron_komut_masaustunde_mikrofonu_onerir(tmp_path):
    command = build_registry().get("voice")
    assert command is not None and "voice" in ASYNC_COMMANDS
    assert command.handler(_state(tmp_path, ""), "") == messages.VOICE_DESKTOP_HINT
    assert build_registry().get("dikte") is command


def test_guvenilmeyen_proje_configi_dinleyici_komutu_tasiyamaz():
    temiz, dusen = without_execution_settings({"runtime": {"voice_listener": "/tmp/kotu"}})
    assert "runtime.voice_listener" in dusen
    assert "voice_listener" not in temiz["runtime"]  # type: ignore[operator]


def test_kaynak_agacindaki_yardimci_yolu_depoyu_gosterir():
    # Kaynak ağacı adayı `app/src-tauri/resources` olmalı (geliştirici kurulumu).
    assert stt.listener_dirs()[-1].parts[-3:] == ("app", "src-tauri", "resources")
    assert stt.listener_dirs()[0].is_absolute()


async def test_tui_voice_metni_giris_kutusuna_yazar(tmp_path):
    from fusion_cli.cli.repl.tui_loop import _TuiSession

    betik = _sahte_dinleyici(tmp_path, [_olay("son", "planı göster"), _olay("ses-bitti")])
    session = _TuiSession(_state(tmp_path, str(betik)))

    await session._command("/voice")

    assert session.tui._input.text == "planı göster"


async def test_satir_ici_istem_dikte_metniyle_acilir(tmp_path):
    from fusion_cli.cli.repl import loop

    state = _state(tmp_path, "")
    state.pending_input = "taslak"
    gelen: list[str] = []

    class _Okuyucu:
        mode = state.approval

        async def prompt(self, default: str = "") -> str:
            gelen.append(default)
            return "x"

    assert await loop._read_line(_Okuyucu(), state) == "x"  # type: ignore[arg-type]
    assert gelen == ["taslak"] and state.pending_input == ""

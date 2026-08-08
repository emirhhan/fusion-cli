"""Ink-benzeri TUI alt-chrome — durum biçimi ve tuş yönlendirmesi (TTY'siz)."""

from __future__ import annotations

import asyncio

from fusion_cli.cli.repl.tui import FusionTui, format_status


def test_durum_satiri_modu_ve_ipucunu_icerir():
    html = format_status("auto", "agent")

    assert "auto" in html
    assert "agent" in html
    assert "shift-tab" in html and "esc" in html


def test_riskli_mod_farkli_renkte():
    """security modu auto'dan farklı renk almalı (göze çarpsın)."""
    assert format_status("security", "agent") != format_status("auto", "agent")


def _tui():
    olaylar: dict[str, object] = {"submit": None, "interrupt": 0, "exit": 0, "cycle": 0}

    def _submit(text: str) -> None:
        olaylar["submit"] = text

    def _bump(anahtar: str):
        def _f() -> None:
            olaylar[anahtar] = int(olaylar[anahtar]) + 1  # type: ignore[arg-type]

        return _f

    tui = FusionTui(
        on_submit=_submit,
        on_interrupt=_bump("interrupt"),
        on_exit=_bump("exit"),
        on_cycle_mode=_bump("cycle"),
    )
    return tui, olaylar


def test_enter_satiri_submit_callback_ine_verir():
    tui, olaylar = _tui()

    class _Buf:
        text = "merhaba dünya"

    silindi = tui._accept(_Buf())

    assert olaylar["submit"] == "merhaba dünya"
    # False dönmeli: prompt_toolkit tamponu temizlesin.
    assert silindi is False


def test_calisma_satiri_ayarlanip_temizlenir():
    tui, _ = _tui()

    tui.set_work_source(lambda: "hazırlanıyor…")
    assert tui._work_now() == "hazırlanıyor…"

    tui.clear_work()
    assert tui._work_now() == ""


def test_durum_ayarlanir():
    tui, _ = _tui()

    tui.set_status("plan", "fusion")

    assert "plan" in tui._status_html and "fusion" in tui._status_html


def test_application_tam_ekran():
    """Tam-ekran: girdi en alta pinli, resize'da kopya olmaz (çıkışta transcript dökülür)."""
    tui, _ = _tui()

    assert tui.application.full_screen is True


# --- Yapıştırma katlama ------------------------------------------------------- #


async def test_kisa_yapistirma_oldugu_gibi_girer():
    # async: buffer.insert_text çalışan bir event loop bekler (üretimde app loop var).
    tui, _ = _tui()

    tui._fold_paste("kısa metin")

    assert tui._input.buffer.text == "kısa metin"
    assert not tui._pastes  # katlama yok


async def test_uzun_cok_satirli_yapistirma_katlanir_ve_gonderimde_acilir():
    tui, olaylar = _tui()
    uzun = "\n".join(f"satır {i}" for i in range(20))

    tui._fold_paste(uzun)

    # Girdi tek satırlık yer tutucu; tam metin değil.
    assert tui._input.buffer.text != uzun
    assert "\n" not in tui._input.buffer.text
    assert "20 satır" in tui._input.buffer.text

    # Gönderimde yer tutucu tam metne geri açılır.
    class _Buf:
        text = tui._input.buffer.text

    tui._accept(_Buf())
    assert olaylar["submit"] == uzun


async def test_cok_uzun_tek_satir_da_katlanir():
    tui, _ = _tui()
    uzun = "x" * 700

    tui._fold_paste(uzun)

    assert "700 karakter" in tui._input.buffer.text


def _press(tui, *keys: str) -> None:
    """Verilen tuş dizisine bağlı işleyiciyi sahte olayla çağır."""
    kb = tui.application.key_bindings
    for binding in kb.bindings:
        adlar = tuple(str(getattr(k, "value", k)) for k in binding.keys)
        if adlar == keys:
            binding.handler(None)
            return
    raise AssertionError(f"bağ bulunamadı: {keys}")


def test_esc_interrupt_callback_ini_tetikler():
    tui, olaylar = _tui()

    _press(tui, "escape")

    assert olaylar["interrupt"] == 1


def test_ctrl_c_ve_ctrl_q_cikar_esc_keser_shift_tab_dondurur():
    """Kullanıcı isteği: Ctrl-C fusion'dan ÇIKAR; turu esc keser."""
    tui, olaylar = _tui()

    _press(tui, "c-c")
    _press(tui, "c-q")
    _press(tui, "s-tab")

    assert olaylar["exit"] == 2  # hem c-c hem c-q çıkışa gider
    assert olaylar["cycle"] == 1
    assert olaylar["interrupt"] == 0  # Ctrl-C artık kesme değil


# --- Modal (onay/soru) -------------------------------------------------------- #


async def test_await_confirm_e_ile_true():
    tui, _ = _tui()
    task = asyncio.ensure_future(tui.await_confirm())
    await asyncio.sleep(0)
    assert tui._mode == "confirm"

    _press(tui, "e")

    assert await task is True
    assert tui._mode == "idle"


async def test_await_confirm_esc_ile_false():
    tui, olaylar = _tui()
    task = asyncio.ensure_future(tui.await_confirm())
    await asyncio.sleep(0)

    _press(tui, "escape")

    assert await task is False
    # Modal esc'i turu KESMEZ; yalnızca onayı reddeder.
    assert olaylar["interrupt"] == 0


async def test_await_choice_ok_ve_enter_ile_secer():
    from fusion_cli.ui.picker import Choice

    tui, _ = _tui()
    secenekler = [Choice("a", "A"), Choice("b", "B"), Choice("c", "C")]
    task = asyncio.ensure_future(tui.await_choice("başlık", secenekler))
    await asyncio.sleep(0)
    assert tui._mode == "choice"

    _press(tui, "down")  # index 0 → 1 ("b")

    class _Buf:
        text = ""

    tui._accept(_Buf())  # Enter → seçili değeri döndür

    assert await task == "b"
    assert tui._mode == "idle"


async def test_await_choice_esc_ile_iptal_none():
    from fusion_cli.ui.picker import Choice

    tui, _ = _tui()
    task = asyncio.ensure_future(tui.await_choice("t", [Choice("a", "A")]))
    await asyncio.sleep(0)

    _press(tui, "escape")

    assert await task is None


async def test_await_text_enter_ile_metni_doner():
    tui, olaylar = _tui()
    task = asyncio.ensure_future(tui.await_text())
    await asyncio.sleep(0)
    assert tui._mode == "ask"

    class _Buf:
        text = "kullanıcı yanıtı"

    tui._accept(_Buf())

    assert await task == "kullanıcı yanıtı"
    # Soru modunda Enter turu BAŞLATMAZ.
    assert olaylar["submit"] is None


def test_onceki_transcript_yuklenir_ve_degisim_kaydedilir():
    snapshots: list[str] = []
    tui = FusionTui(
        on_submit=lambda _text: None,
        on_interrupt=lambda: None,
        on_exit=lambda: None,
        on_cycle_mode=lambda: None,
        initial_transcript="önceki kullanıcı\nönceki cevap\n",
        on_transcript_change=snapshots.append,
    )

    assert "önceki kullanıcı" in tui.transcript
    tui.console.print("yeni cevap")
    tui.sync_conversation()
    assert snapshots and "yeni cevap" in snapshots[-1]


def test_gecmise_bakarken_yeni_cikti_konumu_bozmaz(monkeypatch):
    monkeypatch.setattr("fusion_cli.cli.repl.tui._term_rows", lambda: 12)
    tui, _ = _tui()
    tui.console.print("\n".join(f"satır {i}" for i in range(30)))
    tui.sync_conversation()
    tui._scroll_by(6)
    before = tui._scroll

    tui.console.print("yeni 1\nyeni 2")
    tui.sync_conversation()

    assert tui._scroll >= before + 2
    assert tui._unread_lines >= 2
    tui._scroll_end()
    assert tui._scroll == 0 and tui._unread_lines == 0


def test_klavye_kaydirma_baglari_var():
    """Fare izleme kapandığı için kaydırma tamamen klavyeden yapılır."""
    tui, _ = _tui()
    names = {
        tuple(str(getattr(k, "value", k)) for k in binding.keys)
        for binding in tui.application.key_bindings.bindings
    }
    assert ("up",) in names
    assert ("down",) in names
    assert ("pageup",) in names
    assert ("pagedown",) in names
    assert ("home",) in names
    assert ("end",) in names
    # `\x1b[62~`/`\x1b[63~` gönderen terminaller için; bu diziler fare kipinden
    # BAĞIMSIZ ayrıştırılır, dolayısıyla bağlar ölü kod değildir.
    assert ("<scroll-up>",) in names
    assert ("<scroll-down>",) in names


def test_fare_izleme_kapali():
    """KARAR TERSİNE ÇEVRİLDİ: bu değer önce açıktı ve test onu kilitliyordu.

    Açıkken prompt_toolkit terminale `?1000h/?1003h/?1006h/?1015h` yazıp tüm
    fare olaylarını kendine alıyor, bu da terminalin KENDİ metin seçimini
    öldürüyordu — ekrandaki hiçbir şey fareyle kopyalanamıyordu (pty ile
    ölçüldü). Kopyalayabilmek tekerlekle kaydırmaktan daha temel bir beklenti.
    """
    tui, _ = _tui()

    assert bool(tui.application.mouse_support()) is False


# --- çalışma satırı: dönen kare -------------------------------------------- #


def test_calisma_satiri_donen_kare_ile_baslar():
    """Satır olaylarla besleniyor; kare olay gelmese bile turun sürdüğünü gösterir."""
    from fusion_cli.cli.repl.tui import SPINNER_FRAMES

    tui, _ = _tui()
    tui.set_work_source(lambda: "  düşünüyor…")

    parcalar = tui._work_fragments()

    assert len(parcalar) == 1
    assert parcalar[0][1].startswith(f" {SPINNER_FRAMES[0]}")
    assert "düşünüyor…" in parcalar[0][1]


def test_calisma_satiri_bosken_kare_cizilmez():
    tui, _ = _tui()

    assert tui._work_fragments() == []


def test_spinner_olay_loop_yokken_cokmez():
    """TTY dışı/test kurulumunda olay döngüsü yoktur; animasyon sessizce atlanır."""
    tui, _ = _tui()

    tui.set_work_source(lambda: "  düşünüyor…")  # get_running_loop() burada RuntimeError verir

    assert tui._spinner_task is None
    assert tui._work_fragments()  # satır yine de çizilir


async def test_spinner_kare_ilerletir_ve_durdurulunca_durur():
    from fusion_cli.cli.repl.tui import SPINNER_FRAMES, SPINNER_INTERVAL_S

    tui, _ = _tui()
    tui.set_work_source(lambda: "  düşünüyor…")
    assert tui._spinner_task is not None

    await asyncio.sleep(SPINNER_INTERVAL_S * 3.5)
    ilerledi = tui._spinner_frame
    assert ilerledi > 0
    assert tui._work_fragments()[0][1].startswith(
        f" {SPINNER_FRAMES[ilerledi % len(SPINNER_FRAMES)]}"
    )

    tui.clear_work()
    assert tui._spinner_task is None
    await asyncio.sleep(SPINNER_INTERVAL_S * 2)
    assert tui._spinner_frame == ilerledi  # durduktan sonra kare ilerlemez


async def test_spinner_iki_kez_baslatilmaz():
    tui, _ = _tui()
    tui.set_work_source(lambda: "  bir")
    ilk = tui._spinner_task
    tui.set_work_source(lambda: "  iki")

    assert tui._spinner_task is ilk


# --- tekerlek kipleri ------------------------------------------------------- #


def _kip_yakala(tui):
    """`_write_raw`ı sahteleyip yazılan kip dizilerini topla."""
    yazilan: list[str] = []
    tui._write_raw = yazilan.append  # type: ignore[method-assign]
    return yazilan


def test_tekerlek_kipleri_render_sonrasi_bir_kez_yazilir():
    """prompt_toolkit açılışta `?1l` yazıyor; kip ondan SONRA kurulmalı, yoksa geri alınır.

    Bu yüzden `after_render` kancasına bağlı ve bir kez yazılmalı — her render'da
    tekrar yazmak terminale gereksiz trafik demektir.
    """
    from fusion_cli.cli.repl.tui import _WHEEL_AS_ARROWS_ON

    tui, _ = _tui()
    yazilan = _kip_yakala(tui)

    tui._apply_wheel_modes()
    tui._apply_wheel_modes()

    assert yazilan == [_WHEEL_AS_ARROWS_ON]


def test_tekerlek_kipleri_after_render_e_bagli():
    tui, _ = _tui()

    assert tui._apply_wheel_modes in tui.application.after_render._handlers


def test_tekerlek_kipleri_cikista_geri_alinir():
    """Kipler terminal geneline yazılır; fusion çıkınca terminal normale dönmeli."""
    from fusion_cli.cli.repl.tui import _WHEEL_AS_ARROWS_OFF

    tui, _ = _tui()
    tui._apply_wheel_modes()
    yazilan = _kip_yakala(tui)

    tui.restore_wheel_modes()

    assert yazilan == [_WHEEL_AS_ARROWS_OFF]


def test_kurulmamis_kip_geri_alinmaz():
    """Hiç kurulmadıysa çıkışta yazma: dokunmadığımız kipi kapatmak yan etkidir."""
    tui, _ = _tui()
    yazilan = _kip_yakala(tui)

    tui.restore_wheel_modes()

    assert yazilan == []


def test_calisma_satiri_her_karede_kaynaktan_yeniden_okunur():
    """Metin değil, metni üreten şey tutulur.

    Regresyon: satır olay anında dondurulup saklanıyordu; içindeki süre bir
    sonraki olaya kadar değişmiyordu. Kaynak her karede yeniden okunmalı.
    """
    tui, _ = _tui()
    sayac = {"n": 0}

    def kaynak() -> str:
        sayac["n"] += 1
        return f"  tur {sayac['n']}"

    tui.set_work_source(kaynak)
    ilk = tui._work_fragments()[0][1]
    ikinci = tui._work_fragments()[0][1]

    assert ilk != ikinci, "aynı metin iki kez döndüyse kaynak yeniden okunmuyor"


# --- kaydırma her kipte açık olmalı ---------------------------------------- #
#
# Kullanıcı beş dakikalık bir turun ORTASINDA yukarı bakmak istedi ve
# yapamadı: kaydırma bağları `idle` filtresine bağlıydı. Turun ortasında
# geçmişe bakamamak, kaydırmanın hiç olmamasıyla aynı şey.


def _yeni_tui():
    return FusionTui(
        on_submit=lambda _text: None,
        on_interrupt=lambda: None,
        on_exit=lambda: None,
        on_cycle_mode=lambda: None,
    )


def _kayit_anahtarlari(tui):
    """Bağlı tüm tuş dizilerini düz metin olarak çıkar."""
    return {
        " ".join(str(getattr(key, "value", key)) for key in binding.keys)
        for binding in tui.application.key_bindings.bindings
    }


def test_cakismayan_kaydirma_kisayollari_bagli():
    anahtarlar = _kayit_anahtarlari(_yeni_tui())

    # Ok tuşu geçmiş için ayrıldı; kaydırmanın çakışmayan karşılığı olmalı.
    assert any("s-up" in a for a in anahtarlar)
    assert any("s-down" in a for a in anahtarlar)
    assert any("c-u" in a for a in anahtarlar)


def test_pageup_hala_bagli():
    assert any("pageup" in a for a in _kayit_anahtarlari(_yeni_tui()))

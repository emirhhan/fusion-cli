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

    tui.set_work("hazırlanıyor…")
    assert tui._work_text == "hazırlanıyor…"

    tui.clear_work()
    assert tui._work_text == ""


def test_durum_ayarlanir():
    tui, _ = _tui()

    tui.set_status("plan", "fusion")

    assert "plan" in tui._status_html and "fusion" in tui._status_html


def test_application_full_screen_degil():
    """Normal tampon: alternatif ekran YOK → scrollback korunur."""
    tui, _ = _tui()

    assert tui.application.full_screen is False


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


def test_ctrl_c_interrupt_ctrl_q_exit_shift_tab_cycle():
    tui, olaylar = _tui()

    _press(tui, "c-c")
    _press(tui, "c-q")
    _press(tui, "s-tab")

    assert olaylar["interrupt"] == 1
    assert olaylar["exit"] == 1
    assert olaylar["cycle"] == 1


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

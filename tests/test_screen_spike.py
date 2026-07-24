"""SPIKE testleri (commit edilmez) — renkli konuşma çekirdeğinin headless kanıtı.

Renk×tekerlek davranışı yalnızca gerçek terminalde ölçülür; burada renkten
BAĞIMSIZ, headless doğrulanabilir mantığı sabitliyoruz: köprü renkli SGR üretir,
kaydırma ofseti sınırlanır, takip modu doğru geçiş yapar.
"""

from __future__ import annotations


def test_renkli_kopru_sgr_uretir():
    from fusion_cli.cli.repl.screen_spike import _RenkliKopru

    kopru = _RenkliKopru()
    kopru.console.print("[bold red]merhaba[/] dünya")
    delta = kopru.drain()

    # Renge-özgü SGR: bold(1) + red(31). Yalnızca "\x1b[ var mı" değil.
    assert "\x1b[1;31m" in delta
    assert "merhaba" in kopru.text


def test_kaydirma_sinirlanir_ve_takip_modu_gecis_yapar():
    from fusion_cli.cli.repl.screen_spike import _SpikeScreen

    ekran = _SpikeScreen()
    for i in range(20):
        ekran.bridge.console.print(f"satir-{i}")
    ekran.after_event()

    # Takip modu açık: alta yapışır (son satır görünür).
    assert ekran._follow is True
    assert ekran._scroll == ekran._satir_sayisi() - 1

    # Yukarı kaydır: takip kopar, ofset düşer.
    ekran._kaydir(-5)
    assert ekran._follow is False
    assert ekran._scroll == ekran._satir_sayisi() - 1 - 5

    # Üst sınır: 0'ın altına inmez.
    ekran._kaydir(-1000)
    assert ekran._scroll == 0

    # Alt sınıra dönünce takip yeniden açılır.
    ekran._kaydir(+1000)
    assert ekran._follow is True


def test_yeni_icerik_takip_modunda_alta_yapisir():
    from fusion_cli.cli.repl.screen_spike import _SpikeScreen

    ekran = _SpikeScreen()
    ekran.bridge.console.print("ilk")
    ekran.after_event()
    ekran._kaydir(-100)  # yukarı çık, takip kopsun
    assert ekran._follow is False

    # Kullanıcı yukarıdayken yeni içerik gelince ZORLA alta çekilmemeli.
    onceki = ekran._scroll
    for i in range(10):
        ekran.bridge.console.print(f"yeni-{i}")
    ekran.after_event()
    assert ekran._follow is False
    assert ekran._scroll == onceki

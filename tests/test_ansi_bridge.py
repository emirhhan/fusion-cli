"""ANSI köprüsü — Rich çıktısını ANSI olarak biriktirir."""

from __future__ import annotations


def test_kopru_baslangicta_bostur():
    from fusion_cli.cli.repl.ansi_bridge import AnsiBridge

    kopru = AnsiBridge()
    assert kopru.text == ""
    assert kopru.drain() == ""


def test_drain_yeni_deltayi_dondurur_ve_biriktirir():
    from fusion_cli.cli.repl.ansi_bridge import AnsiBridge

    kopru = AnsiBridge()
    kopru.console.print("merhaba")
    delta1 = kopru.drain()
    assert "merhaba" in delta1
    assert kopru.text == delta1

    kopru.console.print("dünya")
    delta2 = kopru.drain()
    assert "dünya" in delta2
    assert "merhaba" not in delta2  # delta yalnızca YENİ kısım
    assert kopru.text == delta1 + delta2


def test_konsol_renk_uretir():
    from fusion_cli.cli.repl.ansi_bridge import AnsiBridge

    kopru = AnsiBridge()
    kopru.console.print("[red]hata[/red]")
    delta = kopru.drain()
    assert "\x1b[" in delta  # ANSI kaçış dizisi üretildi (force_terminal)

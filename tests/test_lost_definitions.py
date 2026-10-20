"""Üzerine yazma, hâlâ kullanılan tanımları silerse yakalanır."""

from __future__ import annotations

from fusion_cli.tools.lost_definitions import lost_definitions

_ILK = """const GameState = { MENU: 0, PLAYING: 1 };
const CONFIG = { width: 800 };
function clamp(v) { return v; }
class Player {}
"""


def test_devami_diye_ezilen_dosyada_kullanilan_tanimlar_bulunur():
    """dalga46: game.js ikinci write_file ile ezildi, GameState tanımı kayboldu."""
    ikinci = (
        "class Game {\n  constructor() { this.state = GameState.MENU; this.w = CONFIG.width; }\n}\n"
    )

    assert lost_definitions(_ILK, ikinci) == ("CONFIG", "GameState")


def test_kullanilmayan_ya_da_yeniden_tanimlanan_ad_bulgu_degildir():
    yeni = "let GameState = 1;\nconsole.log(GameState);\n"

    assert lost_definitions(_ILK, yeni) == ()


def test_python_tanimlari_da_izlenir():
    once = "def yardimci():\n    pass\n\nclass Model:\n    pass\n"
    sonra = "def main():\n    yardimci()\n"

    assert lost_definitions(once, sonra) == ("yardimci",)


def test_write_file_ezilen_tanimi_sonucta_soyler(tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools.files import write_file

    context = ToolContext(root=tmp_path)
    assert write_file({"path": "game.js", "content": _ILK}, context).ok
    sonuc = write_file(
        {"path": "game.js", "content": "class Game { s = GameState.MENU; }\n"}, context
    )

    assert sonuc.ok
    assert "GameState" in sonuc.output and "kayboldu" in sonuc.output

from fusion_cli.mcp_bridge.oauth_page import callback_page


def test_basari_sayfasi_stilli_ve_kacislanmis():
    sayfa = callback_page(ok=True, title="Bağlantı kuruldu", message="<b>x</b>")

    assert "<style>" in sayfa
    assert "Bağlantı kuruldu" in sayfa
    assert "&lt;b&gt;x&lt;/b&gt;" in sayfa
    assert "class='ok'" in sayfa


def test_hata_sayfasi_hata_durumunu_gosterir():
    sayfa = callback_page(ok=False, title="Bağlantı izni verilmedi", message="iptal")

    assert "class='error'" in sayfa
    assert "yeniden dene" in sayfa

"""Seçim ekranı — gezinme, renk dağılımı ve TTY olmayan ortam davranışı.

Gerçek terminal kurulmaz: saf fonksiyonlar (`fragments`, `row_colors`,
`resolve_plain`, `PickerState`) doğrudan test edilir.
"""

from __future__ import annotations

import io

from fusion_cli.ui import theme
from fusion_cli.ui.picker import Choice, PickerState, fragments, pick, resolve_plain, row_colors

SECENEKLER = (
    Choice("low", "low", "mevcut varsayılan"),
    Choice("medium", "medium", "bir üstü"),
    Choice("premium", "premium", "en iyi"),
)


# --------------------------------------------------------------------------- #
# Gezinme
# --------------------------------------------------------------------------- #


def test_imlec_asagi_yukari_hareket_eder():
    durum = PickerState(3)

    durum.move(1)

    assert durum.index == 1


def test_imlec_listenin_sonundan_basa_sarar():
    """Uçta takılmak yerine sarmak, uzun listede geri dönüşü kısaltır."""
    durum = PickerState(3, index=2)

    durum.move(1)

    assert durum.index == 0


def test_imlec_listenin_basindan_sona_sarar():
    durum = PickerState(3)

    durum.move(-1)

    assert durum.index == 2


# --------------------------------------------------------------------------- #
# Renk
# --------------------------------------------------------------------------- #


def test_gradyan_ilk_satirdan_son_satira_turuncudan_pembeye_gider():
    renkler = row_colors(5, gradient_rows=True)

    assert renkler[0] == theme.ACCENT
    assert renkler[-1] == theme.ACCENT_ALT


def test_gradyan_ara_satirlari_iki_ucun_arasindadir():
    """Geçiş yumuşak olmalı: ara satırlar iki uçtan da farklı olmalı."""
    renkler = row_colors(5, gradient_rows=True)

    assert len(set(renkler)) == 5
    assert theme.ACCENT not in renkler[1:]
    assert theme.ACCENT_ALT not in renkler[:-1]


def test_gradyan_kapaliyken_tek_vurgu_rengi_kullanilir():
    renkler = row_colors(4, gradient_rows=False)

    assert set(renkler) == {theme.ACCENT}


def test_tek_satirlik_gradyan_baslangic_rengini_verir():
    """Sıfıra bölme olmamalı."""
    assert row_colors(1, gradient_rows=True) == (theme.ACCENT,)


def test_gradyan_imzayla_ayni_karistiriciyi_kullanir():
    """İki farklı geçiş formülü olsaydı aynı ürün iki farklı renk gösterirdi."""
    renkler = row_colors(3, gradient_rows=True)

    assert renkler[1] == theme.blend(theme.ACCENT, theme.ACCENT_ALT, 0.5)


# --------------------------------------------------------------------------- #
# Çizim
# --------------------------------------------------------------------------- #


def test_secili_satir_isaretci_alir():
    parcalar = fragments(SECENEKLER, 1, row_colors(3, gradient_rows=True))

    metin = "".join(deger for _, deger in parcalar)
    assert f"{theme.ICON_PROMPT} medium" in metin


def test_secili_olmayan_satirda_isaretci_yoktur():
    parcalar = fragments(SECENEKLER, 1, row_colors(3, gradient_rows=True))

    metin = "".join(deger for _, deger in parcalar)
    assert f"{theme.ICON_PROMPT} low" not in metin


def test_isaretsiz_satirlarin_hizasi_korunur():
    """İşaretçi yerine boşluk konmazsa etiketler sola kayar ve imleç gezerken liste titrer."""
    parcalar = fragments(SECENEKLER, 0, row_colors(3, gradient_rows=True))

    satirlar = [satir for satir in "".join(v for _, v in parcalar).split("\n") if satir]
    sutunlar = {satir.index(secim.label) for satir, secim in zip(satirlar, SECENEKLER, strict=True)}
    assert sutunlar == {3}


def test_aciklamalar_cizilir():
    parcalar = fragments(SECENEKLER, 0, row_colors(3, gradient_rows=True))

    assert "mevcut varsayılan" in "".join(deger for _, deger in parcalar)


def test_secili_satir_kendi_gradyan_rengiyle_yazilir():
    renkler = row_colors(3, gradient_rows=True)

    parcalar = fragments(SECENEKLER, 2, renkler)

    assert any(renkler[2] in stil for stil, _ in parcalar)


def test_her_secenek_bir_satir_uretir():
    parcalar = fragments(SECENEKLER, 0, row_colors(3, gradient_rows=True))

    assert "".join(deger for _, deger in parcalar).count("\n") == len(SECENEKLER)


# --------------------------------------------------------------------------- #
# TTY olmayan ortam
# --------------------------------------------------------------------------- #


def test_duz_modda_numarayla_secilir():
    assert resolve_plain(SECENEKLER, "2") == "medium"


def test_duz_modda_adiyla_secilir():
    assert resolve_plain(SECENEKLER, "PREMIUM") == "premium"


def test_duz_modda_bos_cevap_vazgecmektir():
    assert resolve_plain(SECENEKLER, "  ") is None


def test_duz_modda_aralik_disi_numara_vazgecmektir():
    """Tekrar sormak boru hattında sonsuz döngü olurdu."""
    assert resolve_plain(SECENEKLER, "99") is None
    assert resolve_plain(SECENEKLER, "0") is None


def test_duz_modda_taninmayan_ad_vazgecmektir():
    assert resolve_plain(SECENEKLER, "boyle-bir-sey-yok") is None


def test_tty_yokken_liste_basilir_ve_secim_alinir(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda: "3")
    cikti = io.StringIO()

    secim = pick(SECENEKLER, title="Kademe seç", stream=cikti)

    assert secim == "premium"
    assert "Kademe seç" in cikti.getvalue()
    assert "3. premium" in cikti.getvalue()


def test_tty_yokken_eof_vazgecmektir(monkeypatch):
    """CI'da girdi olmadan çalıştırılırsa komut çökmemeli."""

    def _eof():
        raise EOFError

    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("builtins.input", _eof)

    assert pick(SECENEKLER, title="Kademe seç", stream=io.StringIO()) is None


def test_bos_liste_secim_uretmez():
    assert pick((), title="Kademe seç") is None


# --- Uzun listelerde görüş penceresi ----------------------------------------- #


def test_kisa_liste_tamamen_gosterilir():
    from fusion_cli.ui.picker import window_bounds

    assert window_bounds(total=5, selected=0, height=10) == (0, 5)


def test_uzun_listede_pencere_yuksekligi_kadar_gosterilir():
    """327 modelin tamamını basmak ekranı taşırır ve üst satırlar kaybolur."""
    from fusion_cli.ui.picker import window_bounds

    start, end = window_bounds(total=327, selected=0, height=10)

    assert (start, end) == (0, 10)


def test_pencere_secimi_takip_eder():
    from fusion_cli.ui.picker import window_bounds

    start, end = window_bounds(total=100, selected=50, height=10)

    assert start <= 50 < end
    assert end - start == 10


def test_liste_sonunda_pencere_tasmaz():
    from fusion_cli.ui.picker import window_bounds

    start, end = window_bounds(total=100, selected=99, height=10)

    assert end == 100
    assert start == 90


def test_pencere_yukselik_birden_kucukse_bile_calisir():
    from fusion_cli.ui.picker import window_bounds

    assert window_bounds(total=10, selected=3, height=0) == (3, 4)


def test_gorunmeyen_satirlar_sayisi_bildirilir():
    """Kullanıcı listenin devamı olduğunu bilmeli, yoksa hepsi bu sanır."""
    from fusion_cli.ui.picker import Choice, fragments, row_colors

    secenekler = tuple(Choice(f"m{i}", f"model-{i}") for i in range(50))
    renkler = row_colors(50, gradient_rows=False)

    metin = "".join(parca for _, parca in fragments(secenekler, 0, renkler, height=10))

    assert "model-0" in metin
    assert "model-49" not in metin, "pencere dışındaki satır basılmamalı"
    assert "40" in metin, "kaç satırın gizlendiği yazmalı"


def test_ortadayken_iki_yonde_de_gostergesi_olur():
    from fusion_cli.ui.picker import Choice, fragments, row_colors

    secenekler = tuple(Choice(f"m{i}", f"model-{i}") for i in range(50))
    renkler = row_colors(50, gradient_rows=False)

    metin = "".join(parca for _, parca in fragments(secenekler, 25, renkler, height=10))

    assert "↑" in metin and "↓" in metin


def test_yukseklik_verilmezse_eski_davranis_korunur():
    from fusion_cli.ui.picker import Choice, fragments, row_colors

    secenekler = tuple(Choice(f"m{i}", f"model-{i}") for i in range(50))
    renkler = row_colors(50, gradient_rows=False)

    metin = "".join(parca for _, parca in fragments(secenekler, 0, renkler))

    assert "model-49" in metin

"""Doğru çalışma dizinini bulup ÖNERME.

Kullanıcı fusion'ı yanlış klasörde açtı ve sidebar görevini oraya verdi. "Dosya
yok" demek doğruydu ama yetersizdi: doğru dizin bir üst klasörün hemen altındaydı
ve bunu bulmak tek bir dizin taramasından ibaret.

Dizin DEĞİŞTİRİLMEZ, önerilir. Kök kısıtı kullanıcının açtığı dizinin dışına
çıkılmasın diye vardır; "sanırım şunu kastettin" deyip başka bir projede dosya
düzenlemeye başlamak, halüsinasyon gören bir modelle birleştiğinde kabul edilemez
bir risktir.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.engines.agent.workspace_hint import find_workspace_for


def _proje(taban: Path, ad: str, yollar: tuple[str, ...]) -> Path:
    kok = taban / ad
    for yol in yollar:
        hedef = kok / yol
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text("x", encoding="utf-8")
    return kok


def test_kardes_dizindeki_proje_bulunur(tmp_path):
    yanlis = tmp_path / "fusion-cli"
    yanlis.mkdir()
    dogru = _proje(tmp_path, "GATE HOLDING", ("app/page.tsx", "components/Sidebar.tsx"))

    bulunan = find_workspace_for(("app/page.tsx", "components/Sidebar.tsx"), yanlis)

    assert bulunan == dogru


def test_bir_alt_katman_da_taranir(tmp_path):
    """Kullanıcının projeleri çoğu zaman ortak bir klasörün altındadır."""
    yanlis = tmp_path / "kod" / "fusion-cli"
    yanlis.mkdir(parents=True)
    dogru = _proje(tmp_path / "kod", "GATE HOLDING", ("app/page.tsx", "app/layout.tsx"))

    assert find_workspace_for(("app/page.tsx", "app/layout.tsx"), yanlis) == dogru


def test_birden_cok_aday_varsa_oneri_yapilmaz(tmp_path):
    """Belirsiz öneri, önerisizlikten kötüdür: yanlış projeye yönlendirir."""
    yanlis = tmp_path / "burasi"
    yanlis.mkdir()
    _proje(tmp_path, "proje-a", ("app/page.tsx", "app/layout.tsx"))
    _proje(tmp_path, "proje-b", ("app/page.tsx", "app/layout.tsx"))

    assert find_workspace_for(("app/page.tsx", "app/layout.tsx"), yanlis) is None


def test_tek_yol_yeterli_kanit_degildir(tmp_path):
    """`app/page.tsx` her Next.js projesinde var; tek eşleşme öneri için az."""
    yanlis = tmp_path / "burasi"
    yanlis.mkdir()
    _proje(tmp_path, "proje-a", ("app/page.tsx",))

    assert find_workspace_for(("app/page.tsx",), yanlis) is None


def test_hicbir_aday_yoksa_none(tmp_path):
    yanlis = tmp_path / "burasi"
    yanlis.mkdir()

    assert find_workspace_for(("app/page.tsx", "components/Sidebar.tsx"), yanlis) is None


def test_mutlak_yollar_yok_sayilir(tmp_path):
    yanlis = tmp_path / "burasi"
    yanlis.mkdir()
    _proje(tmp_path, "proje-a", ("app/page.tsx", "app/layout.tsx"))

    assert find_workspace_for(("/etc/passwd", "/tmp/x"), yanlis) is None


def test_kardesin_cocugu_da_bulunur(tmp_path):
    """Gerçek yerleşim: ~/Desktop/fusion-cli → ~/Desktop/projeler/GATE HOLDING.

    Hedef, kardeşin (`projeler`) çocuğuydu; yalnızca kardeşlere bakan bir tarama
    onu bulamıyordu.
    """
    yanlis = tmp_path / "fusion-cli"
    yanlis.mkdir()
    dogru = _proje(
        tmp_path / "projeler", "GATE HOLDING", ("app/page.tsx", "components/Sidebar.tsx")
    )

    bulunan = find_workspace_for(("app/page.tsx", "components/Sidebar.tsx"), yanlis)

    assert bulunan == dogru


def test_tarama_sinirli_kalir(tmp_path):
    """Derin arama büyük ağaçlarda turu bekletirdi; sınır aşılmamalı."""
    from fusion_cli.engines.agent.workspace_hint import MAX_CANDIDATES, _candidates

    yanlis = tmp_path / "burasi"
    yanlis.mkdir()
    for i in range(80):
        (tmp_path / f"k{i}" / f"c{i}").mkdir(parents=True)

    assert len(_candidates(yanlis)) <= MAX_CANDIDATES

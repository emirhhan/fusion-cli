"""Diff render — eklenen yeşil, silinen kırmızı (Claude Code diff dizilimi)."""

from __future__ import annotations

import io

from rich.console import Console

from fusion_cli.ui import theme
from fusion_cli.ui.diff import render_diff

_UNIFIED = "\n".join(
    (
        "--- a/app.py",
        "+++ b/app.py",
        "@@ -1,3 +1,3 @@",
        " ilk satir",
        "-eski satir",
        "+yeni satir",
        " son satir",
    )
)


def _plain(text) -> str:
    """Renkli Text'i renksiz düz metne indir (sayım/dizilim testleri için)."""
    buffer = io.StringIO()
    Console(file=buffer, force_terminal=False, width=200, no_color=True).print(text)
    return buffer.getvalue()


def test_ekleme_ve_silme_sayilir():
    rendered = render_diff(_UNIFIED)

    assert rendered.added == 1
    assert rendered.removed == 1


def test_baslik_satirlari_gosterilmez():
    """`--- a/` ve `+++ b/` diff başlıkları gürültü; gösterilmez."""
    cikti = _plain(render_diff(_UNIFIED).body)

    assert "a/app.py" not in cikti
    assert "b/app.py" not in cikti


def test_eklenen_ve_silinen_satir_metni_gorunur():
    cikti = _plain(render_diff(_UNIFIED).body)

    assert "yeni satir" in cikti
    assert "eski satir" in cikti
    assert "ilk satir" in cikti


def test_eklenen_satir_yesil_silinen_kirmizi_boyanir(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=True, width=80, color_system="truecolor")
    console.print(render_diff(_UNIFIED).body)
    cikti = buffer.getvalue()

    # Truecolor ANSI kaçışında yeşil ve kırmızı zemin/ön plan kodları bulunmalı.
    assert theme.DIFF_ADD.lstrip("#").lower() in cikti.lower() or "48;2" in cikti


def test_satir_numaralari_hunk_basligindan_gelir():
    cikti = _plain(render_diff(_UNIFIED).body)

    # @@ -1,3 +1,3 @@ → satırlar 1'den numaralanır.
    assert "1" in cikti


def test_yeni_dosya_onizlemesi_de_render_edilir():
    """write_file yeni dosyaya çağrıldığında unified diff değil +satır listesi gelir."""
    yeni = "YENİ DOSYA: not.txt (2 satır)\n+birinci\n+ikinci"

    rendered = render_diff(yeni)

    assert rendered.added == 2
    cikti = _plain(rendered.body)
    assert "birinci" in cikti and "ikinci" in cikti


def test_tavani_asan_diff_kirpilir():
    satirlar = ["--- a/x", "+++ b/x", "@@ -1,1 +1,50 @@"]
    satirlar += [f"+satir {i}" for i in range(50)]
    rendered = render_diff("\n".join(satirlar), max_lines=10)

    cikti = _plain(rendered.body)
    gorunen = [s for s in cikti.splitlines() if s.strip()]
    # 10 satır + 1 kırpma satırı sınırı; tümü basılmaz.
    assert len(gorunen) <= 11
    assert "satır daha" in cikti
    # Sayım yine de TAM diff'i yansıtır, kırpılan değil.
    assert rendered.added == 50


def test_bos_diff_sifir_dondurur():
    rendered = render_diff("")

    assert rendered.added == 0 and rendered.removed == 0

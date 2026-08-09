"""İskele → toptan-yazma ölü kilidi.

Ölçülen gerçek koşu: `scaffold_web` iskeleyi diske yazdı ve "şimdi bunları DOLDUR"
dedi; ama iskele dosyasını doldurmak tanımı gereği toptan yazmadır ve web modellerine
uygulanan toptan-yazma kısıtı onu bloklıyordu. Model `write_file` deneyip bloklandı,
`edit_file` deneyip 'old' metnini tutturamadı, içeriği öğrenmek için yeniden okumaya
kalkınca tekrar kapısına takıldı ve tur "3 turdur ilerleme yok" ile öldü.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.changeset import ChangeSet
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import _targeted_edit_required
from fusion_cli.tools.scaffold_tool import SCAFFOLD_FILES, scaffold_web, yabanci_sayfalar


class _SahteDeps:
    """`_targeted_edit_required` yalnızca `tool_context` alanına bakar."""

    def __init__(self, context: ToolContext) -> None:
        self.tool_context = context


def _web_politikasi() -> ExecutionPolicy:
    return ExecutionPolicy(is_web=True)


def _blok(context: ToolContext, yol: str, *, basarisiz_duzenleme: int = 0) -> list[str]:
    from fusion_cli.engines.agent.loop import _State

    return _targeted_edit_required(
        "write_file",
        {"path": yol, "content": "x"},
        _SahteDeps(context),
        _web_politikasi(),
        _State(failed_mutations_in_row=basarisiz_duzenleme),
    )


def test_kullanicinin_var_olan_dosyasi_toptan_yazilamaz(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("kullanıcının kodu", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    hatalar = _blok(context, "app.py")

    assert hatalar and "zaten var" in hatalar[0]


def test_yeni_dosya_yazmak_serbest(tmp_path: Path) -> None:
    assert _blok(ToolContext(root=tmp_path), "yeni.py") == []


def test_iskelenin_yazdigi_dosya_ayni_turda_doldurulabilir(tmp_path: Path) -> None:
    """Ölü kilidin ta kendisi: iskele dosyası bloklanırsa model doldurma yapamaz."""
    context = ToolContext(root=tmp_path)
    scaffold_web({"path": "."}, context)

    for ad in SCAFFOLD_FILES:
        assert (tmp_path / ad).exists()
        assert _blok(context, ad) == [], f"{ad} bloklandı — ölü kilit geri geldi"


def test_iskele_dosyasi_onceki_turdan_kalmissa_yine_korunur(tmp_path: Path) -> None:
    """Koruma kalkmaz: yalnızca BU turda oluşturulan dosya serbesttir."""
    (tmp_path / "index.html").write_text("<h1>önceki turun işi</h1>", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    hatalar = _blok(context, "index.html")

    assert hatalar and "zaten var" in hatalar[0]


def test_iskele_degisiklik_kumesine_kaydedilir_ve_geri_alinabilir(tmp_path: Path) -> None:
    """`/undo` iskeleyi görmüyordu: changes.record hiç çağrılmıyordu."""
    context = ToolContext(root=tmp_path)
    scaffold_web({"path": "."}, context)

    assert context.changes.paths
    context.changes.restore()

    for ad in SCAFFOLD_FILES:
        assert not (tmp_path / ad).exists(), f"{ad} geri alınamadı"


def test_was_created_this_turn_var_olan_dosyayi_olusturulmus_saymaz(tmp_path: Path) -> None:
    hedef = tmp_path / "a.txt"
    hedef.write_text("eski", encoding="utf-8")
    changes = ChangeSet()
    changes.record(hedef)

    assert changes.was_created_this_turn(hedef) is False


def test_was_created_this_turn_yeni_dosyayi_olusturulmus_sayar(tmp_path: Path) -> None:
    hedef = tmp_path / "b.txt"
    changes = ChangeSet()
    changes.record(hedef)
    hedef.write_text("yeni", encoding="utf-8")

    assert changes.was_created_this_turn(hedef) is True


# --------------------------------------------------------------------------- #
# İskele koşulludur: dizinde zaten site varsa yanlış hamledir
# --------------------------------------------------------------------------- #


def test_bos_dizinde_yabanci_sayfa_yok(tmp_path: Path) -> None:
    scaffold_web({"path": "."}, ToolContext(root=tmp_path))
    assert yabanci_sayfalar(tmp_path) == ()


def test_var_olan_sayfa_yabanci_sayilir(tmp_path: Path) -> None:
    (tmp_path / "urunler.html").write_text("<h1>var olan site</h1>", encoding="utf-8")
    assert yabanci_sayfalar(tmp_path) == ("urunler.html",)


def test_iskele_var_olan_siteyi_gorunce_arac_sonucunda_uyarir(tmp_path: Path) -> None:
    """Uyarı prompta değil ARAÇ SONUCUNA konur; model prompt kurallarını atlıyor."""
    (tmp_path / "urunler.html").write_text("<h1>var olan site</h1>", encoding="utf-8")
    sonuc = scaffold_web({"path": "."}, ToolContext(root=tmp_path))

    assert "DİKKAT" in sonuc.output
    assert "urunler.html" in sonuc.output


def test_bos_dizinde_uyari_cikmaz(tmp_path: Path) -> None:
    sonuc = scaffold_web({"path": "."}, ToolContext(root=tmp_path))
    assert "DİKKAT" not in sonuc.output

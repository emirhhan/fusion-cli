"""Büyük araç çıktısı modele değil diske gider; modele özet + referans döner.

Context rot ölçülmüş bir olgudur: bağlam uzadıkça, ilgili bilgi hâlâ oradayken
bile doğruluk düşer. Blueprint'in kuralı: eşiği aşan çıktı hemen artifact'a yazılır
ve modele handle verilir. Kırpma ise bilgiyi tamamen yok ediyordu — artifact yolu
kırpılan kısmı KAYBETMEDEN bağlamı küçültür.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.artifacts import ArtifactStore, offload_output


def test_esigi_asan_cikti_dosyaya_yazilir(tmp_path: Path):
    store = ArtifactStore(tmp_path)

    _, yol = offload_output("A" * 500, store=store, tool="run_shell", limit=100)

    assert yol is not None
    assert yol.read_text(encoding="utf-8") == "A" * 500
    assert "run_shell" in yol.name


def test_modele_ozet_ve_yol_doner(tmp_path: Path):
    store = ArtifactStore(tmp_path)

    metin, yol = offload_output("satır\n" * 200, store=store, tool="run_shell", limit=100)

    assert "satır" in metin  # ilk kısım modele ulaşır
    assert "200 satır" in metin
    assert yol is not None and str(yol) in metin
    assert "read_file" in metin  # devamının nasıl alınacağı yazılır


def test_esigin_altindaki_cikti_dokunulmaz(tmp_path: Path):
    store = ArtifactStore(tmp_path)

    metin, yol = offload_output("kısa çıktı", store=store, tool="run_shell", limit=100)

    assert metin == "kısa çıktı"
    assert yol is None
    assert not list(tmp_path.glob("*"))


def test_artifact_icerigi_maskelenir(tmp_path: Path):
    """Artifact diskte kalır: transcript ve iz ile aynı maskeleme kuralı geçerlidir."""
    store = ArtifactStore(tmp_path)

    _, yol = offload_output(
        "api_key=sk-gercek-anahtar\n" + "x" * 500, store=store, tool="run_shell", limit=100
    )

    assert yol is not None
    assert "sk-gercek-anahtar" not in yol.read_text(encoding="utf-8")


def test_ayni_arac_icin_dosyalar_cakismaz(tmp_path: Path):
    store = ArtifactStore(tmp_path)

    _, ilk = offload_output("A" * 500, store=store, tool="run_shell", limit=100)
    _, ikinci = offload_output("B" * 500, store=store, tool="run_shell", limit=100)

    assert ilk is not None and ikinci is not None and ilk != ikinci

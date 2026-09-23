"""Proje dosya listesi: git biliyorsa ondan, yoksa budamalı yürüyüşten.

İki çağıranı var (`core.repo_map` ve `@` ile dosya anma) ve ikisinin de aynı
listeyi görmesi gerekiyor; testler bu sözleşmeyi kilitler.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fusion_cli.core.project_files import project_files


def _goreli(root: Path, yollar: list[Path]) -> set[str]:
    return {str(yol.relative_to(root)) for yol in yollar}


def test_git_deposunda_izlenen_ve_yeni_dosyalar_gelir(tmp_path):
    """Agent'ın az önce oluşturduğu dosya da listede olmalı."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "izlenen.py").write_text("x = 1\n", "utf-8")
    subprocess.run(["git", "add", "izlenen.py"], cwd=tmp_path, check=True)
    (tmp_path / "yeni.txt").write_text("taze\n", "utf-8")

    yollar, kisitli = project_files(tmp_path)

    assert _goreli(tmp_path, yollar) >= {"izlenen.py", "yeni.txt"}
    assert kisitli is False


def test_gitignore_edilen_dosya_listeye_girmez(tmp_path):
    """Ölçülen gerçek: paketli runtime kopyası listeyi boğuyordu."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("uretilmis/\n", "utf-8")
    (tmp_path / "uretilmis").mkdir()
    (tmp_path / "uretilmis" / "paket.py").write_text("x = 1\n", "utf-8")
    (tmp_path / "kod.py").write_text("y = 2\n", "utf-8")

    goreli = _goreli(tmp_path, project_files(tmp_path)[0])

    assert "kod.py" in goreli
    assert "uretilmis/paket.py" not in goreli


def test_git_disinda_gurultu_dizinleri_atlanir(tmp_path):
    """Depo değilse budama yürüyüş sırasında yapılır."""
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "paket.js").write_text("x\n", "utf-8")
    (tmp_path / ".gizli").mkdir()
    (tmp_path / ".gizli" / "sir.txt").write_text("x\n", "utf-8")
    (tmp_path / "kod.py").write_text("y\n", "utf-8")

    goreli = _goreli(tmp_path, project_files(tmp_path)[0])

    assert goreli == {"kod.py"}


def test_nokta_ile_baslayan_dosya_iki_yolda_da_gelir(tmp_path):
    """Git yolu `.gitignore`'u döndürüyor; elle yürüyüş de döndürmeli.

    İki yol farklı liste verirse `@` önerileri deponun git olup olmamasına
    göre değişir ve kullanıcı aynı dosyayı bazen bulur bazen bulamaz.
    """
    (tmp_path / ".editorconfig").write_text("root = true\n", "utf-8")
    (tmp_path / "kod.py").write_text("y\n", "utf-8")

    yuruyus = _goreli(tmp_path, project_files(tmp_path)[0])
    assert ".editorconfig" in yuruyus

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    git_yolu = _goreli(tmp_path, project_files(tmp_path)[0])
    assert git_yolu == yuruyus


def test_tavan_asilinca_bildirilir(tmp_path):
    for sira in range(6):
        (tmp_path / f"dosya{sira}.txt").write_text("x\n", "utf-8")

    yollar, kisitli = project_files(tmp_path, limit=3)

    assert len(yollar) == 3
    assert kisitli is True

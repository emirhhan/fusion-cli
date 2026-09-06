"""İzole çalışma alanı: aynı görevi birden çok kez denemenin ön koşulu.

8. madde (paralel deneme + kanıtla seçim) bir adımı N kez denemeyi ister; bu, her
denemenin BİRBİRİNİ görmeyen bir kopyada çalışmasını gerektirir. Aksi halde ikinci
deneme birincinin yarım bıraktığı dosyaların üstüne yazar ve "hangi aday kazandı"
sorusu anlamsızlaşır.

İzolasyon git'e BAĞLI DEĞİLDİR: proje git olmayabilir, dosyalar untracked olabilir
ve kullanıcının bekleyen değişiklikleri bulunabilir. Git varsa worktree kullanılır
(ucuzdur), yoksa dizin kopyalanır.
"""

from __future__ import annotations

import subprocess

from fusion_cli.core.workspace import IsolatedWorkspace, isolate


def _git_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "kod.py").write_text("deger = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "ilk"],
        cwd=tmp_path,
        check=True,
    )
    return tmp_path


def test_git_olmayan_projede_dizin_kopyalanir(tmp_path):
    (tmp_path / "kod.py").write_text("deger = 1\n", encoding="utf-8")

    with isolate(tmp_path, name="deneme-1") as alan:
        assert isinstance(alan, IsolatedWorkspace)
        assert (alan.root / "kod.py").read_text(encoding="utf-8") == "deger = 1\n"
        (alan.root / "kod.py").write_text("deger = 2\n", encoding="utf-8")

    # Kopyadaki değişiklik ASIL projeye sızmaz: seçim yapılmadan hiçbir aday kazanmaz.
    assert (tmp_path / "kod.py").read_text(encoding="utf-8") == "deger = 1\n"


def test_git_projesinde_worktree_kullanilir(tmp_path):
    kok = _git_repo(tmp_path)

    with isolate(kok, name="deneme-2") as alan:
        assert alan.uses_worktree
        assert (alan.root / "kod.py").is_file()
        assert alan.root != kok


def test_iki_deneme_birbirini_gormez(tmp_path):
    (tmp_path / "kod.py").write_text("deger = 1\n", encoding="utf-8")

    with isolate(tmp_path, name="a") as birinci, isolate(tmp_path, name="b") as ikinci:
        (birinci.root / "kod.py").write_text("A\n", encoding="utf-8")

        assert (ikinci.root / "kod.py").read_text(encoding="utf-8") == "deger = 1\n"


def test_kazanan_aday_asil_projeye_uygulanir(tmp_path):
    (tmp_path / "kod.py").write_text("deger = 1\n", encoding="utf-8")

    with isolate(tmp_path, name="kazanan") as alan:
        (alan.root / "kod.py").write_text("deger = 2\n", encoding="utf-8")
        (alan.root / "yeni.py").write_text("yeni = True\n", encoding="utf-8")
        degisenler = alan.apply()

    assert (tmp_path / "kod.py").read_text(encoding="utf-8") == "deger = 2\n"
    assert (tmp_path / "yeni.py").is_file()
    assert {yol.name for yol in degisenler} == {"kod.py", "yeni.py"}


def test_alan_kapaninca_temizlenir(tmp_path):
    (tmp_path / "kod.py").write_text("deger = 1\n", encoding="utf-8")

    with isolate(tmp_path, name="gecici") as alan:
        yol = alan.root

    assert not yol.exists()

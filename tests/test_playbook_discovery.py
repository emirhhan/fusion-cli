"""Playbook'lar projeden KEŞFEDİLEN komutları kullanır.

Kütüphane `ruff` ve `pytest` sabit kodluyordu; bir Node ya da Go projesinde
"lint" yazan kullanıcıda yanlış komut çalışıyor, tur boşa gidiyordu. `/verify`
zaten projeyi tanıyor (`verify_discovery`); playbook'un kendi sabit listesini
tutması aynı bilginin iki yerde durması demekti.
"""

from __future__ import annotations

from fusion_cli.engines.playbook.library import build_playbooks


def test_python_projesinde_python_araclari_kullanilir(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[dependency-groups]\ndev=['pytest','ruff']\n", encoding="utf-8"
    )

    playbooks = build_playbooks(tmp_path)
    komutlar = [adim.command for kitap in playbooks for adim in kitap.steps]

    assert any("ruff" in k for k in komutlar)
    assert any("pytest" in k for k in komutlar)


def test_node_projesinde_node_komutlari_kullanilir(tmp_path):
    """Sabit `ruff`/`pytest` bir Node projesinde yanlış komuttur."""
    (tmp_path / "package.json").write_text(
        '{"scripts": {"lint": "eslint .", "test": "vitest run"}}', encoding="utf-8"
    )

    playbooks = build_playbooks(tmp_path)
    komutlar = [adim.command for kitap in playbooks for adim in kitap.steps]

    assert any("npm run lint" in k for k in komutlar)
    assert any("npm run test" in k for k in komutlar)
    assert not any("ruff" in k or "pytest" in k for k in komutlar)


def test_go_projesinde_go_test_kullanilir(tmp_path):
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")

    komutlar = [a.command for k in build_playbooks(tmp_path) for a in k.steps]

    assert any("go test" in k for k in komutlar)


def test_taninmayan_projede_playbook_uretilmez(tmp_path):
    """Komut uydurmaktansa playbook hiç sunmamak doğrudur.

    Yanlış komut çalıştırmak turu boşa harcar ve kullanıcı sebebini anlamaz.
    """
    assert build_playbooks(tmp_path) == ()


def test_dogrulama_komutu_adimla_tutarli(tmp_path):
    """`checks` keşfedilen komutlardan gelir; sabit `ruff check` yazılmaz."""
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")

    for kitap in build_playbooks(tmp_path):
        for kontrol in kitap.checks:
            assert "ruff" not in kontrol and "pytest" not in kontrol


def test_tetikleyiciler_korunur(tmp_path):
    """Kullanıcının yazdığı kelimeler değişmedi; yalnızca komutlar keşfediliyor."""
    (tmp_path / "pyproject.toml").write_text(
        "[dependency-groups]\ndev=['pytest']\n", encoding="utf-8"
    )

    tetikleyiciler = {t for kitap in build_playbooks(tmp_path) for t in kitap.triggers}

    assert "pytest" in tetikleyiciler or "testleri çalıştır" in tetikleyiciler

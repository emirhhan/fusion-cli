"""Proje türü, doğrulama komutları ve Git özet sözleşmeleri."""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.appserver.project_status import git_status, suggested_commands


def test_package_json_yalniz_tanimli_dogrulama_scriptlerini_onerir(tmp_path: Path):
    """Script keşfi uydurma komut eklerse kullanıcı ilk tıklamada hata alır."""
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"dev": "vite", "test": "vitest", "build": "vite build"}}),
        encoding="utf-8",
    )

    result = suggested_commands(tmp_path)

    assert result == {
        "ok": True,
        "komutlar": [
            {"tur": "test", "ad": "Testleri çalıştır", "komut": "npm test"},
            {"tur": "build", "ad": "Üretim derlemesi", "komut": "npm run build"},
            {"tur": "dev", "ad": "Önizlemeyi başlat", "komut": "npm run dev"},
        ],
    }


def test_makefile_check_hedefi_tek_kanonik_kapi_olarak_onerilir(tmp_path: Path):
    """`make check` varken alt komutlar ayrıca önerilirse kanıt parçalanır."""
    (tmp_path / "Makefile").write_text(
        "check:\n\t@echo ok\ntest:\n\t@echo test\n",
        encoding="utf-8",
    )

    result = suggested_commands(tmp_path)

    assert result["komutlar"] == [
        {"tur": "check", "ad": "Tüm kalite kapısı", "komut": "make check"},
    ]


def test_git_olmayan_klasor_hata_degil_bos_durumdur(tmp_path: Path):
    """Git zorunlu tutulursa yeni/tek dosyalı projeler uygulamada hata görünür."""
    assert git_status(tmp_path) == {
        "ok": True,
        "git": False,
        "branch": None,
        "degisen": 0,
        "ileride": 0,
        "geride": 0,
    }

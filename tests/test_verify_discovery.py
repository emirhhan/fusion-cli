"""Doğrulama komutlarının projeden keşfi.

Keşif yalnızca dosya sistemine bakar; komutları ÇALIŞTIRMAZ. Bu yüzden testler
gerçek proje iskeletleri kurar ve çıkan planı denetler.
"""

from __future__ import annotations

from fusion_cli.engines.agent.verify_discovery import discover_commands


def test_bos_dizinde_plan_uretilmez(tmp_path):
    assert discover_commands(tmp_path) == ()


def test_python_projesinde_arac_zinciri_bulunur(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='x'\n[dependency-groups]\ndev=['pytest','ruff','mypy']\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()

    plan = discover_commands(tmp_path)

    assert "ruff check ." in plan
    assert "mypy src" in plan
    assert "pytest -q" in plan


def test_ucuz_komut_once_calisir(tmp_path):
    """Sıra maliyete göredir: lint saniyeler, test dakikalar sürer.

    Kapı ilk başarısız komutta durduğu için pahalı olanı öne almak her kırık
    turda boşuna beklemek demektir.
    """
    (tmp_path / "pyproject.toml").write_text(
        "[dependency-groups]\ndev=['pytest','ruff','mypy']\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()

    plan = discover_commands(tmp_path)

    assert plan.index("ruff check .") < plan.index("pytest -q")
    assert plan.index("mypy src") < plan.index("pytest -q")


def test_src_yoksa_mypy_koke_bakar(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.mypy]\nstrict=true\n", encoding="utf-8")

    assert "mypy ." in discover_commands(tmp_path)


def test_adi_gecmeyen_arac_plana_girmez(tmp_path):
    """Kurulu olmayan aracı çalıştırmak kapıyı her turda düşürürdü."""
    (tmp_path / "pyproject.toml").write_text(
        "[dependency-groups]\ndev=['pytest']\n", encoding="utf-8"
    )

    plan = discover_commands(tmp_path)

    assert plan == ("pytest -q",)


def test_node_projesinde_script_adlari_kullanilir(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"scripts": {"lint": "eslint .", "test": "vitest run"}}', encoding="utf-8"
    )

    plan = discover_commands(tmp_path)

    assert plan == ("npm run lint", "npm run test")


def test_node_paket_yoneticisi_lock_dosyasindan_secilir(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {"test": "vitest"}}', encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")

    assert discover_commands(tmp_path) == ("pnpm run test",)


def test_tanimsiz_script_plana_girmez(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {"build": "vite build"}}', encoding="utf-8")

    assert discover_commands(tmp_path) == ()


def test_bozuk_package_json_cokmeye_neden_olmaz(tmp_path):
    """Keşif bir iyileştirmedir; okunamayan dosya turu düşürmemeli."""
    (tmp_path / "package.json").write_text("{bozuk json", encoding="utf-8")

    assert discover_commands(tmp_path) == ()


def test_go_ve_rust_projeleri_taninir(tmp_path):
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")

    assert discover_commands(tmp_path) == ("go test ./...",)

    (tmp_path / "go.mod").unlink()
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")

    assert discover_commands(tmp_path) == ("cargo test",)


def test_makefile_yalnizca_var_olan_hedefi_onerir(tmp_path):
    (tmp_path / "Makefile").write_text("build:\n\techo x\ntest:\n\techo y\n", encoding="utf-8")

    plan = discover_commands(tmp_path)

    assert plan == ("make test",)


def test_makefile_hedefsizse_bos_doner(tmp_path):
    (tmp_path / "Makefile").write_text("build:\n\techo x\n", encoding="utf-8")

    assert discover_commands(tmp_path) == ()


# --- otomatik kapı: hızlı ve yalnızca "bozdum mu" -------------------------- #
#
# Ölçüldü: kapı opt-in olduğu için pratikte hiç kurulmuyordu. Agent bir TSX
# dosyasının ortasına beş kapanış etiketi ekledi, dosya 12 sözdizimi hatasıyla
# bozuldu ve tur "tamamladım" diyerek kapandı. Bozuk kod teslim edip başarı
# iddia etmek, hiç yazmamaktan kötüdür.


def test_otomatik_kapi_test_paketini_dislar(tmp_path):
    """Önceden kırık bir test agent'ın HER turunu düşürürdü."""
    from fusion_cli.engines.agent.verify_discovery import discover_auto_commands

    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n[tool.mypy]\n[tool.pytest]\n")

    plan = discover_auto_commands(tmp_path)

    assert "ruff check ." in plan
    assert not any("pytest" in komut for komut in plan)


def test_otomatik_kapi_node_projesinde_build_onerir(tmp_path):
    """TypeScript/Next'te sözdizimini ve tipleri asıl `build` denetler."""
    import json

    from fusion_cli.engines.agent.verify_discovery import discover_auto_commands

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"dev": "next dev", "build": "next build", "lint": "next lint"}})
    )

    assert discover_auto_commands(tmp_path) == ("npm run lint", "npm run build")


def test_otomatik_kapi_kanitsiz_komut_uydurmaz(tmp_path):
    from fusion_cli.engines.agent.verify_discovery import discover_auto_commands

    assert discover_auto_commands(tmp_path) == ()


def test_kapi_yapilandirma_yoksa_kesiften_kurulur(tmp_path):
    """`verification_commands` boşken bile komut kapısı devrede olmalı."""
    import json

    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.verification import build_verifier

    from .fakes import make_config

    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"build": "next build"}}))
    config = make_config(runtime={"web_verification": False, "browser_verification": False})

    verifier = build_verifier(config, root=tmp_path, tool_context=ToolContext(root=tmp_path))

    assert verifier is not None, "keşfedilen komut kapısı kurulmadı"

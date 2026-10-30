"""Dalga 4 (plan-dogrulama): adım doğrulama, kapı ve rapor bulguları (A4-14 ...)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fusion_cli.core.evidence import EvidenceStatus
from fusion_cli.core.execution_plan import VerificationCheck, VerificationCheckKind
from fusion_cli.engines.agent import step_verification as sv

# --- A4-14: git seçenekli çağrılarda alt komut doğru çıkarılır -------------------- #


@pytest.mark.parametrize(
    "komut",
    [
        "git --git-dir=.git commit -m x",
        "git -c a=b -C repo commit -m x",
        "git -C repo commit -m x",
        "git --no-pager commit -m x",
    ],
)
def test_git_secenekli_commit_tanınır(komut):
    """Ölçüldü (29 Ekim): `--git-dir=.git` değer-içi seçenekte `commit` atlanıyordu."""
    assert sv._contains_git_action(komut, "commit")


def test_git_baska_alt_komut_commit_sayilmaz():
    assert not sv._contains_git_action("git --git-dir=.git status", "commit")


# --- A4-53: 'var' alt dizesi ------------------------------------------------------ #


def test_eski_dosya_kosulu_varsayilan_kelimesine_takilmaz():
    from fusion_cli.core.execution_plan import PlanStep, RetrySafety

    adim = PlanStep(
        step_id="a",
        goal="g",
        depends_on=(),
        expected_effects=("file:a.txt",),
        allowed_tool_families=("files",),
        success_criteria=("dosya varsayılan ayarları içerir",),
        verification_hint="",
        retry_safety=RetrySafety.SAFE,
    )

    assert sv._legacy_file_check(adim, "dosya varsayılan ayarları içerir") is None
    assert sv._legacy_file_check(adim, "a.txt dosyası var") is not None


# --- A4-18: araç takma adı, boş expected, komut boşluğu --------------------------- #


def _cikti(*kullanimlar):
    return SimpleNamespace(tool_uses=tuple(kullanimlar))


def _kullanim(name, arguments=None, output=""):
    return SimpleNamespace(name=name, ok=True, arguments=arguments or {}, output=output)


def test_arac_kontrolu_takma_adi_ve_bos_expected_kabul_eder(tmp_path):
    kontrol = VerificationCheck("k", VerificationCheckKind.TOOL, "bash", "")
    kanit = sv._evaluate_check(
        kontrol,
        root=tmp_path,
        outcome=_cikti(_kullanim("run_shell", {"command": "ls"})),
        verification=None,
    )

    assert kanit.status is EvidenceStatus.PASSED


def test_komut_kontrolu_bosluk_farkini_tolere_eder(tmp_path):
    kontrol = VerificationCheck("k", VerificationCheckKind.COMMAND, "pytest   -q")
    kanit = sv._evaluate_check(
        kontrol,
        root=tmp_path,
        outcome=_cikti(_kullanim("run_shell", {"command": "python3 -m pytest -q"})),
        verification=None,
    )

    assert kanit.status is EvidenceStatus.PASSED


# --- A4-19: içerik kontrolü ------------------------------------------------------- #


def test_dosya_icerik_kontrolu_bosluk_farkini_tolere_eder_ve_kesifte_dusurmez(tmp_path):
    (tmp_path / "a.py").write_text("def main() -> None:\n    pass\n", encoding="utf-8")
    kontrol = VerificationCheck("k", VerificationCheckKind.FILE_CONTAINS, "a.py", "def  main()")
    assert sv.evaluate_file_check(kontrol, tmp_path).status is EvidenceStatus.PASSED

    yanlis = VerificationCheck("k", VerificationCheckKind.FILE_CONTAINS, "a.py", "def run():")
    assert sv.evaluate_file_check(yanlis, tmp_path).status is EvidenceStatus.FAILED
    assert (
        sv.evaluate_file_check(yanlis, tmp_path, step_mutates=False).status
        is EvidenceStatus.UNVERIFIED
    )


# --- A4-17: değişken gürültü önceden kırık kapıyı yeni kırılma yapmaz -------------- #


def test_zaman_damgasi_ve_sure_farki_yeni_bulgu_sayilmaz():
    onceki = (
        "pytest düştü (çıkış 1)\n[2026-10-29 10:00:00] 3 failed in 1.52s pid 123 /tmp/tmpab/x",
    )
    simdi = (
        "pytest düştü (çıkış 1)\n[2026-10-29 10:07:41] 3 failed in 2.08s pid 9981 /tmp/tmpzz/x",
    )

    assert sv.new_findings(simdi, onceki) == ()
    yeni = ("pytest düştü (çıkış 1)\n[2026-10-29 10:07:41] 4 failed in 2.08s pid 9981",)
    assert sv.new_findings(yeni, onceki) == yeni


# --- A4-15: manifest taraması bağımlılık klasörlerine girmez ----------------------- #


def test_manifest_taramasi_node_modules_a_girmez(tmp_path):
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "paket.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ASSETS.json").write_text("{}", encoding="utf-8")

    adlar = [p.name for p in sv._manifests(tmp_path)]

    assert adlar == ["ASSETS.json"]


# --- A4-24 / A4-25: kapı çöküşü ve sessiz atlama -------------------------------------- #


async def test_tek_kapinin_cokusu_butun_dogrulamayi_dusurmez():
    from fusion_cli.core.verification import VerificationResult
    from fusion_cli.engines.agent.verification import CompositeVerifier

    class Cokuyor:
        async def verify(self):
            raise RuntimeError("playwright patladı")

    class Temiz:
        async def verify(self):
            return VerificationResult(ok=False, summary="lint", findings=("lint kırık",))

    sonuc = await CompositeVerifier((Cokuyor(), Temiz())).verify()

    assert sonuc.ok is False
    assert sonuc.findings == ("lint kırık",)
    assert any("Cokuyor" in uyari and "DOĞRULANAMADI" in uyari for uyari in sonuc.warnings)


async def test_tarayici_denetimi_atlanirsa_neden_uyaridadir(tmp_path, monkeypatch):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import site_verify

    class Bozuk:
        def __init__(self, context):
            pass

        async def observe_urls(self, adresler):
            raise RuntimeError("chromium yok")

    monkeypatch.setattr(site_verify, "BrowserVerifier", Bozuk)
    sonuc = SimpleNamespace(status=200, url="http://x/", links=())

    sonuc_ = await site_verify.SiteVerifier(ToolContext(root=tmp_path), None)._browser_audit(sonuc)

    assert sonuc_ is not None
    assert "atlandı" in sonuc_.warnings[0]


# --- A4-21 / A4-22 / A4-23: doğrulama komutu keşfi --------------------------------- #


def test_arac_yalniz_yorumda_ya_da_baska_paketin_adinda_geciyorsa_tanimli_sayilmaz(tmp_path):
    from fusion_cli.engines.agent.verify_discovery import discover_commands

    (tmp_path / "pyproject.toml").write_text(
        "# ruff sonra eklenecek\n[project]\nname='x'\ndependencies=['ruff-lsp']\n",
        encoding="utf-8",
    )

    assert discover_commands(tmp_path) == ()


def test_arac_yalniz_venvde_kuruluysa_venv_yolu_kullanilir(tmp_path):
    from fusion_cli.engines.agent.verify_discovery import discover_commands

    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length=100\n", encoding="utf-8")
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "ruff").write_text("", encoding="utf-8")

    assert discover_commands(tmp_path) == (".venv/bin/ruff check .",)


def test_rust_ve_go_otomatik_kapisi_bos_kalmaz(tmp_path):
    from fusion_cli.engines.agent.verify_discovery import discover_auto_commands

    (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    assert discover_auto_commands(tmp_path) == ("cargo check",)
    (tmp_path / "Cargo.toml").unlink()
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    assert discover_auto_commands(tmp_path) == ("go vet ./...",)


def test_make_test_otomatik_kapidan_dislanir(tmp_path):
    from fusion_cli.engines.agent.verify_discovery import discover_auto_commands

    (tmp_path / "Makefile").write_text("test:\n\tpytest\n", encoding="utf-8")

    assert discover_auto_commands(tmp_path) == ()


@pytest.mark.parametrize(
    "komut",
    [
        "uv run pytest -q",
        "poetry run pytest tests/",
        "python -m unittest discover",
        "tox",
        "npx playwright test",
        "deno test",
        "mvn test",
        "./gradlew test",
        "dotnet test",
        "bundle exec rspec",
        "phpunit",
        "cargo +nightly test",
        "npm run test:unit",
    ],
)
def test_yaygin_test_kosuculari_davranis_kaniti_sayilir(komut):
    from fusion_cli.engines.agent.verify_discovery import is_behavioral_command

    assert is_behavioral_command(komut)


def test_bun_metin_kilit_dosyasi_taninir(tmp_path):
    from fusion_cli.engines.agent.verify_discovery import discover_commands

    (tmp_path / "package.json").write_text('{"scripts": {"test": "x"}}', encoding="utf-8")
    (tmp_path / "bun.lock").write_text("", encoding="utf-8")

    assert discover_commands(tmp_path) == ("bun run test",)


# --- A4-26 / A4-27 / A4-65: tur raporu ----------------------------------------------- #


def _yaz(yol):
    from fusion_cli.core.evidence import ToolUse

    return ToolUse(name="write_file", arguments={"path": yol}, ok=True, output="ok", mutating=True)


def _kabuk(komut, cikti):
    from fusion_cli.core.evidence import ToolUse

    return ToolUse(
        name="run_shell", arguments={"command": komut}, ok=True, output=cikti, mutating=True
    )


def test_cikis_kodu_okunamayan_komut_raporda_none_yazmaz_ve_basari_iddiasini_engeller():
    from fusion_cli.engines.agent.turn_report import build_turn_report

    rapor = build_turn_report(
        ("a.py",), (_yaz("a.py"), _kabuk("pytest -q", "zaman aşımı, çıktı kesildi")), gate=None
    )

    metin = rapor.render()
    assert "çıkış None" not in metin
    assert "zaman aşımı" in metin
    assert rapor.blocks_success is True


def test_kapsamli_degistirmedim_cumlesi_aciklamayi_gizlemez():
    from fusion_cli.engines.agent.turn_report import build_turn_report

    rapor = build_turn_report(
        ("a.py",), (_yaz("a.py"), _kabuk("pytest -q", "(çıkış kodu 0)\nok")), gate=None
    )

    metin = rapor.render_with_model_text(
        "src/ dışındaki dosyalarda değişiklik yapmadım; yalnız a.py'yi düzenledim."
    )
    assert "yalnız a.py'yi düzenledim" in metin
    tum = rapor.render_with_model_text("Hiçbir dosya değiştirmedim.")
    assert "açıklaması gösterilmedi" in tum


def test_cikis_kodu_oneki_uretici_ve_okuyucuda_ayni_sabittir():
    from fusion_cli.core.constants import EXIT_CODE_PREFIX
    from fusion_cli.engines.agent import turn_report

    assert turn_report._EXIT_CODE_PREFIX == EXIT_CODE_PREFIX

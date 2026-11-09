"""Masaüstü sürümü Python kalite kapısı geçmeden yayımlanmaz (Q1-01, WP19).

Ölçüldü (28 Ekim): `desktop.yml` içindeki `release` işi yalnız paket işlerine
(`macos`, `windows`, `terminal`) bağlıydı; lint/tip/test kapısı ayrı `ci.yml`'de
koştuğu için testler kırmızıyken etiket atılsa da herkese açık Release oluşuyordu.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def _yukle(ad: str) -> dict:
    veri = yaml.safe_load((_WORKFLOWS / ad).read_text(encoding="utf-8"))
    # PyYAML `on:` anahtarını True olarak okur.
    if True in veri:
        veri["on"] = veri.pop(True)
    return veri


def test_ci_yeniden_kullanilabilir_kalite_kapisidir():
    ci = _yukle("ci.yml")

    assert "workflow_call" in ci["on"]
    assert any("make check" in str(step.get("run", "")) for step in ci["jobs"]["check"]["steps"])


def test_surum_isi_kalite_kapisina_baglidir():
    desktop = _yukle("desktop.yml")
    jobs = desktop["jobs"]
    kapi = next(
        name for name, job in jobs.items() if job.get("uses") == "./.github/workflows/ci.yml"
    )

    assert kapi in jobs["release"]["needs"]
    assert {"macos", "windows", "terminal"} <= set(jobs["release"]["needs"])


def _adimlar(is_adi: str, dosya: str = "desktop.yml") -> list[dict]:
    return _yukle(dosya)["jobs"][is_adi]["steps"]


def test_release_kaniti_yayinlanan_ikilileri_kapsar():
    """Q1-05: SHA256SUMS yalnız wheel/sdist içindi; DMG/EXE hiç girmiyordu.

    Ölçüldü (30 Ekim): `release-evidence.yml` yalnız `python -m build` çıktısını
    özetliyor ve artifact Release'e eklenmiyordu; SECURITY.md'nin "her etiket
    SHA256SUMS ile gelir" iddiası ikililer için yanlıştı. Kanıt artık Release
    işinde, yayınlanacak `dagitim/` klasörünün kendisi için üretilir.
    """
    adimlar = _adimlar("release")
    manifest = next(s for s in adimlar if "release_manifest.py" in str(s.get("run", "")))
    komut = str(manifest["run"])

    assert "--artifacts dagitim" in komut
    assert "sha256sum -c" in komut
    indeks = adimlar.index(manifest)
    yayin = next(s for s in adimlar if "action-gh-release" in str(s.get("uses", "")))
    assert indeks < adimlar.index(yayin)
    assert "kanit/*" in str(yayin["with"]["files"])
    # release_manifest.py ve kilit dosyaları depodan gelir.
    assert any("actions/checkout" in str(s.get("uses", "")) for s in adimlar[:indeks])


def test_ayri_kanit_is_akisi_etikette_yayin_kaniti_uretmez():
    """Tag'de yalnız wheel özetleyen ikinci iş akışı yanıltıcı kanıt bırakıyordu."""
    tetik = _yukle("release-evidence.yml")["on"]

    assert "push" not in tetik
    assert "workflow_dispatch" in tetik


def test_pty_testleri_ayri_kisa_sureli_ve_sert_basarisiz_olan_isle_kosar():
    """Q1-02: `terminal::tests::` üç platformda `--skip` ile atlanıyor, kapsama SIFIRdı.

    Ölçüldü (30 Ekim): hem `desktop.yml` hem `package.json:check:ci` 13 PTY/terminal
    testini atlıyordu. Testler artık ayrı `terminal-pty` matris işinde koşar: süre
    sınırı kısa, `continue-on-error` yok (kırmızı kırmızı görünür). İş yayın
    kapısı DEĞİLDİR (`release.needs` dışında): bilinen runner asılması sürüm
    üretimini yeniden bloklamasın; karar raporda işaretlidir.
    """
    desktop = _yukle("desktop.yml")
    is_ = desktop["jobs"]["terminal-pty"]

    assert is_["timeout-minutes"] <= 45
    assert is_["strategy"]["fail-fast"] is False
    runners = set(is_["strategy"]["matrix"]["runner"])
    assert {"macos-15", "macos-15-intel", "windows-latest"} <= runners
    kosan = [s for s in is_["steps"] if "check:pty" in str(s.get("run", ""))]
    assert kosan and all(0 < s["timeout-minutes"] <= 15 for s in kosan)
    assert all("--skip" not in str(s["run"]) for s in kosan)
    assert "continue-on-error" not in (_WORKFLOWS / "desktop.yml").read_text(encoding="utf-8")
    assert "terminal-pty" not in desktop["jobs"]["release"]["needs"]


def test_check_ci_atlamasi_pty_isiyle_tutarli():
    """Atlanan şey `check:ci`de kalır ama PTY işi aynı modülü çalıştırır."""
    import json

    paket = json.loads(
        (_WORKFLOWS.parents[1] / "app" / "package.json").read_text(encoding="utf-8")
    )["scripts"]

    assert "--skip terminal::tests::" in paket["check:ci"]
    assert paket["check:pty"].endswith("cargo test terminal::tests::")
    assert "--skip" not in paket["check:pty"]


def test_release_requires_live_acceptance_and_preserves_exact_candidate_first():
    steps = _adimlar("release")
    manifest = next(s for s in steps if "release_manifest.py" in str(s.get("run", "")))
    assert "--require-live-acceptance" in manifest["run"]
    assert "--kits-manifest kanit-girdisi/kits-manifest.json" in manifest["run"]
    stage = next(s for s in steps if s.get("with", {}).get("name") == "fusion-release-candidate")
    assert steps.index(stage) < steps.index(manifest)
    assert stage["with"]["path"] == "dagitim/*"
    assert "continue-on-error" not in manifest
    for job in ("macos", "windows"):
        assert any(
            "fusion-kits-" in str(step.get("with", {}).get("name", ""))
            and "kits-manifest.json" in str(step.get("with", {}).get("path", ""))
            for step in _adimlar(job)
        )


def test_verifier_authority_is_separate_from_actor_artifacts():
    jobs = _yukle("desktop.yml")["jobs"]
    verifier = jobs["acceptance-verifier"]
    assert "acceptance-actor" in verifier["needs"]
    assert "acceptance-candidate" in verifier["needs"]
    assert "acceptance-verifier" in jobs["release"]["needs"]
    assert "steps.verify.outputs.verifier_key_sha256" in verifier["outputs"]["verifier_key_sha256"]
    assert "NVIDIA_NIM_API_KEY" not in str(verifier)
    assert any("bubblewrap" in step.get("run", "") for step in verifier["steps"])
    gate = next(
        step for step in jobs["release"]["steps"] if "release_manifest.py" in step.get("run", "")
    )
    assert "needs.acceptance-verifier.outputs.verifier_key_sha256" in gate["run"]
    assert "--live-acceptance-signature" in gate["run"]

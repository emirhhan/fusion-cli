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

"""Sürüm kanıt paketi: özetler doğrulanabilir, SBOM üretilir, hazır iddiası yok."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "release_manifest", ROOT / "scripts/release_manifest.py"
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_manifest_ozetleri_dosyalarla_eslesir(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "a.dmg").write_bytes(b"alpha")
    (dist / "alt").mkdir()
    (dist / "alt" / "b.exe").write_bytes(b"beta")
    out = tmp_path / "out"
    code = module.main(
        ["--version", "1.2.3", "--commit", "abc", "--artifacts", str(dist), "--out", str(out)]
    )
    assert code == 0
    manifest = json.loads((out / "release-manifest.json").read_text())
    assert manifest["claimsReady"] is False and manifest["knownGaps"]
    by_name = {item["name"]: item for item in manifest["artifacts"]}
    assert by_name["a.dmg"]["sha256"] == hashlib.sha256(b"alpha").hexdigest()
    assert set(by_name) == {"a.dmg", "alt/b.exe"}
    sums = (out / "SHA256SUMS").read_text().splitlines()
    assert f"{hashlib.sha256(b'beta').hexdigest()}  alt/b.exe" in sums


def test_sbom_cyclonedx_ve_bilesenler() -> None:
    sbom = module.build_sbom("9.9.9")
    assert sbom["bomFormat"] == "CycloneDX" and sbom["components"]
    purls = {item["purl"] for item in sbom["components"]}
    assert any(purl.startswith("pkg:pypi/") for purl in purls)
    assert any(purl.startswith("pkg:cargo/") for purl in purls)
    assert any(purl.startswith("pkg:npm/") for purl in purls)


def test_bos_veya_olmayan_klasor_reddedilir(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        module.collect_artifacts(tmp_path / "yok")
    (tmp_path / "bos").mkdir()
    with pytest.raises(SystemExit):
        module.collect_artifacts(tmp_path / "bos")


def test_bilinen_eksikler_gecersizse_reddedilir(tmp_path: Path) -> None:
    bad = tmp_path / "gaps.json"
    bad.write_text('{"gaps": "metin"}')
    with pytest.raises(SystemExit):
        module.load_known_gaps(bad)

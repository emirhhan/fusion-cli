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
        [
            *("--version", "1.2.3", "--commit", "abc", "--artifacts", str(dist)),
            *("--out", str(out), "--kits-commit", "a" * 40),
        ]
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


def test_sbom_python_bilesenleri_kilit_dosyasindan_gelir(tmp_path: Path) -> None:
    """Q1-05: SBOM runner'da o an kurulu her paketi (pip, build...) listeliyordu.

    Ölçüldü (30 Ekim): `importlib.metadata.distributions()` kilit dosyasını değil
    CI ortamını yansıtır. Artık `uv.lock` okunur; projenin kendisi hariç tutulur.
    """
    (tmp_path / "uv.lock").write_text(
        "version = 1\n\n"
        '[[package]]\nname = "kilitli-paket"\nversion = "1.0.0"\n'
        'source = { registry = "https://pypi.org/simple" }\n\n'
        '[[package]]\nname = "fusion-cli"\nversion = "0.1.0"\n'
        'source = { editable = "." }\n',
        encoding="utf-8",
    )

    sbom = module.build_sbom("9.9.9", root=tmp_path)

    purls = {item["purl"] for item in sbom["components"]}
    assert purls == {"pkg:pypi/kilitli-paket@1.0.0"}


def test_required_release_rejects_missing_live_report(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="zorunlu"):
        module.live_acceptance(None, [], "a" * 40, now=1001, required=True, version="1.2.3")


@pytest.mark.parametrize("change", ["version", "source", "scorer", "model", "config", "oracle"])
def test_release_binding_and_oracle_are_fail_closed(
    tmp_path: Path, monkeypatch, change: str
) -> None:
    from copy import deepcopy

    artifacts = [{"name": "app.dmg", "sha256": "a" * 64}]
    expected = {
        "source_digest": "b" * 64,
        "scorer_digest": "c" * 64,
        "model": "approved-model",
        "effective_config_digest": "d" * 64,
    }
    monkeypatch.setattr(module, "_release_expectations", lambda: expected)
    monkeypatch.setattr(module, "_validate_live_measurement", lambda metadata, results: None)
    payload = {
        "binding": {
            "commit": "a" * 40,
            "artifacts": {"app.dmg": "a" * 64},
            "version": "1.2.3",
            "measured_at": 1000,
        },
        "metadata": deepcopy(expected),
        "results": [],
        "oracle": {"independent": True, "passed": True, "producer": "trusted"},
    }
    if change == "version":
        payload["binding"]["version"] = "old"
    elif change != "oracle":
        key = {
            "source": "source_digest",
            "scorer": "scorer_digest",
            "model": "model",
            "config": "effective_config_digest",
        }[change]
        payload["metadata"][key] = "wrong"
    path = tmp_path / "candidate-written.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(SystemExit, match=r"Sürüm|kimliği|Bağımsız"):
        module.live_acceptance(path, artifacts, "a" * 40, now=1001, required=True, version="1.2.3")


def test_diagnostic_missing_report_stays_unmeasured() -> None:
    assert module.live_acceptance(None, [], "abc", now=1001)["status"] == "not_measured"

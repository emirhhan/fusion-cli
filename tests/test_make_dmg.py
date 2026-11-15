"""DMG, Finder'a (AppleScript) bağlı olmadan üretilir.

Ölçüldü (1 Kasım 2026): Tauri'nin `bundle_dmg.sh` betiği kurulum penceresini AppleScript ile
Finder'a düzenletiyor; Finder meşgulken (-15260) paketleme düşüyor, yarım `rw.*.dmg` kalıyordu.
"""

from __future__ import annotations

import plistlib
import shutil
from pathlib import Path

import pytest
from desktop_build.macos import make_dmg


def _bundle(root: Path, version: str = "0.7.19") -> Path:
    app = root / "macos/Fusion.app/Contents"
    app.mkdir(parents=True)
    (app / "Info.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": version}))
    (app / "MacOS").mkdir()
    (app / "MacOS/fusion-desktop").write_text("ikili", encoding="utf-8")
    return root


def test_dmg_adi_tauri_ile_ayni_ve_finder_kullanilmaz(tmp_path, monkeypatch) -> None:
    root = _bundle(tmp_path / "bundle")
    calls: list[tuple[str, ...]] = []
    staged: dict[str, bool] = {}

    def fake_run(*args: str) -> None:
        calls.append(args)
        if args[0] == "ditto":
            shutil.copytree(args[1], args[2], symlinks=True)
        if args[:2] == ("hdiutil", "create"):
            source = Path(args[args.index("-srcfolder") + 1])
            staged["app"] = (source / "Fusion.app/Contents/Info.plist").is_file()
            staged["applications"] = (source / "Applications").is_symlink()
            Path(args[-1]).write_bytes(b"dmg")

    monkeypatch.setattr(make_dmg, "_run", fake_run)
    monkeypatch.setattr(make_dmg.platform, "machine", lambda: "arm64")

    dmg = make_dmg.make_dmg(root)

    assert dmg == (root / "dmg/Fusion_0.7.19_aarch64.dmg").resolve()
    assert dmg.read_bytes() == b"dmg"
    assert staged == {"app": True, "applications": True}
    assert not any("osascript" in part for call in calls for part in call)
    create = next(call for call in calls if call[:2] == ("hdiutil", "create"))
    assert create[create.index("-volname") + 1] == "Fusion"
    assert ("hdiutil", "verify", str(dmg)) in calls


def test_eski_dmg_ve_yarim_kalintilar_temizlenir(tmp_path, monkeypatch) -> None:
    root = _bundle(tmp_path / "bundle")
    (root / "dmg").mkdir()
    (root / "dmg/Fusion_0.7.18_aarch64.dmg").write_bytes(b"eski")
    (root / "macos/rw.123.Fusion_0.7.19_aarch64.dmg").write_bytes(b"yarim")

    def fake_run(*args: str) -> None:
        if args[:2] == ("hdiutil", "create"):
            Path(args[-1]).write_bytes(b"yeni")

    monkeypatch.setattr(make_dmg, "_run", fake_run)
    monkeypatch.setattr(make_dmg.platform, "machine", lambda: "arm64")

    make_dmg.make_dmg(root)

    assert sorted(p.name for p in (root / "dmg").glob("*.dmg")) == ["Fusion_0.7.19_aarch64.dmg"]
    assert not list((root / "macos").glob("rw.*.dmg"))


def test_uygulama_yoksa_acik_hata(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match=r"Fusion\.app"):
        make_dmg.make_dmg(tmp_path)


def test_paket_komutu_dmgyi_finder_disi_uretir() -> None:
    import json

    root = Path(__file__).resolve().parents[1]
    script = json.loads((root / "app/package.json").read_text(encoding="utf-8"))["scripts"][
        "bundle:mac"
    ]
    assert "--bundles app " in script and "app,dmg" not in script
    assert script.index("make_dmg.py") < script.index("stable_sign_bundle.py")

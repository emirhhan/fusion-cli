"""Apply Fusion's stable ad-hoc identity to an app and its DMG payload."""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path

IDENTIFIER = "com.fusion.desktop"
DESIGNATED_REQUIREMENT = f'designated => identifier "{IDENTIFIER}"'


COMMAND_TIMEOUT_SECONDS = 120


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )


def _verify(app: Path) -> None:
    _run("codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app))
    result = _run("codesign", "-dr", "-", str(app))
    requirement = result.stdout + result.stderr
    if DESIGNATED_REQUIREMENT not in requirement:
        raise RuntimeError(f"Kararlı designated requirement bulunamadı: {requirement.strip()}")


def _nested_executables(app: Path) -> tuple[Path, ...]:
    """`Contents/Resources` altındaki çalıştırılabilir Mach-O dosyaları."""
    resources = app / "Contents/Resources"
    if not resources.is_dir():
        return ()
    return tuple(
        sorted(
            yol
            for yol in resources.iterdir()
            if yol.is_file() and not yol.is_symlink() and os.access(yol, os.X_OK)
        )
    )


def _verify_nested(app: Path) -> None:
    """Nested yardımcılar GERÇEK imza taşımalı; `linker-signed` kabul edilmez."""
    for nested in _nested_executables(app):
        result = _run("codesign", "-dv", str(nested))
        birlesik = f"{result.stdout}{result.stderr}"
        if "linker-signed" in birlesik:
            raise ValueError(f"Nested yardımcı gerçek imza taşımıyor: {nested}")


def _sign_and_verify(app: Path) -> None:
    plist = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    if plist.get("CFBundleIdentifier") != IDENTIFIER:
        raise ValueError(f"Beklenmeyen bundle kimliği: {plist.get('CFBundleIdentifier')!r}")

    # İÇTEN DIŞA imzalama: `Contents/Resources` altındaki Mach-O yardımcılar
    # `--deep` ile güvenilir biçimde imzalanmaz (kod değil kaynak olarak
    # mühürlenirler) ve derleyicinin `linker-signed` imzası yerinde kalır. AMFI
    # bunu reddedince yardımcı mikrofondan sessizlik alır. Bu yüzden nested
    # çalıştırılabilirler dış paketten ÖNCE tek tek imzalanır.
    for nested in _nested_executables(app):
        _run("codesign", "--force", "--sign", "-", "--timestamp=none", str(nested))

    _run(
        "codesign",
        "--force",
        "--deep",
        "--sign",
        "-",
        "--requirements",
        f"={DESIGNATED_REQUIREMENT}",
        str(app),
    )
    _verify(app)
    _verify_nested(app)


def _replace_dmg_payload(app: Path, dmg: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="fusion-sign-") as raw_temp:
        temp = Path(raw_temp)
        mountpoint = temp / "mounted"
        staging = temp / "staging"
        mountpoint.mkdir()
        staging.mkdir()

        _run(
            "hdiutil",
            "attach",
            "-readonly",
            "-nobrowse",
            "-mountpoint",
            str(mountpoint),
            str(dmg),
        )
        try:
            _run("ditto", str(mountpoint), str(staging))
        finally:
            _run("hdiutil", "detach", str(mountpoint))

        old_payload = staging / app.name
        if not old_payload.is_dir():
            raise FileNotFoundError(f"DMG içinde {app.name} bulunamadı")
        shutil.rmtree(old_payload)
        shutil.copytree(app, old_payload, symlinks=True)

        replacement = temp / dmg.name
        _run(
            "hdiutil",
            "create",
            "-quiet",
            "-format",
            "UDZO",
            "-srcfolder",
            str(staging),
            "-volname",
            "Fusion",
            str(replacement),
        )
        replacement.replace(dmg)


def _verify_dmg_payload(app_name: str, dmg: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="fusion-verify-") as raw_temp:
        mountpoint = Path(raw_temp) / "mounted"
        mountpoint.mkdir()
        _run(
            "hdiutil",
            "attach",
            "-readonly",
            "-nobrowse",
            "-mountpoint",
            str(mountpoint),
            str(dmg),
        )
        try:
            _verify(mountpoint / app_name)
        finally:
            _run("hdiutil", "detach", str(mountpoint))


def stable_sign_bundle(app: Path, dmg: Path) -> None:
    app = app.resolve()
    dmg = dmg.resolve()
    if not app.is_dir() or not dmg.is_file():
        raise FileNotFoundError("Fusion.app veya DMG bulunamadı")
    _sign_and_verify(app)
    _replace_dmg_payload(app, dmg)
    _verify_dmg_payload(app.name, dmg)


def _bundle_artifacts(bundle_root: Path) -> tuple[Path, Path]:
    app = bundle_root.resolve() / "macos/Fusion.app"
    plist = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    version = plist.get("CFBundleShortVersionString")
    candidates = sorted((bundle_root.resolve() / "dmg").glob(f"Fusion_{version}_*.dmg"))
    if len(candidates) != 1:
        raise FileNotFoundError(
            f"Fusion {version} için tam bir DMG bekleniyordu, {len(candidates)} bulundu"
        )
    return app, candidates[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path)
    parser.add_argument("--dmg", type=Path)
    parser.add_argument("--bundle-root", type=Path)
    args = parser.parse_args()
    if args.bundle_root and not args.app and not args.dmg:
        app, dmg = _bundle_artifacts(args.bundle_root)
    elif args.app and args.dmg and not args.bundle_root:
        app, dmg = args.app, args.dmg
    else:
        parser.error("--bundle-root veya birlikte --app/--dmg verilmelidir")
    stable_sign_bundle(app, dmg)
    print(f"Kararlı imza doğrulandı: {DESIGNATED_REQUIREMENT}")


if __name__ == "__main__":
    main()

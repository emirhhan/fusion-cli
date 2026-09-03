from __future__ import annotations

import hashlib
import json
import os
import plistlib
import select
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from desktop_build.runtime import build_runtime as runtime_builder
from desktop_build.runtime.build_runtime import (
    build_manifest,
    build_runtime,
    macos_target,
    write_archive,
)

LISTEN_BUILD_SCRIPT = Path("desktop_build/listen/build_adapter.py")
STABLE_SIGN_SCRIPT = Path("desktop_build/macos/stable_sign_bundle.py")
WINDOWS_LISTEN_SOURCE = Path("desktop_build/listen/windows/FusionListen.cs")
CROSSOVER_ROOT = Path("/Applications/CrossOver.app/Contents/SharedSupport/CrossOver")


def _windows_listen_capability() -> tuple[bool, str]:
    """Return whether this host can execute the Windows adapter contract."""
    if os.name == "nt" and shutil.which("csc"):
        return True, ""
    # CrossOver is a useful manual verification tool, but it is not a native
    # Windows runtime contract. Require an explicit opt-in so a macOS full-suite
    # run cannot create large Wine prefixes or turn an adapter test into a
    # host-dependent timeout.
    if os.environ.get("FUSION_RUN_CROSSOVER_TESTS") != "1":
        return False, "Windows adapter requires native Windows csc; CrossOver is opt-in"
    if not CROSSOVER_ROOT.is_dir():
        return False, "CrossOver Windows adapter capability is unavailable"
    return True, ""


def run_listen_fixture(tmp_path: Path, *, fixture: str) -> subprocess.CompletedProcess[str]:
    output = tmp_path / "fusion-listen"
    build = subprocess.run(
        [
            sys.executable,
            str(LISTEN_BUILD_SCRIPT),
            "--platform",
            "macos",
            "--arch",
            "arm64",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr

    env = os.environ.copy()
    env["FUSION_LISTEN_TEST_FIXTURE"] = fixture
    return subprocess.run(
        [str(output), "tr-TR"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )


def run_windows_listen_fixture(tmp_path: Path, *, fixture: str) -> subprocess.CompletedProcess[str]:
    output = tmp_path / "FusionListen.exe"
    capable, reason = _windows_listen_capability()
    if not capable:
        pytest.skip(reason)
    if os.name == "nt" and shutil.which("csc"):
        build = subprocess.run(
            [
                "csc",
                "-nologo",
                "-target:exe",
                "-out:" + str(output),
                "-reference:System.Speech.dll",
                str(WINDOWS_LISTEN_SOURCE),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert build.returncode == 0, build.stdout + build.stderr
        return subprocess.run(
            [str(output), "tr-TR", "--fixture", fixture],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )

    wine = CROSSOVER_ROOT / "lib/wine/x86_64-unix/wine"
    csc = CROSSOVER_ROOT / "share/wine/mono/wine-mono-10.4.1/lib/mono/4.5/csc.exe"
    speech = (
        CROSSOVER_ROOT
        / "share/wine/mono/wine-mono-10.4.1/lib/mono/gac/System.Speech"
        / "4.0.0.0__31bf3856ad364e35/System.Speech.dll"
    )
    if not all(path.exists() for path in (wine, csc, speech)):
        pytest.skip("Windows helper davranış testi için C# runtime bulunamadı")

    prefix = tmp_path / "wine-prefix"
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    env["WINEDLLPATH"] = str(CROSSOVER_ROOT / "lib/wine")
    env["CX_ROOT"] = str(CROSSOVER_ROOT)

    def wine_path(path: Path) -> str:
        return "Z:" + str(path.resolve()).replace("/", "\\")

    build = subprocess.run(
        [
            str(wine),
            wine_path(csc),
            "-nologo",
            "-target:exe",
            "-out:" + wine_path(output),
            "-reference:" + wine_path(speech),
            wine_path(WINDOWS_LISTEN_SOURCE),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    return subprocess.run(
        [str(wine), wine_path(output), "tr-TR", "--fixture", fixture],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


def _fake_listen_compiler(tmp_path: Path) -> Path:
    compiler_py = tmp_path / "fake_listen_compiler.py"
    compiler_py.write_text(
        """import os
import sys
from pathlib import Path

if os.environ.get("FAKE_LISTEN_COMPILE_FAIL"):
    print("sentetik derleme hatası", file=sys.stderr)
    raise SystemExit(7)

args = sys.argv[1:]
if "-o" in args:
    output = Path(args[args.index("-o") + 1])
else:
    output_dir = Path(args[args.index("--output") + 1])
    output = output_dir / "FusionListen.exe"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_bytes(b"compiled-listen-adapter")
""",
        encoding="utf-8",
    )
    if os.name == "nt":
        wrapper = tmp_path / "fake-listen-compiler.cmd"
        wrapper.write_text(f'@"{sys.executable}" "{compiler_py}" %*\r\n', encoding="utf-8")
    else:
        wrapper = tmp_path / "fake-listen-compiler"
        source = str(compiler_py)
        wrapper.write_text(
            f"#!{sys.executable}\n"
            f"exec(compile(open({source!r}, 'rb').read(), {source!r}, 'exec'))\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
    return wrapper


def _run_listen_build(
    tmp_path: Path,
    *,
    platform_name: str,
    arch: str,
    output_name: str,
    fail: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    output = tmp_path / output_name
    env = os.environ.copy()
    if fail:
        env["FAKE_LISTEN_COMPILE_FAIL"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            str(LISTEN_BUILD_SCRIPT),
            "--platform",
            platform_name,
            "--arch",
            arch,
            "--compiler",
            str(_fake_listen_compiler(tmp_path)),
            "--output",
            str(output),
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return result, output


@pytest.mark.parametrize("arch", ["arm64", "x86_64"])
def test_macos_listen_adapter_contract_builds_fusion_listen(tmp_path: Path, arch: str):
    result, output = _run_listen_build(
        tmp_path,
        platform_name="macos",
        arch=arch,
        output_name="fusion-listen",
    )

    assert result.returncode == 0, result.stderr
    assert output.read_bytes() == b"compiled-listen-adapter"


def test_windows_listen_adapter_contract_builds_fusion_listen_exe(tmp_path: Path):
    result, output = _run_listen_build(
        tmp_path,
        platform_name="windows",
        arch="AMD64",
        output_name="fusion-listen.exe",
    )

    assert result.returncode == 0, result.stderr
    assert output.read_bytes() == b"compiled-listen-adapter"


def test_listen_adapter_compile_failure_is_not_silent(tmp_path: Path):
    result, output = _run_listen_build(
        tmp_path,
        platform_name="windows",
        arch="AMD64",
        output_name="fusion-listen.exe",
        fail=True,
    )

    assert result.returncode != 0
    assert not output.exists()
    assert "derlenemedi" in result.stderr.lower()


@pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("swiftc") is None,
    reason="macOS Swift VAD sözleşme testi",
)
def test_macos_listen_silence_never_emits_transcript(tmp_path: Path):
    result = run_listen_fixture(tmp_path, fixture="silence")
    events = [json.loads(line) for line in result.stdout.splitlines()]

    assert result.returncode == 0, result.stderr
    assert events[0]["tur"] == "hazir"
    assert not any(event["tur"] in {"kismi", "son"} for event in events)


@pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("swiftc") is None,
    reason="macOS Swift VAD sözleşme testi",
)
def test_macos_listen_voiced_wraps_numeric_transcript_metadata_with_vad_events(
    tmp_path: Path,
):
    result = run_listen_fixture(tmp_path, fixture="voiced")
    events = [json.loads(line) for line in result.stdout.splitlines()]
    kinds = [event["tur"] for event in events]
    text_events = [event for event in events if event["tur"] in {"kismi", "son"}]

    assert result.returncode == 0, result.stderr
    assert kinds[0] == "hazir"
    assert kinds.index("ses-basladi") < min(kinds.index("kismi"), kinds.index("son"))
    assert kinds.index("ses-bitti") > max(kinds.index("kismi"), kinds.index("son"))
    assert text_events
    assert all(isinstance(event["guven"], (int, float)) for event in text_events)
    assert all(isinstance(event["speech_ms"], int) for event in text_events)
    assert all(isinstance(event["segment"], int) for event in text_events)


@pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("swiftc") is None,
    reason="macOS Swift güven kapısı testi",
)
def test_macos_listen_low_confidence_never_emits_final_transcript(tmp_path: Path):
    result = run_listen_fixture(tmp_path, fixture="low-confidence-partial")
    events = [json.loads(line) for line in result.stdout.splitlines()]
    kinds = [event["tur"] for event in events]

    assert result.returncode == 0, result.stderr
    assert "ses-basladi" in kinds
    assert "kismi" not in kinds
    assert "son" not in kinds
    assert "hata" in kinds
    assert kinds[-1] == "ses-bitti"


@pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("swiftc") is None,
    reason="macOS Swift eski callback kapısı testi",
)
def test_macos_listen_drops_partial_callback_after_speech_ends(tmp_path: Path):
    result = run_listen_fixture(tmp_path, fixture="delayed-partial")
    events = [json.loads(line) for line in result.stdout.splitlines()]
    kinds = [event["tur"] for event in events]

    assert result.returncode == 0, result.stderr
    assert kinds == ["hazir", "ses-basladi", "kismi", "son", "ses-bitti"]
    assert [event["metin"] for event in events if event["tur"] == "kismi"] == ["zamaninda"]


@pytest.mark.parametrize(
    ("fixture", "expected_kinds"),
    [
        ("silence", ["hazir"]),
        (
            "voiced",
            ["hazir", "ses-basladi", "kismi", "son", "ses-bitti"],
        ),
        (
            "low-confidence",
            ["hazir", "ses-basladi", "hata", "ses-bitti"],
        ),
        ("too-short", ["hazir", "ses-basladi", "hata", "ses-bitti"]),
    ],
)
def test_windows_listen_enforces_shared_vad_and_confidence_contract(
    tmp_path: Path, fixture: str, expected_kinds: list[str]
):
    result = run_windows_listen_fixture(tmp_path, fixture=fixture)
    events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]

    assert result.returncode == 0, result.stdout + result.stderr
    assert [event["tur"] for event in events] == expected_kinds
    assert all(set(event) == {"tur", "metin", "guven", "speech_ms", "segment"} for event in events)


@pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("swiftc") is None,
    reason="macOS Swift signal cleanup testi",
)
def test_macos_listen_sigterm_runs_cleanup_and_exits_cleanly(tmp_path: Path):
    output = tmp_path / "fusion-listen"
    build = subprocess.run(
        [
            sys.executable,
            str(LISTEN_BUILD_SCRIPT),
            "--platform",
            "macos",
            "--arch",
            "arm64",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr

    env = os.environ.copy()
    env["FUSION_LISTEN_SIGNAL_SMOKE"] = "1"
    helper = subprocess.Popen(
        [str(output), "tr-TR"],
        env=env,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert helper.stdout is not None
        ready, _, _ = select.select([helper.stdout], [], [], 3)
        assert ready, "helper signal smoke için hazır olmadı"
        assert json.loads(helper.stdout.readline()) == {
            "tur": "hazir",
            "metin": "tr-TR",
            "guven": None,
            "speech_ms": 0,
            "segment": 0,
        }
        helper.terminate()
        assert helper.wait(timeout=3) == 0
    finally:
        if helper.poll() is None:
            helper.kill()


def test_macos_listen_fails_closed_without_on_device_recognition():
    source = Path("desktop_build/listen/main.swift").read_text(encoding="utf-8")

    assert "guard tanıyıcı.supportsOnDeviceRecognition else" in source
    assert "r.requiresOnDeviceRecognition = true" in source
    assert "if tanıyıcı.supportsOnDeviceRecognition" not in source


def test_desktop_bundle_scripts_build_platform_listen_adapters():
    package = json.loads(Path("app/package.json").read_text(encoding="utf-8"))
    scripts = package["scripts"]

    assert "build_adapter.py --platform macos" in scripts["listen:build:mac"]
    assert "build_adapter.py --platform windows" in scripts["listen:build:win"]
    assert scripts["bundle:mac"].startswith("npm run listen:build:mac &&")
    assert "stable_sign_bundle.py --bundle-root" in scripts["bundle:mac"]
    assert scripts["bundle:win"].startswith("npm run listen:build:win &&")


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS codesign/DMG sözleşme testi")
def test_stable_signing_preserves_designated_requirement_in_app_and_dmg(tmp_path: Path):
    bundle_root = tmp_path / "bundle"
    app = bundle_root / "macos/Fusion.app"
    executable = app / "Contents/MacOS/Fusion"
    executable.parent.mkdir(parents=True)
    shutil.copyfile("/usr/bin/true", executable)
    executable.chmod(0o755)
    (app / "Contents/Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleExecutable": "Fusion",
                "CFBundleIdentifier": "com.fusion.desktop",
                "CFBundleName": "Fusion",
                "CFBundlePackageType": "APPL",
                "CFBundleShortVersionString": "0.1.0",
            }
        )
    )

    dmg_source = tmp_path / "dmg-source"
    dmg_source.mkdir()
    shutil.copytree(app, dmg_source / app.name)
    dmg = bundle_root / "dmg/Fusion_0.1.0_aarch64.dmg"
    dmg.parent.mkdir(parents=True)
    create = subprocess.run(
        [
            "hdiutil",
            "create",
            "-quiet",
            "-format",
            "UDZO",
            "-srcfolder",
            str(dmg_source),
            "-volname",
            "Fusion Test",
            str(dmg),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert create.returncode == 0, create.stderr

    sign = subprocess.run(
        [
            sys.executable,
            str(STABLE_SIGN_SCRIPT),
            "--bundle-root",
            str(bundle_root),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert sign.returncode == 0, sign.stdout + sign.stderr

    requirement = subprocess.run(
        ["codesign", "-dr", "-", str(app)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert requirement.returncode == 0, requirement.stderr
    assert 'designated => identifier "com.fusion.desktop"' in (
        requirement.stdout + requirement.stderr
    )

    mountpoint = tmp_path / "mounted"
    mountpoint.mkdir()
    attach = subprocess.run(
        [
            "hdiutil",
            "attach",
            "-readonly",
            "-nobrowse",
            "-mountpoint",
            str(mountpoint),
            str(dmg),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert attach.returncode == 0, attach.stderr
    try:
        payload_requirement = subprocess.run(
            ["codesign", "-dr", "-", str(mountpoint / app.name)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert payload_requirement.returncode == 0, payload_requirement.stderr
        assert (
            'designated => identifier "com.fusion.desktop"'
            in payload_requirement.stdout + payload_requirement.stderr
        )
    finally:
        subprocess.run(
            ["hdiutil", "detach", str(mountpoint)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )


def test_runtime_spec_tiktoken_encoding_pluginsini_toplar():
    """LiteLLM'in cl100k_base kodlaması namespace plugin olmadan çalışmaz."""
    spec = Path("desktop_build/runtime/fusion_runtime.spec").read_text(encoding="utf-8")

    assert '"tiktoken"' in spec
    assert '"tiktoken_ext"' in spec


def test_windows_tauri_bundle_maps_listen_exe_as_resource():
    config = json.loads(
        Path("app/src-tauri/tauri.windows.bundle.conf.json").read_text(encoding="utf-8")
    )

    assert config["bundle"]["resources"]["resources/fusion-listen.exe"] == "fusion-listen.exe"


def test_macos_target_mimariyi_tauri_adina_cevirir():
    assert macos_target("arm64") == "aarch64-apple-darwin"
    assert macos_target("x86_64") == "x86_64-apple-darwin"


def test_manifest_dosyalari_sirali_ve_ozetlidir(tmp_path: Path):
    root = tmp_path / "runtime"
    root.mkdir()
    executable = root / "fusion"
    executable.write_bytes(b"runtime")
    executable.chmod(0o755)
    (root / "z.txt").write_text("z", encoding="utf-8")
    archive = tmp_path / "fusion-runtime.tar.gz"
    write_archive(root, archive)

    manifest = build_manifest(root, archive, version="0.3.0a1", target="aarch64-apple-darwin")

    assert manifest["entrypoint"] == "fusion"
    assert [item["path"] for item in manifest["files"]] == ["fusion", "z.txt"]
    assert manifest["archive_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()


def test_ayni_girdi_ayni_arsivi_uretir(tmp_path: Path):
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "fusion").write_bytes(b"same")
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"

    write_archive(root, first)
    write_archive(root, second)

    assert first.read_bytes() == second.read_bytes()


def test_manifest_symlink_girdisini_hedefiyle_isaretler(tmp_path: Path):
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "fusion").write_bytes(b"runtime")
    (root / "libfusion.dylib").write_bytes(b"lib")
    link = root / "libfusion.so"
    link.symlink_to("libfusion.dylib")
    archive = tmp_path / "fusion-runtime.tar.gz"
    write_archive(root, archive)

    manifest = build_manifest(root, archive, version="0.3.0a1", target="aarch64-apple-darwin")

    entry = next(item for item in manifest["files"] if item["path"] == "libfusion.so")
    assert entry["kind"] == "symlink"
    assert entry["target"] == "libfusion.dylib"


def test_runtime_derlemesi_izlenen_readme_dosyasini_korur(tmp_path: Path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    readme = output / "README.md"
    readme.write_text("Bu dosya depoya aittir.\n", encoding="utf-8")

    def fake_pyinstaller(dist_path: Path, _build_path: Path) -> None:
        bundle = dist_path / "fusion-runtime"
        bundle.mkdir(parents=True)
        executable = bundle / "fusion"
        executable.write_bytes(b"runtime")
        executable.chmod(0o755)

    monkeypatch.setattr(runtime_builder, "_run_pyinstaller", fake_pyinstaller)

    build_runtime(output, tmp_path / "work")

    assert readme.read_text(encoding="utf-8") == "Bu dosya depoya aittir.\n"


def test_windows_hedefi_ve_exe_giris_noktasi():
    """Windows paketi Tauri'nin MSVC üçlüsünü ve `.exe` giriş noktasını taşımalı.

    PyInstaller çapraz derleme yapmaz: Windows ikilisi Windows'ta üretilir. Ama
    hedef adı ve giriş noktası ADI platformdan türetilir; bu iki alanı yanlış
    yazmak, Rust tarafındaki `RuntimeManifest::validate` ve giriş noktası
    çözümlemesini paket açıldıktan SONRA patlatır.
    """
    from desktop_build.runtime.build_runtime import entrypoint_name, platform_target

    assert platform_target("Darwin", "arm64") == "aarch64-apple-darwin"
    assert platform_target("Darwin", "x86_64") == "x86_64-apple-darwin"
    assert platform_target("Windows", "AMD64") == "x86_64-pc-windows-msvc"
    assert platform_target("Windows", "ARM64") == "aarch64-pc-windows-msvc"

    assert entrypoint_name("Darwin") == "fusion"
    assert entrypoint_name("Windows") == "fusion.exe"


def test_desteklenmeyen_platform_sessizce_gecilmez():
    from desktop_build.runtime.build_runtime import platform_target

    with pytest.raises(ValueError):
        platform_target("Linux", "x86_64")
    with pytest.raises(ValueError):
        platform_target("Windows", "itanium")


def test_runtime_cli_basari_mesaji_windows_konsolunda_yazilabilir(
    tmp_path: Path, monkeypatch, capsys
):
    """Başarılı paketleme, Windows'un CP1252 konsolunda son satırda çökmemeli."""
    archive = tmp_path / "fusion-runtime.tar.gz"
    manifest = tmp_path / "runtime-manifest.json"
    monkeypatch.setattr(runtime_builder, "build_runtime", lambda *_args: (archive, manifest))
    monkeypatch.setattr(sys, "argv", ["build_runtime.py", "--output", str(tmp_path)])

    runtime_builder.main()

    output = capsys.readouterr().out
    assert str(archive) in output
    assert str(manifest) in output
    output.encode("cp1252")


@pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("swiftc") is None,
    reason="macOS konuşma yardımcısı yalnız swiftc bulunan macOS'ta derlenir",
)
def test_macos_listen_ilk_konusmadan_sonra_dinlemeye_devam_eder(tmp_path: Path):
    """Yardımcı TEK konuşmalık olmamalı.

    Gerçek hata: ilk sessizlikte `endAudio()` çağrılıp `isFinal` gelince süreç
    `bitir(0)` ile kapanıyordu. Ortamdan gelen sahte bir tetik tek konuşma
    hakkını harcayınca kullanıcı konuşmaya başlamadan dinleme bitiyordu.
    """
    result = run_listen_fixture(tmp_path, fixture="iki-konusma")
    events = [json.loads(line) for line in result.stdout.splitlines()]

    assert result.returncode == 0, result.stderr
    finaller = [event["metin"] for event in events if event["tur"] == "son"]
    assert finaller == ["son-1", "son-2"], events
    assert [event["tur"] for event in events].count("ses-basladi") == 2


@pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("swiftc") is None,
    reason="macOS konuşma yardımcısı yalnız swiftc bulunan macOS'ta derlenir",
)
def test_macos_listen_raporlanmayan_guven_metni_dusurmez(tmp_path: Path):
    """Bölge `tr_TR` iken confidence 0.0 dönebiliyor; bu reddetme gerekçesi değildir."""
    result = run_listen_fixture(tmp_path, fixture="iki-konusma")
    events = [json.loads(line) for line in result.stdout.splitlines()]

    metinli = [event for event in events if event["tur"] in {"kismi", "son"}]
    assert metinli, "sıfır güvenli metin sessizce düşürülmemeli"
    assert all(event["guven"] == 0 for event in metinli)


@pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("swiftc") is None,
    reason="macOS konuşma yardımcısı yalnız swiftc bulunan macOS'ta derlenir",
)
def test_macos_listen_yardimcisi_gercek_imza_tasir(tmp_path: Path):
    """Yardımcı ikili GERÇEKTEN imzalanmalı; `linker-signed` yetmez.

    Ölçülen hata: derleyicinin otomatik koyduğu ad-hoc `linker-signed` imzayı
    AMFI reddediyor ("has no CMS blob", "Unrecoverable CT signature issue").
    TCC izin kaydı imza kimliğine bağlı olduğu için imzasız sürece macOS hata
    vermez, sessizce SIFIR dolu ses verir: motor başlar, `hazir` yazılır, ama
    tek bir örnek gelmez ve kullanıcı "konuşuyorum, hiçbir şey olmuyor" görür.
    """
    output = tmp_path / "fusion-listen"
    build = subprocess.run(
        [
            sys.executable,
            str(LISTEN_BUILD_SCRIPT),
            "--platform",
            "macos",
            "--arch",
            "arm64",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr

    signature = subprocess.run(
        ["codesign", "-dv", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    birlesik = signature.stdout + signature.stderr
    assert "linker-signed" not in birlesik, birlesik
    assert "Signature=adhoc" in birlesik, birlesik


@pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("swiftc") is None,
    reason="macOS konuşma yardımcısı yalnız swiftc bulunan macOS'ta derlenir",
)
def test_macos_listen_kapi_acilmasa_da_metin_uretilir(tmp_path: Path):
    """Ses etkinlik kapısı tanıyıcıya giden sesi ENGELLEMEZ.

    Ölçülen hata: kapının sabit eşiği (0.012 RMS) bu mikrofonun konuşma
    seviyesinin (0.007–0.010) üstündeydi. Kapı hiç açılmadığı için tanıyıcıya
    tek bir örnek bile gitmiyor, kullanıcı konuşurken hiçbir şey olmuyordu.
    Apple'ın tanıyıcısı kendi bitiş tespitini zaten yapar; VAD'ın işi sesi
    engellemek değil, turun ne zaman biteceğini söylemektir.
    """
    result = run_listen_fixture(tmp_path, fixture="kapisiz")
    events = [json.loads(line) for line in result.stdout.splitlines()]
    kinds = [event["tur"] for event in events]

    assert result.returncode == 0, result.stderr
    assert "ses-basladi" not in kinds, "bu senaryoda kapı açılmamalı"
    assert "kismi" in kinds, f"kapı açılmasa da metin üretilmeli: {events}"


@pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("swiftc") is None,
    reason="macOS konuşma yardımcısı yalnız swiftc bulunan macOS'ta derlenir",
)
def test_macos_listen_cok_kanalli_giris_sessiz_mono_uretmez(tmp_path: Path):
    """Çok kanallı giriş tek kanala GERÇEKTEN indirgenmeli.

    Ölçülen hata: `AVAudioConverter` 3 kanal → 1 kanal dönüşümünde hata
    bildirmeden tamamen sessiz tampon üretiyordu (`girisRms=0.00778
    monoRms=0.00000 donusumHatasi=0`). Tanıyıcıya saf sessizlik gittiği için
    ne söylenirse söylensin aynı dört karakterlik kırıntı çıkıyordu.
    """
    result = run_listen_fixture(tmp_path, fixture="indirgeme")
    events = [json.loads(line) for line in result.stdout.splitlines()]

    assert result.returncode == 0, result.stderr
    assert events, result.stdout
    olay = events[-1]
    assert olay["speech_ms"] == 480, f"çerçeve sayısı korunmalı: {olay}"
    assert olay["guven"] > 0.1, f"indirgenmiş ses sessiz olmamalı: {olay}"

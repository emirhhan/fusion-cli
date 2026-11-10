"""Kits kaynaklarına özel ortam dosyası sızması yayın öncesinde kapanır."""

from __future__ import annotations

from pathlib import Path

import pytest

from .test_kits_bundle import (
    _POSIX_ONLY,
    _fake_app,
    _fake_kits,
    _git,
    _node24,
    _prepare,
    _system_otool,
    _write_kits,
)


@pytest.mark.parametrize(
    "relative",
    [
        ".env",
        "app/.env",
        "app/.env.local",
        "app/nested/.env.production",
        "app/.ENV",
        "app/.ENV.EXAMPLE",
    ],
)
def test_kits_denetimi_ozel_ortam_dosyasini_reddeder(tmp_path: Path, relative: str) -> None:
    from desktop_build.kits_bundle import KitsBundleError, inspect_kits

    kits = _write_kits(tmp_path / "kits")
    private = kits / relative
    private.parent.mkdir(parents=True, exist_ok=True)
    private.write_text("KITS_TEST_PRIVATE=ornektir\n", encoding="utf-8")

    with pytest.raises(KitsBundleError, match="özel yapılandırma"):
        inspect_kits(kits, node_name="node", macos=True, otool=_system_otool)
    assert private.read_text(encoding="utf-8") == "KITS_TEST_PRIVATE=ornektir\n"


def test_kits_denetimi_ortam_sablonu_ve_isci_dosyalarini_korur(tmp_path: Path) -> None:
    from desktop_build.kits_bundle import inspect_kits

    kits = _write_kits(tmp_path / "kits")
    preserved = (
        "app/.env.example",
        "app/speech/worker.py",
        "app/background/worker.js",
        "app/terminal/asset.js",
    )
    for relative in preserved:
        output = kits / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("yalniz-ornek\n", encoding="utf-8")

    inspect_kits(kits, node_name="node", macos=True, otool=_system_otool)

    assert all(
        (kits / relative).read_text(encoding="utf-8") == "yalniz-ornek\n" for relative in preserved
    )


@_POSIX_ONLY
def test_kits_denetimi_ortam_sablonunda_dis_baglantiya_guvenmez(tmp_path: Path) -> None:
    from desktop_build.kits_bundle import KitsBundleError, inspect_kits

    kits = _write_kits(tmp_path / "kits")
    outside = tmp_path / "dis-ozel"
    outside.write_text("KITS_TEST_PRIVATE=baglanti\n", encoding="utf-8")
    (kits / "app/.env.example").symlink_to(outside)

    with pytest.raises(KitsBundleError, match="özel yapılandırma"):
        inspect_kits(kits, node_name="node", macos=True, otool=_system_otool)
    assert outside.read_text(encoding="utf-8") == "KITS_TEST_PRIVATE=baglanti\n"


def test_kits_denetimi_ortam_sablonu_adli_dizini_kabul_etmez(tmp_path: Path) -> None:
    from desktop_build.kits_bundle import KitsBundleError, inspect_kits

    kits = _write_kits(tmp_path / "kits")
    (kits / "app/.env.example").mkdir()

    with pytest.raises(KitsBundleError, match="özel yapılandırma"):
        inspect_kits(kits, node_name="node", macos=True, otool=_system_otool)


def test_kits_denetimi_girdi_butcesi_dolarsa_kapanir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop_build import kits_bundle

    kits = _write_kits(tmp_path / "kits")
    monkeypatch.setattr(kits_bundle, "MAX_KITS_CONFIG_ENTRIES", 2, raising=False)

    with pytest.raises(kits_bundle.KitsBundleError, match="girdi sınırı"):
        kits_bundle.inspect_kits(kits, node_name="node", macos=True, otool=_system_otool)


def test_kits_denetimi_derinlik_butcesi_dolarsa_kapanir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop_build import kits_bundle

    kits = _write_kits(tmp_path / "kits")
    monkeypatch.setattr(kits_bundle, "MAX_KITS_CONFIG_DEPTH", 2, raising=False)

    with pytest.raises(kits_bundle.KitsBundleError, match="derinlik sınırı"):
        kits_bundle.inspect_kits(kits, node_name="node", macos=True, otool=_system_otool)


@_POSIX_ONLY
@pytest.mark.parametrize("relative", [".env", "nested/.env.local", ".ENV"])
def test_kits_hazirligi_ozel_ortamda_eski_kaynaklari_korur(tmp_path: Path, relative: str) -> None:
    kits = _fake_kits(tmp_path)
    script = kits / "scripts/kits-bundle.mjs"
    script.write_text(
        script.read_text(encoding="utf-8")
        + f"\nmkdirSync(resolve(output, '{relative}', '..'), {{ recursive: true }});\n"
        + f"writeFileSync(resolve(output, '{relative}'), 'PRIVATE-CANARY');\n",
        encoding="utf-8",
    )
    _git(kits, "add", "scripts/kits-bundle.mjs")
    _git(kits, "commit", "-q", "-m", "sahte ozel ortam")
    target = _fake_app(tmp_path)
    private = target / ".env"
    private.write_text("ESKI-KAYNAK", encoding="utf-8")

    result = _prepare(tmp_path, kits, _node24(tmp_path))

    assert result.returncode != 0
    assert "özel yapılandırma" in result.stderr
    assert "PRIVATE-CANARY" not in result.stderr + result.stdout
    assert (target / "sentinel").read_text(encoding="utf-8") == "koru"
    assert private.read_text(encoding="utf-8") == "ESKI-KAYNAK"
    assert len(_git(kits, "worktree", "list").splitlines()) == 1


@_POSIX_ONLY
def test_kits_hazirligi_ornek_ortam_ve_iscileri_yayimlar(tmp_path: Path) -> None:
    kits = _fake_kits(tmp_path)
    script = kits / "scripts/kits-bundle.mjs"
    paths = (".env.example", "speech/worker.py", "background/worker.js", "terminal/asset.js")
    additions = "\n".join(
        f"mkdirSync(resolve(output, '{relative}', '..'), {{ recursive: true }});\n"
        f"writeFileSync(resolve(output, '{relative}'), 'PORTABLE-EXAMPLE');"
        for relative in paths
    )
    script.write_text(script.read_text(encoding="utf-8") + "\n" + additions, encoding="utf-8")
    _git(kits, "add", "scripts/kits-bundle.mjs")
    _git(kits, "commit", "-q", "-m", "sahte tasinabilir kaynak")
    target = _fake_app(tmp_path)

    result = _prepare(tmp_path, kits, _node24(tmp_path))

    assert result.returncode == 0, result.stderr
    assert all(
        (target / "app" / relative).read_text(encoding="utf-8") == "PORTABLE-EXAMPLE"
        for relative in paths
    )


@_POSIX_ONLY
def test_kits_denetimi_ic_goreli_baglantiyi_korur(tmp_path: Path) -> None:
    from desktop_build.kits_bundle import inspect_kits

    kits = _write_kits(tmp_path / "kits")
    (kits / "app/worker.js").write_text("// tasinabilir", encoding="utf-8")
    link = kits / "app/worker-alias.js"
    link.symlink_to("worker.js")

    inspect_kits(kits, node_name="node", macos=True, otool=_system_otool)

    assert link.is_symlink() and link.readlink() == Path("worker.js")


@_POSIX_ONLY
@pytest.mark.parametrize("kind", ["absolute", "escape", "dangling", "resolution-loop", "ancestor"])
def test_kits_denetimi_tasinamayan_baglantiyi_reddeder(tmp_path: Path, kind: str) -> None:
    from desktop_build.kits_bundle import KitsBundleError, inspect_kits

    kits = _write_kits(tmp_path / "kits")
    outside = tmp_path / "dis"
    outside.mkdir()
    (outside / ".env").write_text("DISARIDA-KAL", encoding="utf-8")
    link = kits / "app/alias"
    if kind == "absolute":
        link.symlink_to(outside)
    elif kind == "escape":
        link.symlink_to("../../dis")
    elif kind == "dangling":
        link.symlink_to("yok")
    elif kind == "resolution-loop":
        link.symlink_to("alias2")
        (kits / "app/alias2").symlink_to("alias")
    else:
        link.symlink_to("..")

    with pytest.raises(KitsBundleError, match="bağlantı"):
        inspect_kits(kits, node_name="node", macos=True, otool=_system_otool)
    assert (outside / ".env").read_text(encoding="utf-8") == "DISARIDA-KAL"


@_POSIX_ONLY
def test_kits_denetimi_dis_dizini_taramaz(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from desktop_build import kits_bundle

    kits = _write_kits(tmp_path / "kits")
    outside = tmp_path / "dis"
    outside.mkdir()
    (kits / "app/alias").symlink_to("../../dis")
    original = kits_bundle.os.scandir

    def guarded(directory: str | Path):  # type: ignore[no-untyped-def]
        assert Path(directory).is_relative_to(kits), "Paket dışı dizin tarandı"
        return original(directory)

    monkeypatch.setattr(kits_bundle.os, "scandir", guarded)
    with pytest.raises(kits_bundle.KitsBundleError, match="bağlantı"):
        kits_bundle.inspect_kits(kits, node_name="node", macos=True, otool=_system_otool)


@_POSIX_ONLY
@pytest.mark.parametrize(
    "kind",
    ["private-link", "example-link", "example-directory", "escape", "dangling", "resolution-loop"],
)
def test_kits_hazirligi_tasinamayan_baglantida_eski_kaynagi_korur(
    tmp_path: Path, kind: str
) -> None:
    kits = _fake_kits(tmp_path)
    script = kits / "scripts/kits-bundle.mjs"
    if kind == "private-link":
        addition = "symlinkSync('dist/client/index.html', resolve(output, '.env'));"
    elif kind == "example-link":
        addition = "symlinkSync('dist/client/index.html', resolve(output, '.env.example'));"
    elif kind == "example-directory":
        addition = "mkdirSync(resolve(output, '.env.example'));"
    elif kind == "escape":
        addition = "symlinkSync('../../dis', resolve(output, 'alias'));"
    elif kind == "dangling":
        addition = "symlinkSync('yok', resolve(output, 'alias'));"
    else:
        addition = (
            "symlinkSync('alias2', resolve(output, 'alias')); "
            "symlinkSync('alias', resolve(output, 'alias2'));"
        )
    script.write_text(
        script.read_text(encoding="utf-8")
        + "\nimport { symlinkSync } from 'node:fs';\n"
        + addition,
        encoding="utf-8",
    )
    _git(kits, "add", "scripts/kits-bundle.mjs")
    _git(kits, "commit", "-q", "-m", "sahte baglanti")
    target = _fake_app(tmp_path)

    result = _prepare(tmp_path, kits, _node24(tmp_path))

    assert result.returncode != 0
    assert "özel yapılandırma" in result.stderr or "bağlantı" in result.stderr
    assert (target / "sentinel").read_text(encoding="utf-8") == "koru"


@_POSIX_ONLY
def test_kits_hazirligi_ic_goreli_baglantiyi_korur(tmp_path: Path) -> None:
    kits = _fake_kits(tmp_path)
    script = kits / "scripts/kits-bundle.mjs"
    script.write_text(
        script.read_text(encoding="utf-8")
        + "\nimport { symlinkSync } from 'node:fs';\n"
        + "symlinkSync('dist/client/index.html', resolve(output, 'client-alias.html'));",
        encoding="utf-8",
    )
    _git(kits, "add", "scripts/kits-bundle.mjs")
    _git(kits, "commit", "-q", "-m", "sahte tasinabilir baglanti")
    target = _fake_app(tmp_path)

    result = _prepare(tmp_path, kits, _node24(tmp_path))

    assert result.returncode == 0, result.stderr
    assert (target / "app/client-alias.html").is_symlink()


def test_kits_denetimi_ozel_dosyanin_icerigini_okumaz(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop_build.kits_bundle import KitsBundleError, inspect_kits

    kits = _write_kits(tmp_path / "kits")
    private = kits / "app/.env"
    private.write_text("OKUNMAMALI", encoding="utf-8")
    original = Path.open

    def guarded(path: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        assert path != private, "Özel dosya içeriği okundu"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    with pytest.raises(KitsBundleError, match="özel yapılandırma"):
        inspect_kits(kits, node_name="node", macos=True, otool=_system_otool)


@_POSIX_ONLY
@pytest.mark.parametrize("state", ["portable", "private", "escaping-chain"])
def test_kits_denetimi_kardes_dizin_grafiginde_gercek_agaci_tarar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    from desktop_build import kits_bundle

    kits = _write_kits(tmp_path / "kits")
    for name in ("a", "b"):
        (kits / "app" / name).mkdir()
    (kits / "app/a/to-b").symlink_to("../b")
    (kits / "app/b/to-a").symlink_to("../a")
    if state == "private":
        (kits / "app/b/.env").write_text("FAKE-PRIVATE", encoding="utf-8")
    elif state == "escaping-chain":
        outside = tmp_path / "outside"
        outside.mkdir()
        (kits / "app/b/escape").symlink_to("../../../outside")
        (kits / "app/a/indirect").symlink_to("to-b/escape")
    original = kits_bundle.os.scandir
    visited: set[Path] = set()

    def guarded(directory: str | Path):  # type: ignore[no-untyped-def]
        path = Path(directory)
        assert path.is_relative_to(kits) and not path.is_symlink()
        assert path not in visited, "Aynı gerçek dizin yeniden tarandı"
        visited.add(path)
        return original(directory)

    monkeypatch.setattr(kits_bundle.os, "scandir", guarded)
    if state == "portable":
        kits_bundle.inspect_kits(kits, node_name="node", macos=True, otool=_system_otool)
        assert {kits / "app/a", kits / "app/b"} <= visited
        assert len(visited) <= 10
        assert (kits / "app/a/to-b").readlink() == Path("../b")
    else:
        message = "özel yapılandırma" if state == "private" else "bağlantı"
        with pytest.raises(kits_bundle.KitsBundleError, match=message):
            kits_bundle.inspect_kits(kits, node_name="node", macos=True, otool=_system_otool)


@_POSIX_ONLY
@pytest.mark.parametrize("state", ["portable", "private", "escaping-chain"])
def test_kits_hazirligi_kardes_dizin_grafiginde_gercek_agaci_tarar(
    tmp_path: Path, state: str
) -> None:
    kits = _fake_kits(tmp_path)
    script = kits / "scripts/kits-bundle.mjs"
    addition = (
        "\nimport { symlinkSync } from 'node:fs';\n"
        "mkdirSync(resolve(output, 'a')); mkdirSync(resolve(output, 'b'));\n"
        "symlinkSync('../b', resolve(output, 'a/to-b'));\n"
        "symlinkSync('../a', resolve(output, 'b/to-a'));\n"
    )
    if state == "private":
        addition += "writeFileSync(resolve(output, 'b/.env'), 'FAKE-PRIVATE');"
    elif state == "escaping-chain":
        addition += (
            "symlinkSync('../../../', resolve(output, 'b/escape'));\n"
            "symlinkSync('to-b/escape', resolve(output, 'a/indirect'));"
        )
    script.write_text(script.read_text(encoding="utf-8") + addition, encoding="utf-8")
    _git(kits, "add", "scripts/kits-bundle.mjs")
    _git(kits, "commit", "-q", "-m", "sahte kardes dizin grafigi")
    target = _fake_app(tmp_path)

    result = _prepare(tmp_path, kits, _node24(tmp_path))

    if state == "portable":
        assert result.returncode == 0, result.stderr
        assert (target / "app/a/to-b").readlink() == Path("../b")
        assert (target / "app/b/to-a").readlink() == Path("../a")
    else:
        assert result.returncode != 0
        message = "özel yapılandırma" if state == "private" else "bağlantı"
        assert message in result.stderr
        assert (target / "sentinel").read_text(encoding="utf-8") == "koru"

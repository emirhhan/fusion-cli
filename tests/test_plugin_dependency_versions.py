"""Bağımlılık `version` aralıkları: npm semver, `<ad>--v<sürüm>` etiketi, geri alma (#389)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.plugin_commands import app
from fusion_cli.config import plugin_store
from fusion_cli.config.plugin_store import MarketplaceRecord, PluginState
from fusion_cli.core.semver_range import intersect, max_satisfying, satisfies
from fusion_cli.tools import plugin_dependency_versions as versions
from fusion_cli.tools import plugin_install
from fusion_cli.tools.plugin_install import _Resolved

from .test_plugin_dependencies import _market

runner = CliRunner()


@pytest.mark.parametrize(
    ("version", "wanted", "ok"),
    [
        ("1.2.3", "^1.2.0", True),
        ("2.0.0", "^1.2.0", False),
        ("0.2.5", "^0.2.3", True),
        ("0.3.0", "^0.2.3", False),
        ("1.2.9", "~1.2.3", True),
        ("1.3.0", "~1.2.3", False),
        ("1.4.0", "1.x", True),
        ("2.0.0", "1.x", False),
        ("1.0.0-beta", "*", False),
        ("1.0.0-beta.2", ">=1.0.0-beta.1", True),
        ("2.3.5", "1.2.3 - 2.3.4", False),
        ("2.1.0", "<1.0.0 || >=2.0.0", True),
        ("1.2.3", ">= 1.2.0", True),
    ],
)
def test_npm_semver_araliklari(version, wanted, ok):
    assert satisfies(version, wanted) is ok


def test_kesisim_ve_en_yuksek_surum():
    assert max_satisfying(["1.0.0", "1.4.2", "1.4.10", "2.0.0"], "^1.2") == "1.4.10"
    assert intersect(["^1.2", "~1.4.0"]) == "^1.2 ~1.4.0"
    assert intersect(["^1", "^2"]) is None


def test_etiketlerden_araliga_uyan_en_yuksek_soyulmus_sha():
    output = "\n".join(
        [
            "aaa\trefs/tags/yardimci--v1.9.0",
            "bbb\trefs/tags/yardimci--v2.1.0",
            "ccc\trefs/tags/yardimci--v2.1.0^{}",
            "ddd\trefs/tags/yardimci--v3.0.0",
            "eee\trefs/tags/baska--v2.5.0",
        ]
    )
    pin = versions.parse_tags(output, "yardimci", "^2.0")
    assert pin == versions.TagPin("yardimci--v2.1.0", "ccc", "2.1.0")
    assert versions.parse_tags(output, "yardimci", "^4") is None


def test_dis_kaynakta_etiket_yoksa_hata_goreli_kaynakta_guncel_kopya(monkeypatch):
    monkeypatch.setattr(versions, "list_remote_tags", lambda _url: "")
    with pytest.raises(versions.DependencyVersionError, match="has no git tag satisfying"):
        versions.resolve_pin("yardimci", "https://x/r.git", "^2", relative=False)
    assert versions.resolve_pin("yardimci", "https://x/r.git", "^2", relative=True) is None


def test_goreli_eklenti_pazar_deposunun_etiketinden_alt_klasor_olarak_kurulur(tmp_path):
    clone = tmp_path / "klon"
    record = MarketplaceRecord("ekip", "https://example.com/ekip.git", "git", str(clone))
    resolved = _Resolved(
        "yerel", str(clone / "plugins" / "yardimci"), "ekip", commit_dir=str(clone)
    )

    pinned = versions.pinned_source(
        resolved, ("yardimci--v2.1.0", "c" * 40), PluginState((), (record,))
    )

    assert (pinned.kind, pinned.location, pinned.ref, pinned.subdir) == (
        "git",
        "https://example.com/ekip.git",
        "yardimci--v2.1.0",
        "plugins/yardimci",
    )


def test_git_disi_pazarda_surum_karsilanmazsa_kurulum_geri_alinir(tmp_path):
    market = _market(
        tmp_path / "pazar",
        "ekip",
        {"rapor": [{"name": "yardimci", "version": "^2.0"}], "yardimci": []},
    )
    plugin_install.add_marketplace(str(market))

    done = runner.invoke(app, ["install", "rapor@ekip", "--json"])

    assert done.exit_code == 1
    line = json.loads(done.output.strip().splitlines()[-1])
    assert line["failureCode"] == "dependency_version_conflict"
    assert "pinned to its listed commit (version 1.0.0)" in line["message"]
    assert plugin_store.load_state().plugins == ()


def test_kurulu_bagimlilik_araligi_karsilamiyor(tmp_path):
    market = _market(
        tmp_path / "pazar",
        "ekip",
        {"rapor": [{"name": "yardimci", "version": ">=2"}], "yardimci": []},
    )
    plugin_install.add_marketplace(str(market))
    plugin_install.install_plugin("yardimci@ekip", approve=lambda _p: True)

    done = runner.invoke(app, ["install", "rapor@ekip"])

    assert done.exit_code == 1
    assert 'Dependency "yardimci@ekip" is installed at 1.0.0' in done.output
    assert plugin_store.load_state().plugin("rapor") is None


def test_baglilarin_araliklari_celisirse_hata(tmp_path):
    market = _market(
        tmp_path / "pazar",
        "ekip",
        {
            "eski": [{"name": "ortak", "version": "^1.0"}],
            "rapor": [{"name": "ortak", "version": "^2.0"}],
            "ortak": [],
        },
    )
    plugin_install.add_marketplace(str(market))
    assert runner.invoke(app, ["install", "eski@ekip"]).exit_code == 0

    done = runner.invoke(app, ["install", "rapor@ekip"])

    assert done.exit_code == 1
    text = " ".join(done.output.split())
    assert "conflicting version requirements (no version satisfies all of: ^2.0, ^1.0)" in text
    assert plugin_store.load_state().plugin("rapor") is None


def test_git_kaynakli_bagimlilik_etiketle_sabitlenir(tmp_path, monkeypatch):
    from fusion_cli.tools import plugin_dependencies

    market = _market(
        tmp_path / "pazar",
        "ekip",
        {"rapor": [{"name": "yardimci", "version": "^1.0"}], "yardimci": []},
    )
    plugin_install.add_marketplace(str(market))
    monkeypatch.setattr(
        versions, "pin_target", lambda _i, _b=None: ("yardimci", "https://x/r.git", True)
    )
    monkeypatch.setattr(versions, "list_remote_tags", lambda _u: "s1\trefs/tags/yardimci--v1.0.0\n")
    seen: list[object] = []
    original = plugin_install.install_plugin

    def capture(spec, **kwargs):
        seen.append(kwargs.pop("pin", None))
        return original(spec, **kwargs)

    monkeypatch.setattr(plugin_dependencies.plugin_install, "install_plugin", capture)

    done = runner.invoke(app, ["install", "rapor@ekip"])

    assert done.exit_code == 0, done.output
    assert ("yardimci--v1.0.0", "s1") in seen


def test_surumlu_bagimlilik_bildirimden_okunur():
    from fusion_cli.core.plugins import parse_manifest

    manifest = parse_manifest(
        {"name": "a", "dependencies": ["b", {"name": "c", "marketplace": "m", "version": "~1"}]},
    )
    assert manifest.dependencies == ("b", "c@m")
    assert manifest.dependency_versions == (("c@m", "~1"),)


def test_ayni_adli_kurulum_varken_surum_uyusmazligi_geri_alinir(tmp_path):
    """#389/#391: geri alma `ad@pazar` ile kaldırır; belirsiz ad hatası uyuşmazlığı maskelemez."""
    other = _market(tmp_path / "diger", "diger", {"yardimci": []})
    market = _market(
        tmp_path / "pazar",
        "ekip",
        {"rapor": [{"name": "yardimci", "version": "^2.0"}], "yardimci": []},
    )
    plugin_install.add_marketplace(str(other))
    plugin_install.add_marketplace(str(market))
    plugin_install.install_plugin("yardimci@diger", approve=lambda _p: True)

    done = runner.invoke(app, ["install", "rapor@ekip", "--json"])

    assert done.exit_code == 1
    line = json.loads(done.output.strip().splitlines()[-1])
    assert line["failureCode"] == "dependency_version_conflict", line
    left = [plugin_store.plugin_id(r) for r in plugin_store.load_state().plugins]
    assert left == ["yardimci@diger"]

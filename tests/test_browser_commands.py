"""`fusion browser …` komutları: içe aktarma onayı, listeleme, silme, varsayılan (P-023).

Depo `tmp_path` altında, anahtar açıkça verilir; gerçek Chrome/Keychain'e gidilmez.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from fusion_cli.cli import browser_commands
from fusion_cli.cli.app import app
from fusion_cli.config.browser_profiles import BrowserProfileStore

GIZLI = "cerez-degeri-GIZLI-55"
runner = CliRunner()


@pytest.fixture
def depo(tmp_path, monkeypatch):
    store = BrowserProfileStore(tmp_path / "bp", secret_key="anahtar", clock=lambda: 1.0)
    monkeypatch.setattr(browser_commands, "default_browser_profile_store", lambda: store)
    return store


@pytest.fixture
def cerez_dosyasi(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text(
        json.dumps(
            [
                {"name": "sid", "value": GIZLI, "domain": ".example.com"},
                {"name": "o", "value": "1", "domain": "other.net"},
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_import_cookies_yes_ile_yazar_ve_degeri_basmaz(depo, cerez_dosyasi):
    result = runner.invoke(
        app, ["browser", "import-cookies", str(cerez_dosyasi), "-p", "is", "--yes"]
    )

    assert result.exit_code == 0, result.output
    assert "example.com" in result.output and "other.net" in result.output
    assert GIZLI not in result.output
    assert depo.summary("is").cookie_count == 2


def test_import_cookies_alan_adi_suzgeci_onay_listesi_olur(depo, cerez_dosyasi):
    result = runner.invoke(
        app,
        ["browser", "import-cookies", str(cerez_dosyasi), "-p", "is", "-d", "example.com", "-y"],
    )

    assert result.exit_code == 0, result.output
    assert "other.net" not in result.output
    ozet = depo.summary("is")
    assert ozet.cookie_count == 1
    assert ozet.allowed_domains == ("example.com",)


def test_import_cookies_tty_yokken_yes_zorunlu(depo, cerez_dosyasi):
    result = runner.invoke(app, ["browser", "import-cookies", str(cerez_dosyasi), "-p", "is"])

    assert result.exit_code == 1
    assert "--yes" in result.output
    assert not depo.exists("is")


def test_import_cookies_olmayan_dosya_turkce_hata(depo, tmp_path):
    result = runner.invoke(
        app, ["browser", "import-cookies", str(tmp_path / "yok.txt"), "-p", "is", "-y"]
    )

    assert result.exit_code == 1
    assert "bulunamadı" in result.output
    assert "Traceback" not in result.output


def test_profiles_listeler_ve_bos_durumda_ornek_verir(depo, cerez_dosyasi):
    bos = runner.invoke(app, ["browser", "profiles"])
    assert bos.exit_code == 0 and "import-cookies" in bos.output

    runner.invoke(app, ["browser", "import-cookies", str(cerez_dosyasi), "-p", "is", "-y"])
    dolu = runner.invoke(app, ["browser", "profiles"])

    assert dolu.exit_code == 0
    assert "is" in dolu.output and "example.com" in dolu.output
    assert GIZLI not in dolu.output


def test_delete_yes_ile_siler_olmayan_profil_hata(depo, cerez_dosyasi):
    runner.invoke(app, ["browser", "import-cookies", str(cerez_dosyasi), "-p", "is", "-y"])

    assert runner.invoke(app, ["browser", "delete", "is", "-y"]).exit_code == 0
    assert not depo.exists("is")
    assert runner.invoke(app, ["browser", "delete", "is", "-y"]).exit_code == 1


def test_default_varolan_profili_yazar_olmayani_reddeder(
    depo, cerez_dosyasi, tmp_path, monkeypatch
):
    """`browser.default_profile` kullanıcı yapılandırmasına yazılır; `--yes` gerekmez."""
    hedef = tmp_path / "config.yaml"
    monkeypatch.setattr(
        browser_commands,
        "write_browser_setting",
        lambda config, key, value: hedef.write_text(f"{key}={value}", encoding="utf-8"),
    )
    runner.invoke(app, ["browser", "import-cookies", str(cerez_dosyasi), "-p", "is", "-y"])

    assert runner.invoke(app, ["browser", "default", "is"]).exit_code == 0
    assert hedef.read_text(encoding="utf-8") == "default_profile=is"
    assert runner.invoke(app, ["browser", "default", "yok"]).exit_code == 1
    assert runner.invoke(app, ["browser", "default"]).exit_code == 0
    assert hedef.read_text(encoding="utf-8") == "default_profile="


def test_chrome_profiles_sahte_dizinle_listeler(depo, tmp_path):
    kok = tmp_path / "Chrome"
    (kok / "Default").mkdir(parents=True)
    (kok / "Default" / "Cookies").write_bytes(b"")

    result = runner.invoke(app, ["browser", "chrome-profiles", "--chrome-dir", str(kok)])

    assert result.exit_code == 0
    assert "Default" in result.output


def test_delete_tty_yokken_yes_zorunlu(depo, cerez_dosyasi):
    """Ölçüldü (31 Ekim): koşul `isatty() and not confirm` olduğundan betikte onaysız siliyordu."""
    runner.invoke(app, ["browser", "import-cookies", str(cerez_dosyasi), "-p", "is", "-y"])

    result = runner.invoke(app, ["browser", "delete", "is"])

    assert result.exit_code == 1 and "--yes" in result.output
    assert depo.exists("is")


def test_import_chrome_alan_adi_olmadan_reddedilir(depo, monkeypatch):
    """`-d` yokken bütün Chrome kavanozu taşınıyordu; artık `--all-domains` açıkça istenir."""
    monkeypatch.setattr(
        browser_commands,
        "find_chrome_profile",
        lambda *_: pytest.fail("alan adı olmadan Chrome profiline bakılmamalı"),
    )

    result = runner.invoke(app, ["browser", "import-chrome", "-p", "is", "--yes"])

    assert result.exit_code == 1
    assert "--all-domains" in result.output and not depo.exists("is")


def test_set_headless_ve_profiles_enabled_yazar(depo, monkeypatch):
    yazilan: list[tuple[str, object]] = []
    monkeypatch.setattr(
        browser_commands, "write_browser_setting", lambda c, k, v: yazilan.append((k, v))
    )

    assert runner.invoke(app, ["browser", "set", "headless", "off"]).exit_code == 0
    assert runner.invoke(app, ["browser", "set", "profiles-enabled", "on"]).exit_code == 0
    assert runner.invoke(app, ["browser", "set", "bilinmez", "on"]).exit_code == 1
    assert runner.invoke(app, ["browser", "set", "headless", "belki"]).exit_code == 1
    assert runner.invoke(app, ["browser", "set", "panel-agent", "off"]).exit_code == 0
    assert yazilan == [("headless", False), ("profiles_enabled", True), ("panel_agent", False)]

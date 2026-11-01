"""Sandbox yüzeyleri (P-010): REPL `/sandbox`, `fusion sandbox`, doctor ve masaüstü `sandbox.*`.

Ölçüldü (31 Ekim, e30d57a0): `/sandbox` komutu, `fusion sandbox` grubu, doctor satırı ve
masaüstü sandbox kartı yoktu; kip yalnız config.yaml elle düzenlenerek açılabiliyordu.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from fusion_cli.appserver.sandbox_rpc import dispatch_sandbox
from fusion_cli.cli import doctor, sandbox_commands
from fusion_cli.cli.repl.commands import build_registry as build_commands
from fusion_cli.cli.repl.sandbox_command import sandbox_command
from fusion_cli.cli.sandbox_view import parse_action
from fusion_cli.config.sandbox_admin import apply_sandbox_action, sandbox_status
from fusion_cli.core.errors import ConfigError

from .fakes import make_config


def _state(proje: Path, config_path: Path):
    from dataclasses import replace

    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    config = replace(make_config(), source=config_path)
    return ReplState(config=config, memory=null_memory(), root=proje, home=proje / "ev")


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# --- ortak yönetim ----------------------------------------------------------- #


def test_durum_kapali_kipte_de_platformu_ve_kurallari_soyler(tmp_path):
    status = sandbox_status(make_config(), tmp_path, platform="win32")
    assert not status.enabled and not status.available
    assert "macOS ve Linux" in status.reason
    assert "~/.ssh" in status.deny_read
    assert any(item.endswith(".env") for item in status.deny_read)


def test_izin_eylemi_yasaktan_cikarir_ve_agi_allowlist_e_alir(tmp_path):
    yol = tmp_path / "config.yaml"
    from dataclasses import replace

    config = replace(make_config(), source=yol)
    config = apply_sandbox_action(config, "engelle", "GitHub.com", yol).config
    degisim = apply_sandbox_action(config, "izin", "github.com", yol)

    assert degisim.config.sandbox.allowed_domains == ("github.com",)
    assert degisim.config.sandbox.denied_domains == ()
    assert degisim.config.sandbox.network == "allowlist"
    # Dosyaya Claude adıyla yazılır (#322).
    assert _yaml(yol)["sandbox"]["network"]["allowedDomains"] == ["github.com"]


def test_gecersiz_eylem_ve_alan_adi_reddedilir(tmp_path):
    for eylem, deger in (("ucur", ""), ("izin", "a b"), ("ag", "kapali")):
        try:
            apply_sandbox_action(make_config(), eylem, deger, tmp_path / "c.yaml")
        except ConfigError:
            continue
        raise AssertionError(f"{eylem} {deger} reddedilmedi")


def test_arguman_ayristirici_turkce_ve_ingilizce_takma_adlari_tanir():
    assert parse_action("") is None
    assert parse_action("on") == ("ac", "")
    assert parse_action("allow *.npmjs.org") == ("izin", "*.npmjs.org")
    assert parse_action("oto açık") == ("oto", "açık")


# --- REPL ------------------------------------------------------------------- #


def test_repl_sandbox_kayitli_ve_durum_basar(tmp_path):
    assert build_commands().get("sandbox") is not None
    state = _state(tmp_path, tmp_path / "config.yaml")
    metin = sandbox_command(state, "")
    assert "Kabuk sandbox'ı: kapalı" in metin and "Okuma engeli" in metin


def test_repl_sandbox_on_oturuma_ve_dosyaya_yazar(tmp_path):
    yol = tmp_path / "config.yaml"
    state = _state(tmp_path, yol)

    sonuc = sandbox_command(state, "on")
    izin = sandbox_command(state, "izin pypi.org")
    hatali = sandbox_command(state, "izin")

    assert "sandbox.enabled = true" in sonuc
    assert state.config.runtime.shell_sandbox == "write_root"
    assert state.config.sandbox.allowed_domains == ("pypi.org",)
    assert "pypi.org" in izin
    assert "Kullanım: /sandbox" in hatali
    # Claude açma anahtarı (#321): dosyada sandbox.enabled, eski anahtar taşınır.
    assert _yaml(yol)["sandbox"]["enabled"] is True
    assert "shell_sandbox" not in (_yaml(yol).get("runtime") or {})


# --- CLI -------------------------------------------------------------------- #


def test_cli_durum_ve_izin(tmp_path, monkeypatch):
    yol = tmp_path / "config.yaml"
    yol.write_text("runtime:\n  shell_sandbox: write_root\n")
    monkeypatch.setenv("FUSION_CONFIG", str(yol))
    runner = CliRunner()

    durum = runner.invoke(sandbox_commands.app, ["durum"])
    izin = runner.invoke(sandbox_commands.app, ["izin", "registry.npmjs.org"])

    assert durum.exit_code == 0 and "AÇIK" in durum.output
    assert izin.exit_code == 0 and _yaml(yol)["sandbox"]["network"]["allowedDomains"] == [
        "registry.npmjs.org"
    ]
    assert runner.invoke(sandbox_commands.app, ["izin", "a b"]).exit_code == 1


def test_cli_calistir_kip_kapaliyken_de_sandbox_icinde_calisir(tmp_path, monkeypatch):
    import subprocess
    import sys

    if sys.platform != "darwin" or (
        subprocess.run(
            ["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)", "/usr/bin/true"],
            capture_output=True,
            check=False,
        ).returncode
        != 0
    ):
        return
    from fusion_cli.core import shell_sandbox

    monkeypatch.setattr(shell_sandbox, "_temporary_directories", lambda: ())
    proje = tmp_path / "proje"
    proje.mkdir()
    monkeypatch.chdir(proje)
    monkeypatch.setenv("FUSION_CONFIG", str(tmp_path / "yok.yaml"))
    (tmp_path / "yok.yaml").write_text("runtime:\n  shell_sandbox: 'off'\n")

    sonuc = CliRunner().invoke(sandbox_commands.app, ["calistir", "echo x > ../dis.txt"])

    assert sonuc.exit_code == 1 and not (tmp_path / "dis.txt").exists()
    assert "sandbox" in sonuc.output.lower()


# --- doctor ----------------------------------------------------------------- #


def test_doctor_kapali_bilgi_acik_kurulamazsa_kaldi(tmp_path, monkeypatch):
    from dataclasses import replace

    from fusion_cli.config import sandbox_admin

    kapali = doctor.sandbox_check(make_config())
    assert kapali.ok is None and "kapalı" in kapali.value

    config = make_config()
    acik = replace(config, runtime=replace(config.runtime, shell_sandbox="write_root"))
    monkeypatch.setattr(sandbox_admin.sys, "platform", "win32")
    kalan = doctor.sandbox_check(acik)
    assert kalan.ok is False and "sandbox'sız" in kalan.remedy


# --- masaüstü RPC ----------------------------------------------------------- #


def test_rpc_durum_ve_ayarla(tmp_path):
    from dataclasses import replace

    config = replace(make_config(), source=tmp_path / "config.yaml")

    yok, durum = dispatch_sandbox("sandbox.durum", {}, config, tmp_path)
    yeni, sonuc = dispatch_sandbox(
        "sandbox.ayarla", {"islem": "oto", "deger": True}, config, tmp_path
    )
    _, hata = dispatch_sandbox(
        "sandbox.ayarla", {"islem": "izin", "deger": "a b"}, config, tmp_path
    )
    _, tip = dispatch_sandbox("sandbox.ayarla", {"islem": 3}, config, tmp_path)

    assert yok is None and durum["ok"] is True and "okuma_engeli" in durum
    assert yeni is not None and yeni.sandbox.auto_allow and sonuc["oto_izin"] is True
    assert sonuc["dosya"].endswith("config.yaml")
    assert hata["ok"] is False and "alan adı" in hata["metin"]
    assert tip["ok"] is False

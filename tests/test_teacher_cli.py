"""`fusion config teacherless` / `teacher-lesson-sync` komutları (Faz 4, Görev 3)."""

from __future__ import annotations

from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.config.loader import load_config

runner = CliRunner()


def test_teacherless_acar_ve_kalicilastirir(tmp_path):
    hedef = tmp_path / "config.yaml"
    hedef.write_text("{}\n", encoding="utf-8")

    result = runner.invoke(
        app_module.app, ["config", "teacherless", "true"], env={"FUSION_CONFIG": str(hedef)}
    )

    assert result.exit_code == 0, result.output
    assert "açık" in result.output
    assert load_config(hedef).runtime.teacherless is True


def test_teacherless_kapatir(tmp_path):
    hedef = tmp_path / "config.yaml"
    hedef.write_text("runtime:\n  teacherless: true\n", encoding="utf-8")

    result = runner.invoke(
        app_module.app, ["config", "teacherless", "false"], env={"FUSION_CONFIG": str(hedef)}
    )

    assert result.exit_code == 0
    assert load_config(hedef).runtime.teacherless is False


def test_teacher_lesson_sync_kapatir_ve_kalicilastirir(tmp_path):
    hedef = tmp_path / "config.yaml"
    hedef.write_text("{}\n", encoding="utf-8")

    result = runner.invoke(
        app_module.app,
        ["config", "teacher-lesson-sync", "false"],
        env={"FUSION_CONFIG": str(hedef)},
    )

    assert result.exit_code == 0, result.output
    assert "kapalı" in result.output
    assert load_config(hedef).runtime.teacher_lesson_sync is False


def test_agent_komutu_bilinmeyen_kisilikte_acik_hata_verir(tmp_path):
    """P-053: `fusion agent --agent <yok>` sessizce varsayılana düşmez.

    Main'in headless `--agent`'ı ile birleşti (31 Ekim): hata mevcut ajanları da listeler."""
    hedef = tmp_path / "config.yaml"
    hedef.write_text("{}\n", encoding="utf-8")

    result = runner.invoke(
        app_module.app,
        ["agent", "bir şey yap", "--agent", "yok-boyle"],
        env={"FUSION_CONFIG": str(hedef), "FUSION_KEYCHAIN": "off", "HOME": str(tmp_path)},
    )

    assert result.exit_code != 0
    assert "yok-boyle" in result.output and "bulunamadı" in result.output


def test_agent_kisiligi_baslik_kesisim_ve_yasak_birlesimi_uygular(tmp_path, monkeypatch):
    """Birleştirme (31 Ekim): headless `--agent` REPL kişiliğiyle aynı etkiyi verir —
    başlıklı sistem eki, `--allowed-tools` ile `tools` kesişimi, yasakların birleşimi."""
    ev = tmp_path / "ev"
    ajanlar = ev / ".claude" / "agents"
    ajanlar.mkdir(parents=True)
    (ajanlar / "denetci.md").write_text(
        "---\nname: denetci\ndescription: d\ndisallowedTools: Bash\n---\nYalnız oku.",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(ev))
    monkeypatch.chdir(tmp_path)

    secenek = app_module._headless_options(
        "işi yap",
        mode="auto",
        as_json=False,
        output_format="text",
        json_schema=None,
        agent_name="denetci",
        permission_channel=None,
        append_system_prompt=None,
        allowed_tools=None,
        disallowed_tools=["WebFetch"],
    )

    # #1: dolu gövde Claude Code'daki gibi varsayılan sistem isteminin yerine geçer.
    assert "# Oturum kişiliği:" in secenek.extra_system
    assert secenek.system_prompt is not None and "Yalnız oku." in secenek.system_prompt
    assert secenek.allowed_tools is None
    assert "run_shell" in secenek.denied_tools and "web_fetch" in secenek.denied_tools

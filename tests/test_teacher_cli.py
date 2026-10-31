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
    """P-053: `fusion agent --agent <yok>` sessizce varsayılana düşmez."""
    hedef = tmp_path / "config.yaml"
    hedef.write_text("{}\n", encoding="utf-8")

    result = runner.invoke(
        app_module.app,
        ["agent", "bir şey yap", "--agent", "yok-boyle"],
        env={"FUSION_CONFIG": str(hedef), "FUSION_KEYCHAIN": "off", "HOME": str(tmp_path)},
    )

    assert result.exit_code != 0
    assert "yok-boyle" in result.output and "adlı ajan yok" in result.output

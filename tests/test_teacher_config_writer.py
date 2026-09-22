"""`write_runtime_flag` — öğretmen bayraklarını kalıcılaştırma (Faz 4, Görev 3)."""

from __future__ import annotations

import pytest

from fusion_cli.config.loader import load_config
from fusion_cli.config.writer import write_runtime_flag

from .fakes import make_config


def test_teacherless_yazilip_geri_okunur(tmp_path):
    hedef = tmp_path / "config.yaml"
    config = make_config(source=hedef)

    write_runtime_flag(config, "teacherless", True, hedef)

    assert load_config(hedef).runtime.teacherless is True


def test_teacher_lesson_sync_yazilip_geri_okunur(tmp_path):
    hedef = tmp_path / "config.yaml"
    config = make_config(source=hedef)

    write_runtime_flag(config, "teacher_lesson_sync", False, hedef)

    assert load_config(hedef).runtime.teacher_lesson_sync is False


def test_yazarken_diger_runtime_ayarlari_korunur(tmp_path):
    hedef = tmp_path / "config.yaml"
    hedef.write_text("runtime:\n  workflow_step_calls: 40\n", encoding="utf-8")
    config = make_config(source=hedef)

    write_runtime_flag(config, "teacherless", True, hedef)

    geri = load_config(hedef)
    assert geri.runtime.teacherless is True
    assert geri.runtime.workflow_step_calls == 40


def test_bilinmeyen_anahtar_reddedilir(tmp_path):
    with pytest.raises(ValueError, match="Bilinmeyen runtime bayrağı"):
        write_runtime_flag(
            make_config(source=tmp_path / "c.yaml"), "rastgele_anahtar", True, tmp_path / "c.yaml"
        )


def test_varsayilanlar():
    config = make_config()
    assert config.runtime.teacherless is False
    assert config.runtime.teacher_lesson_sync is True

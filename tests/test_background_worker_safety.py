"""Arka plan işçisinin güvenlik sınırları: başlatma, kısıt taşıma, onay ayrıntısı (P-048)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fusion_cli.tools import agent_tasks


def test_isci_proje_dizinindeki_golge_paketi_ice_aktarmaz(tmp_path):
    # Ölçüldü (31 Ekim): `python -m` cwd'yi sys.path[0]'a koyuyordu; güvenilmeyen depodaki
    # `yaml/__init__.py` işçi açılırken onaysız çalışıyordu.
    project = tmp_path / "depo"
    (project / "yaml").mkdir(parents=True)
    marker = tmp_path / "pwned"
    (project / "yaml" / "__init__.py").write_text(
        f"open({str(marker)!r}, 'w').write('x')\n", encoding="utf-8"
    )
    argv = [*agent_tasks.worker_argv(tmp_path / "arka-plan", "deadbeef"), "--help"]
    env = {
        **os.environ,
        "HOME": str(tmp_path / "ev"),
        "XDG_CONFIG_HOME": str(tmp_path / "ev" / ".config"),
        "FUSION_KEYCHAIN": "off",
    }

    result = subprocess.run(
        argv, cwd=project, env=env, capture_output=True, text=True, timeout=120, check=False
    )

    assert result.returncode == 0, result.stderr
    assert "arka-plan-calistir" in result.stdout
    assert not marker.exists()


def test_isci_komutu_guvenli_yol_kipini_kullanir():
    argv = agent_tasks.worker_argv(Path("/tmp/x"), "deadbeef")
    if not getattr(sys, "frozen", False):
        assert argv[1] == "-P"

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def test_dev_setup_installs_runtime_extras_and_chromium(tmp_path: Path):
    shutil.copy("setup.sh", tmp_path / "setup.sh")
    (tmp_path / ".env.example").write_text("", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "commands.log"
    fake_python = fake_bin / "python3.13"
    fake_python.write_text(
        """#!/bin/sh
printf '%s\\n' "$*" >> "$SETUP_TEST_LOG"
if [ "$1" = "-V" ]; then echo 'Python 3.13.0'; exit 0; fi
if [ "$1" = "-c" ]; then exit 0; fi
if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then
  mkdir -p "$3/bin"
  cp "$0" "$3/bin/python"
  printf '#!/bin/sh\\nprintf "%%s\\n" "$*" >> "$SETUP_TEST_LOG"\\nexit 0\\n' > "$3/bin/fusion"
  chmod +x "$3/bin/python" "$3/bin/fusion"
  exit 0
fi
exit 0
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
    env["SETUP_TEST_LOG"] = str(log)

    result = subprocess.run(
        ["/bin/sh", "setup.sh", "--dev"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    commands = log.read_text(encoding="utf-8")
    assert "-m pip install --quiet -e .[dev,desktop,mcp,gateway,voice,web]" in commands
    assert "-m playwright install chromium" in commands


def test_setup_sh_ekstralari_makefile_ile_ayni() -> None:
    """Q1-21. Ölçüldü (30 Ekim): setup.sh `dev,mcp,web`, Makefile altı ekstra kuruyordu."""
    import re

    makefile = Path("Makefile").read_text(encoding="utf-8")
    setup = Path("setup.sh").read_text(encoding="utf-8")
    make_extras = re.search(r"^EXTRAS\s*:=\s*(\S+)", makefile, re.M)
    sh_extras = re.search(r"FUSION_DEV_EXTRAS:-([^}]+)\}", setup)
    assert make_extras and sh_extras
    assert make_extras.group(1) == sh_extras.group(1)


def test_app_package_adaptor_hatasini_sessizce_yutmaz() -> None:
    """Q1-20: `|| true` yerel paketi adaptörsüz üretiyordu; CI zaten zorunlu."""
    makefile = Path("Makefile").read_text(encoding="utf-8")
    hedef = makefile[makefile.index("app-package: install") :]
    hedef = hedef[: hedef.index("\n\n")]
    assert "|| true" not in hedef

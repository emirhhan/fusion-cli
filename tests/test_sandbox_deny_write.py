"""Claude `sandbox.filesystem.denyWrite` (#350).

Claude Code (settings-reference › sandbox.filesystem.denyWrite): yazılabilir bölgelerin içinde
de sandbox'taki komutun yazamadığı yollar. Fusion bu anahtarı yok sayıp uyarıyordu.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.config.loader import load_config
from fusion_cli.config.sandbox_config import sandbox_policy
from fusion_cli.core import shell_sandbox
from fusion_cli.core.sandbox_policy import SandboxPolicy
from fusion_cli.core.shell_sandbox_linux import LinuxTools


def test_denywrite_claude_adi_okunur_ve_yollar_cozulur(tmp_path):
    yol = tmp_path / "config.yaml"
    yol.write_text("sandbox:\n  filesystem:\n    denyWrite: ['dist/imzali', '~/.npmrc']\n")
    config = load_config(yol)
    assert config.sandbox.deny_write == ("dist/imzali", "~/.npmrc")
    politika = sandbox_policy(config.sandbox, home=tmp_path / "ev", root=tmp_path / "proje")
    assert politika.deny_write == (tmp_path / "proje" / "dist/imzali", tmp_path / "ev" / ".npmrc")


def test_seatbelt_denywrite_yazma_engeline_girer(tmp_path: Path):
    hedef = tmp_path / "imzali"
    policy = SandboxPolicy(deny_write=(hedef,))
    prefix = shell_sandbox._darwin_prefix((tmp_path,), policy, "/usr/bin/sandbox-exec", None)
    assert f"P0={hedef}" in prefix
    assert '(deny file-write* (subpath (param "P0"))' in prefix[-1]


def test_bwrap_denywrite_salt_okunur_baglanir(tmp_path: Path):
    hedef = tmp_path / "imzali"
    hedef.mkdir()
    plan = shell_sandbox.plan_shell_sandbox(
        "write_root",
        (tmp_path,),
        policy=SandboxPolicy(deny_write=(hedef,)),
        platform="linux",
        linux_tools=LinuxTools("/usr/bin/bwrap"),
    )
    argv = list(plan.prefix)
    konum = len(argv) - 1 - argv[::-1].index(str(hedef))
    assert argv[konum - 2 : konum + 1] == ["--ro-bind", str(hedef), str(hedef)]
    # Kök bağlamasından SONRA gelir: engel kazanır.
    assert konum > argv.index(str(tmp_path))

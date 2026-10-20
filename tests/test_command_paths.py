"""Kabuk argümanlarında proje kökünden kaçan yol tespiti (`command_paths`)."""

from __future__ import annotations

import pytest

from fusion_cli.tools.command_paths import escapes_project


@pytest.mark.parametrize(
    ("ad", "argumanlar"),
    [
        ("cat", ["~/.ssh/id_rsa"]),
        ("cat", ["/etc/hosts"]),
        ("cat", ["$HOME/x"]),
        ("cat", ["../x"]),
        ("cat", ["a/../../x"]),
        ("ls", [".."]),
        ("tool", ["--config=/etc/x"]),
        ("tool", ["PREFIX=~/x"]),
        ("cc", ["-I/usr/include"]),
        ("cc", ["-o../disari"]),
        ("grep", ["-f", "/tmp/desenler", "a.txt"]),
    ],
)
def test_proje_disini_gosteren_argumanlar_yakalanir(ad, argumanlar):
    assert escapes_project(ad, argumanlar) is True


@pytest.mark.parametrize(
    ("ad", "argumanlar"),
    [
        ("cat", ["src/a.py"]),
        ("cat", ["a/../b.txt"]),
        ("ls", ["-la"]),
        ("git", ["show", "HEAD~2"]),
        ("grep", ["^/api", "src"]),
        ("awk", ["/x/ {print $1}", "a.txt"]),
        ("cat", ["/dev/null"]),
    ],
)
def test_proje_ici_argumanlar_gecer(ad, argumanlar):
    assert escapes_project(ad, argumanlar) is False

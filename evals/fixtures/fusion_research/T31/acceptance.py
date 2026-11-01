"""İnsan sözleşmesinin ajan alanı dışındaki davranış kabulü."""

from __future__ import annotations

from pathlib import Path


def check(workspace: Path, fixture: Path) -> None:
    import json
    import subprocess

    source = (
        'mod komut; fn main() { println!("{}", komut::komut(&std::env::args().nth(1).unwrap())); }'
    )
    (workspace / "main.rs").write_text(source)
    build = subprocess.run(
        ["rustc", "--edition=2021", "main.rs", "-o", "command"],
        cwd=workspace,
        capture_output=True,
        timeout=40,
        check=False,
    )
    assert build.returncode == 0, build.stderr.decode()
    for argument, expected in [
        ("7", {"ok": True, "value": 7}),
        ("bozuk", {"ok": False, "error": "Geçersiz sayı"}),
    ]:
        result = subprocess.run(
            [str(workspace / "command"), argument], capture_output=True, timeout=10, check=False
        )
        assert result.returncode == 0
        assert json.loads(result.stdout) == expected

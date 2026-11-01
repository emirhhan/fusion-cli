"""İnsan sözleşmesinin ajan alanı dışındaki davranış kabulü."""

from __future__ import annotations

from pathlib import Path


def check(workspace: Path, fixture: Path) -> None:
    import subprocess

    script = (
        "const assert=require('node:assert/strict'); "
        "const {adetGuncelle}=require('./sepet.cjs'); "
        "const input=[{id:1,adet:1},{id:2,adet:3}]; "
        "const result=adetGuncelle(input,1,4); "
        "assert.deepEqual(result,[{id:1,adet:4},{id:2,adet:3}]); "
        "assert.deepEqual(input,[{id:1,adet:1},{id:2,adet:3}]); "
        "assert.deepEqual(adetGuncelle(input,9,7),input);; "
    )
    result = subprocess.run(
        ["node", "-e", script], cwd=workspace, capture_output=True, timeout=20, check=False
    )
    assert result.returncode == 0, result.stderr.decode()
    assert (workspace / "test.cjs").read_bytes() == (
        fixture / "seed" / "test.cjs.asset"
    ).read_bytes()

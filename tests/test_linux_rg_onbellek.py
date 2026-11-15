"""Linux iç içe korumalı yol taraması (rg) kısa süre önbelleklenir (inceleme bulgusu 5, #350).

Aynı komut için plan hem onayda (`probe_plan`) hem çalıştırmada (`prepare_sandbox`) kurulur;
büyük depoda her kabuk komutu iki rg taramasına yol açmasın. Süre kısa tutulur ki sandbox içinde
yeni oluşturulan iç içe depo bir sonraki komutlarda korunsun.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core import linux_sandbox_tools
from fusion_cli.core.linux_sandbox_tools import nested_protected


def _sayan_rg(tmp_path: Path) -> tuple[Path, Path]:
    counter = tmp_path / "sayac"
    fake = tmp_path / "rg"
    fake.write_text(
        f"#!/bin/sh\necho x >> {counter}\nprintf '%s\\n' alt/.git/config\n", encoding="utf-8"
    )
    fake.chmod(0o755)
    return fake, counter


def _runs(counter: Path) -> int:
    return len(counter.read_text(encoding="utf-8").splitlines()) if counter.exists() else 0


def test_ayni_kok_icin_tarama_kisa_sure_yeniden_kosmaz(tmp_path, monkeypatch):
    fake, counter = _sayan_rg(tmp_path)
    root = tmp_path / "kok"
    root.mkdir()
    now = {"t": 100.0}
    monkeypatch.setattr(linux_sandbox_tools, "_clock", lambda: now["t"])

    first = nested_protected((str(fake),), (root,))
    second = nested_protected((str(fake),), (root,))

    assert first == second == (root / "alt/.git/config",)
    assert _runs(counter) == 1

    other = tmp_path / "baska"
    other.mkdir()
    nested_protected((str(fake),), (other,))
    assert _runs(counter) == 2

    now["t"] += linux_sandbox_tools.SCAN_CACHE_S + 0.1
    nested_protected((str(fake),), (root,))
    assert _runs(counter) == 3

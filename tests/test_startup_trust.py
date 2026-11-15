"""Açılışta klasör güveni sorusu (#71)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.cli.startup_trust import offer_startup_trust, untrusted_allow_rules
from fusion_cli.config import trust
from fusion_cli.config.permission_rules import PermissionDecision, load_permission_rules


@pytest.fixture
def proje(tmp_path, monkeypatch):
    monkeypatch.setattr(trust, "trust_store_file", lambda: tmp_path / "guven.json")
    kok = tmp_path / "proje"
    (kok / ".claude").mkdir(parents=True)
    (kok / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Bash(npm test *)"], "deny": ["WebFetch"]}}),
        encoding="utf-8",
    )
    return kok


def _allow(kok: Path) -> set[str]:
    return {
        r.tool + (f"({r.specifier})" if r.specifier else "")
        for r in load_permission_rules(kok).rules
        if r.decision is PermissionDecision.ALLOW
    }


def test_guvenilmeyen_ayar_kurallari_listeler_ve_evet_guvenir(proje):
    yazilan: list[str] = []
    assert untrusted_allow_rules(proje) == ("Bash(npm test *)",)
    assert _allow(proje) == set()

    sonuc = offer_startup_trust(proje, yazilan.append, lambda _: "e", interactive=True)

    assert sonuc is True
    assert "  Bash(npm test *)" in yazilan
    assert _allow(proje) == {"Bash(npm test *)"}
    # Güvenildikten sonra bir daha sorulmaz.
    assert offer_startup_trust(proje, yazilan.append, lambda _: "e", interactive=True) is None


def test_hayir_guvensiz_birakir(proje):
    assert offer_startup_trust(proje, lambda _: None, lambda _: "", interactive=True) is False
    assert _allow(proje) == set()


def test_etkilesimsiz_ve_ayarsiz_klasorde_sorulmaz(proje, tmp_path):
    def sorma(_: str) -> str:
        raise AssertionError("sorulmamalı")

    assert offer_startup_trust(proje, lambda _: None, sorma, interactive=False) is None
    bos = tmp_path / "bos"
    bos.mkdir()
    assert offer_startup_trust(bos, lambda _: None, sorma, interactive=True) is None

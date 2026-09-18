"""Keşif ve komut kapısı alan bilgisini motordan değil kayıt defterinden alır.

Kanıt iki yönlüdür: sahte bir alan motora dokunmadan kapısını getirir; boş kayıt
defteriyle Godot projesinde hiçbir Godot komutu üretilmez (bilgi gömülü değildir).
"""

from __future__ import annotations

import json

from fusion_cli.engines.agent.domain_adapters.contract import DomainAdapter, ToolFailureMarkers
from fusion_cli.engines.agent.domain_adapters.registry import DomainRegistry
from fusion_cli.engines.agent.verification import CommandVerifier, build_verifier
from fusion_cli.engines.agent.verify_discovery import discover_auto_commands, discover_commands

from .fakes import make_config

_SAHTE = DomainAdapter(name="sahte", marker="sahte.proj", gates=("sahte-kapi --kontrol",))


def _kayit(*adaptorler: DomainAdapter) -> DomainRegistry:
    return DomainRegistry(adaptorler)


def test_alan_kapisi_kayit_defterinden_gelir(tmp_path):
    (tmp_path / "sahte.proj").write_text("", encoding="utf-8")

    assert discover_commands(tmp_path, domains=_kayit(_SAHTE)) == ("sahte-kapi --kontrol",)


def test_python_kesfi_alan_kapisindan_once_gelir(tmp_path):
    (tmp_path / "sahte.proj").write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")

    assert discover_commands(tmp_path, domains=_kayit(_SAHTE)) == ("ruff check .",)


def test_node_kesfi_alan_kapisindan_once_gelir(tmp_path):
    (tmp_path / "sahte.proj").write_text("", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"typecheck": "tsc --noEmit"}}), encoding="utf-8"
    )

    assert discover_auto_commands(tmp_path, domains=_kayit(_SAHTE)) == ("npm run typecheck",)


def test_alan_kapisi_rust_kesfinden_once_gelir(tmp_path):
    (tmp_path / "sahte.proj").write_text("", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")

    assert discover_commands(tmp_path, domains=_kayit(_SAHTE)) == ("sahte-kapi --kontrol",)


def test_bos_kayit_defteriyle_godot_projesinde_godot_komutu_uretilmez(tmp_path):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")

    assert discover_commands(tmp_path, domains=_kayit()) == ()


async def test_komut_kapisi_enjekte_edilen_isaretleri_kullanir(tmp_path):
    komut = "sahte() { echo 'KRITIK HATA: sahne bozuk'; }; sahte --kontrol"

    isaretli = CommandVerifier(
        (komut,),
        cwd=str(tmp_path),
        timeout_s=5,
        failure_markers=(ToolFailureMarkers("sahte", ("kritik hata",)),),
    )
    isaretsiz = CommandVerifier((komut,), cwd=str(tmp_path), timeout_s=5, failure_markers=())

    assert (await isaretli.verify()).ok is False
    assert (await isaretsiz.verify()).ok is True


async def test_dogrulayici_kurucusu_kayit_defterinin_kapi_ve_isaretlerini_kullanir(tmp_path):
    (tmp_path / "sahte.proj").write_text("", encoding="utf-8")
    adaptor = DomainAdapter(
        name="sahte",
        marker="sahte.proj",
        gates=("sahte() { echo 'KRITIK HATA'; }; sahte --kontrol",),
        executable="sahte",
        output_failure_markers=("kritik hata",),
    )
    config = make_config(runtime={"web_verification": False, "browser_verification": False})

    verifier = build_verifier(config, root=tmp_path, tool_context=None, domains=_kayit(adaptor))

    assert verifier is not None
    sonuc = await verifier.verify()
    assert sonuc.ok is False
    assert "kritik hata" in sonuc.summary

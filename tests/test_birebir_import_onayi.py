"""Dış `@import` ilk görüldüğünde onay sorusu (Claude Code #145, #166).

Belge (memory, "Import additional files"): ilk kez görülen dış import için dosyaları listeleyen
onay penceresi açılır; reddedilirse importlar kapalı kalır ve pencere bir daha görünmez.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fusion_cli.engines.agent import claude_md_imports, import_approval
from fusion_cli.engines.agent.instruction_layers import load_instruction_layers


def _proje(tmp_path: Path) -> tuple[Path, Path, Path]:
    home, root = tmp_path / "ev", tmp_path / "proje"
    home.mkdir()
    root.mkdir()
    ortak = tmp_path / "ortak.md"
    ortak.write_text("ORTAK", encoding="utf-8")
    (root / "CLAUDE.md").write_text(f"@{ortak}", encoding="utf-8")
    return home, root, ortak


def _sor(root: Path, home: Path, cevap: str) -> tuple[bool, list[str]]:
    shown: list[str] = []

    async def read() -> str:
        return cevap

    asked = asyncio.run(import_approval.offer(root, home, show=shown.append, read_answer=read))
    return asked, shown


def test_ilk_gorulen_dis_import_sorulur_onaylaninca_yuklenir(tmp_path: Path) -> None:
    home, root, ortak = _proje(tmp_path)

    asked, shown = _sor(root, home, "e")

    assert asked and str(ortak.resolve()) in shown[0]
    assert claude_md_imports.external_import_decision(root) is True
    assert "ORTAK" in load_instruction_layers(root, home).text
    assert _sor(root, home, "e")[0] is False  # karar verildi, bir daha sorulmaz


def test_reddedilen_dis_import_kapali_kalir_ve_bir_daha_sorulmaz(tmp_path: Path) -> None:
    home, root, _ = _proje(tmp_path)

    asked, shown = _sor(root, home, "")

    assert asked and "kapalı" in shown[-1]
    assert claude_md_imports.external_import_decision(root) is False
    assert "ORTAK" not in load_instruction_layers(root, home).text
    assert _sor(root, home, "e")[0] is False


def test_dis_import_yoksa_soru_yok(tmp_path: Path) -> None:
    home, root = tmp_path / "ev", tmp_path / "proje"
    root.mkdir()
    (root / "CLAUDE.md").write_text("yalnız iç", encoding="utf-8")

    assert _sor(root, home, "e")[0] is False


def test_kok_disi_kural_bagi_ayni_onayla_sorulur(tmp_path: Path) -> None:
    home, root = tmp_path / "ev", tmp_path / "proje"
    (root / ".claude" / "rules").mkdir(parents=True)
    dis = tmp_path / "paylasilan.md"
    dis.write_text("KURAL", encoding="utf-8")
    (root / ".claude" / "rules" / "ortak.md").symlink_to(dis)

    asked, shown = _sor(root, home, "evet")

    assert asked and str(dis.resolve()) in shown[0]
    assert claude_md_imports.external_import_decision(root) is True


def test_masaustu_rpc_bekleyen_dis_importu_listeler_ve_karari_yazar(
    tmp_path: Path, monkeypatch
) -> None:
    from fusion_cli.appserver import instructions, voice

    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path / "veri")
    home, root, ortak = _proje(tmp_path)

    assert instructions.get_instructions(root, home)["dis_importlar"] == [str(ortak.resolve())]
    assert instructions.set_external_imports(root, {"onay": "evet"})["ok"] is False
    assert instructions.set_external_imports(root, {"onay": False})["ok"] is True
    assert instructions.get_instructions(root, home)["dis_importlar"] == []
    assert claude_md_imports.external_import_decision(root) is False

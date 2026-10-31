"""Native beceri/ajan/MCP kataloğu protokolü."""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession


async def _request(session: AppSession, lines: list[str], name: str, data: dict[str, object]):
    await session.handle(Request(id=name, name=name, data=data))
    return json.loads(lines[-1])["veri"]


async def test_katalog_dis_kaynaklari_proje_talimatini_ve_birlesik_etiketi_gosterir(tmp_path: Path):
    home = tmp_path / "home"
    root = tmp_path / "project"
    root.mkdir()
    for base in (home / ".claude/skills/review", home / ".codex/skills/review"):
        base.mkdir(parents=True)
        (base / "SKILL.md").write_text(
            "---\nname: review\ndescription: Kodu inceler\n---\nTalimat", encoding="utf-8"
        )
    agent_dir = home / ".claude/agents"
    agent_dir.mkdir(parents=True)
    (agent_dir / "architect.md").write_text(
        "---\nname: architect\ndescription: Mimari uzmanı\ntools: Read, Bash\n---\nAjan",
        encoding="utf-8",
    )
    (root / "CLAUDE.md").write_text("Proje kuralı", encoding="utf-8")
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=home)

    result = await _request(session, lines, "yetenek.katalog", {})
    await session.close()

    assert result["ok"] is True
    assert result["beceriler"][0]["ad"] == "review"
    assert result["beceriler"][0]["kaynak"] == "claude+codex"
    assert result["ajanlar"][0]["ad"] == "architect"
    assert result["ajanlar"][0]["izinler"] == ["dosya okuma", "komut çalıştırma"]
    assert [(t["ad"], t["kaynak"], t["etkin"]) for t in result["talimatlar"]] == [
        ("CLAUDE.md", "proje", True)
    ]


async def test_detay_yalniz_katalogdaki_ogeyi_okur_ve_oturumluk_kapatma_filtreler(tmp_path: Path):
    home = tmp_path / "home"
    root = tmp_path / "project"
    skill = home / ".claude/skills/review/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: review\ndescription: Kodu inceler\n---\nGüvenli talimat", encoding="utf-8"
    )
    root.mkdir()
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=home)

    detail = await _request(session, lines, "yetenek.detay", {"tur": "beceri", "ad": "review"})
    disabled = await _request(
        session, lines, "yetenek.etkinlik", {"tur": "beceri", "ad": "review", "etkin": False}
    )
    catalog = await _request(session, lines, "yetenek.katalog", {})
    traversal = await _request(
        session, lines, "yetenek.detay", {"tur": "beceri", "ad": "../../secret"}
    )
    await session.close()

    assert "Güvenli talimat" in detail["icerik"]
    assert disabled == {"ok": True, "tur": "beceri", "ad": "review", "etkin": False}
    assert catalog["beceriler"][0]["etkin"] is False
    assert traversal["ok"] is False


async def test_acikca_secim_yalniz_sonraki_tur_icin_butceli_baglam_hazirlar(tmp_path: Path):
    home = tmp_path / "home"
    root = tmp_path / "project"
    skill = home / ".hermes/skills/research/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: research\ndescription: Araştırır\n---\n" + "x" * 20_000, encoding="utf-8"
    )
    root.mkdir()
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=home)

    selected = await _request(session, lines, "yetenek.kullan", {"tur": "beceri", "ad": "research"})
    context = session._take_capability_context()  # Tek-kullanımlık sözleşmenin doğrudan kanıtı.
    second = session._take_capability_context()
    await session.close()

    assert selected == {"ok": True, "tur": "beceri", "ad": "research", "sonraki_tur": True}
    assert "research" in context and len(context) <= 6_500
    assert second == ""


async def test_katalog_kurallari_ve_kullanici_katmanini_listeler_detay_okur(tmp_path: Path):
    """P-015/P-016: ~/.claude/CLAUDE.md ve .claude/rules dosyaları talimat sekmesinde görünür."""
    home, root = tmp_path / "home", tmp_path / "project"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_text("genel kural", encoding="utf-8")
    (root / ".claude" / "rules").mkdir(parents=True)
    (root / ".claude" / "rules" / "test.md").write_text(
        "---\npaths: ['tests/**']\n---\nTest kuralı", encoding="utf-8"
    )
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=home)

    result = await _request(session, lines, "yetenek.katalog", {})
    detail = await _request(
        session, lines, "yetenek.detay", {"tur": "talimat", "ad": ".claude/rules/test.md"}
    )
    yabanci = await _request(
        session, lines, "yetenek.detay", {"tur": "talimat", "ad": "../../etc/passwd"}
    )
    await session.close()

    adlar = {t["ad"]: t for t in result["talimatlar"]}
    assert adlar["~/.claude/CLAUDE.md"]["kaynak"] == "kullanici"
    assert "tests/**" in adlar[".claude/rules/test.md"]["aciklama"]
    assert detail["ok"] is True and "Test kuralı" in detail["icerik"]
    assert yabanci["ok"] is False

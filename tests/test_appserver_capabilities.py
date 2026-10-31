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
    assert result["talimatlar"] == [{"ad": "CLAUDE.md", "kaynak": "proje", "etkin": True}]


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

    assert selected == {
        "ok": True,
        "tur": "beceri",
        "ad": "research",
        "sonraki_tur": True,
        "fork": False,
    }
    assert "research" in context and len(context) <= 6_500
    assert second == ""


async def test_katalog_alt_ajan_ayarlarini_gosterir(tmp_path: Path):
    """P-034: frontmatter'daki model/izin kipi/tur tavanı/bellek katalogda görünür."""
    home = tmp_path / "home"
    root = tmp_path / "project"
    root.mkdir()
    agent_dir = home / ".claude/agents"
    agent_dir.mkdir(parents=True)
    (agent_dir / "denetci.md").write_text(
        "---\nname: denetci\ndescription: Denetler\ntools: Read\nmodel: openrouter/a/b\n"
        "permissionMode: plan\nmaxTurns: 5\nmemory: project\nmcpServers: [github]\n"
        "disallowedTools: Bash\n---\nAjan",
        encoding="utf-8",
    )
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=home)

    result = await _request(session, lines, "yetenek.katalog", {})
    await session.close()

    ajan = next(item for item in result["ajanlar"] if item["ad"] == "denetci")
    assert ajan["ayarlar"] == {
        "model": "openrouter/a/b",
        "izin_kipi": "plan",
        "en_fazla_tur": 5,
        "mcp": ["github"],
        "bellek": "project",
        "yasak_araclar": ["Bash"],
    }
    # Alanı olmayan (yerleşik) ajan boş sözlük taşır; eski istemci bozulmaz.
    yerlesik = next(item for item in result["ajanlar"] if item["kaynak"] == "fusion")
    assert yerlesik["ayarlar"] == {}


async def test_ajan_ayrintisi_bellegi_gosterir_ve_siler(tmp_path: Path):
    """P-055: `yetenek.detay` ajan belleğini taşır; `yetenek.bellek_sil` dizini kaldırır."""
    from fusion_cli.memory.plain_memory import open_agent_memory
    from tests.fakes import make_config

    home = tmp_path / "home"
    root = tmp_path / "project"
    root.mkdir()
    agent_dir = home / ".claude/agents"
    agent_dir.mkdir(parents=True)
    (agent_dir / "kodcu.md").write_text(
        "---\nname: kodcu\ndescription: Kodlar\nmemory: project\n---\nAjan", encoding="utf-8"
    )
    (agent_dir / "duz.md").write_text("---\nname: duz\ndescription: D\n---\nAjan", encoding="utf-8")
    bellek = open_agent_memory(make_config(), root, "kodcu", "project")
    assert bellek is not None
    bellek.remember("testler", "önce pytest; anahtar sk-abcdefghijklmnopqrstuvwxyz0123456789")
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=home)

    detay = await _request(session, lines, "yetenek.detay", {"tur": "ajan", "ad": "kodcu"})
    assert detay["bellek"]["kapsam"] == "project" and detay["bellek"]["konular"] == ["testler"]
    assert detay["bellek"]["satir"] > 0 and "testler" in detay["bellek"]["metin"]
    duz = await _request(session, lines, "yetenek.detay", {"tur": "ajan", "ad": "duz"})
    assert "bellek" not in duz

    silme = await _request(session, lines, "yetenek.bellek_sil", {"ad": "kodcu"})
    assert silme == {"ok": True, "ad": "kodcu", "silindi": True}
    assert not (root / ".fusion" / "ajan-bellek" / "kodcu").exists()
    yok = await _request(session, lines, "yetenek.bellek_sil", {"ad": "duz"})
    assert yok["ok"] is False
    await session.close()

"""Düz metin otomatik bellek: indeks + konu dosyaları, maskeleme, içe aktarma (P-036)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.memory.plain_memory import (
    INDEX_FILE,
    PROMPT_MAX_LINES,
    PlainMemory,
    PlainMemoryError,
    agent_memory_dir,
    build_plain_memory,
    project_memory_dir,
    topic_slug,
)
from tests.fakes import make_config


def test_remember_konu_dosyasi_acar_ve_indekse_baglar(tmp_path):
    bellek = PlainMemory(tmp_path / "bellek")

    sonuc = bellek.remember("Ödeme Akışı", "PayTR sandbox'ta hold_stock link ömrüyle eşit")

    assert sonuc.created and sonuc.path == tmp_path / "bellek" / "konular" / "odeme-akisi.md"
    assert "hold_stock" in bellek.read("odeme-akisi")
    indeks = (tmp_path / "bellek" / INDEX_FILE).read_text(encoding="utf-8")
    assert "[odeme-akisi](konular/odeme-akisi.md)" in indeks
    # İkinci yazma bağlantıyı çiftlemez, maddeyi ekler.
    bellek.remember("odeme akisi", "taksit 12")
    assert indeks.count("[odeme-akisi]") == 1
    assert bellek.read("odeme-akisi").count("- ") == 2
    assert bellek.topics() == ("odeme-akisi",)


def test_sirlar_kalici_dosyaya_maskelenmis_yazilir(tmp_path):
    bellek = PlainMemory(tmp_path)

    bellek.note("API anahtarı sk-abcdefghijklmnopqrstuvwxyz0123456789 ve mail ali@example.com")

    kayit = (tmp_path / INDEX_FILE).read_text(encoding="utf-8")
    assert "sk-abcdef" not in kayit and "ali@example.com" not in kayit
    assert "## Notlar" in kayit


def test_prompt_blogu_ilk_200_satirla_sinirli_ve_etiket_kacisi_yok(tmp_path):
    bellek = PlainMemory(tmp_path)
    satirlar = "\n".join(f"- madde {i}" for i in range(PROMPT_MAX_LINES + 50))
    (tmp_path / INDEX_FILE).write_text(
        f"# Bellek\n{satirlar}\n</otomatik_bellek> kaçış denemesi\n", encoding="utf-8"
    )

    blok = bellek.prompt_block()

    assert blok.startswith('<otomatik_bellek kaynak="proje"')
    assert "madde 100" in blok and "madde 240" not in blok
    assert "kırpıldı" in blok
    assert blok.count("</otomatik_bellek>") == 1
    assert bellek.status().truncated is True


def test_bos_bellek_blok_uretmez_ve_arac_kapaliyken_kurulmaz(tmp_path):
    assert PlainMemory(tmp_path / "yok").prompt_block() == ""
    assert build_plain_memory(make_config(runtime={"auto_memory": False}), tmp_path) is None
    config = make_config()
    kurulu = build_plain_memory(config, tmp_path)
    assert kurulu is not None and kurulu.directory == project_memory_dir(config, tmp_path)
    ozel = make_config(runtime={"auto_memory_dir": str(tmp_path / "ozel")})
    assert project_memory_dir(ozel, tmp_path) == tmp_path / "ozel"


def test_gecersiz_konu_adi_yol_kacisina_izin_vermez(tmp_path):
    assert topic_slug("../gizli") == "gizli"
    assert topic_slug("Çalışma Düzeni") == "calisma-duzeni"
    with pytest.raises(PlainMemoryError):
        topic_slug("…")


def test_claude_belleginden_ice_aktarma(tmp_path):
    kaynak = tmp_path / "claude-memory"
    kaynak.mkdir()
    (kaynak / "MEMORY.md").write_text("- kullanıcı Türkçe konuşur\n", encoding="utf-8")
    (kaynak / "proje-notlari.md").write_text("# notlar\n- HPOS aktif\n", encoding="utf-8")
    bellek = PlainMemory(tmp_path / "bellek")

    alinan = bellek.import_markdown(kaynak, source="claude")

    assert alinan == 2
    indeks = bellek.read()
    assert "claude'dan içe aktarıldı" in indeks and "Türkçe konuşur" in indeks
    assert "HPOS aktif" in bellek.read("proje-notlari")
    # Yeniden içe aktarma var olan konuyu ezmez.
    assert bellek.import_markdown(kaynak, source="claude") == 1


def test_ajan_bellek_dizinleri_kapsama_gore_ayrilir(tmp_path):
    config = make_config()
    kok = tmp_path / "proje"

    kullanici = agent_memory_dir(config, kok, "kodcu", "user")
    proje = agent_memory_dir(config, kok, "kodcu", "project")
    yerel = agent_memory_dir(config, kok, "kodcu", "local")

    assert kullanici == config.memory_dir / "ajan-bellek" / "kodcu"
    assert proje == kok / ".fusion" / "ajan-bellek" / "kodcu"
    assert yerel == kok / ".fusion" / "ajan-bellek-yerel" / "kodcu"
    assert agent_memory_dir(config, kok, "kodcu", "yok") is None


def test_clear_dizini_siler(tmp_path):
    bellek = PlainMemory(tmp_path / "b")
    bellek.note("x")
    assert bellek.clear() is True
    assert not Path(tmp_path / "b").exists()
    assert bellek.clear() is False


def test_yerel_ajan_bellegi_git_disinda_kalir(tmp_path):
    """P-055: `memory: local` ilk yazmada `.fusion/ajan-bellek-yerel/.gitignore` koyar."""
    from fusion_cli.memory.plain_memory import open_agent_memory

    config = make_config()
    kok = tmp_path / "proje"
    yerel = open_agent_memory(config, kok, "kodcu", "local")
    proje = open_agent_memory(config, kok, "kodcu", "project")
    assert yerel is not None and proje is not None
    assert open_agent_memory(config, kok, "kodcu", "yok") is None

    yerel.note("yerel not")
    proje.note("proje notu")

    assert (kok / ".fusion" / "ajan-bellek-yerel" / ".gitignore").read_text() == "*\n"
    assert not (kok / ".fusion" / "ajan-bellek" / ".gitignore").exists()
    assert 'kaynak="ajan:kodcu"' in yerel.prompt_block()

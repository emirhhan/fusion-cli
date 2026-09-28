"""`ToolStarted` için şimdiki-zamanlı Türkçe durum cümlesi — saf mantık."""

from __future__ import annotations

from fusion_cli.appserver.tool_progress import progress_text


def test_read_file_yol_ile_okunuyor_der() -> None:
    assert progress_text("read_file", {"path": "src/app.py"}) == "src/app.py okunuyor"


def test_write_file_yol_ile_yaziliyor_der() -> None:
    assert progress_text("write_file", {"path": "a.py"}) == "a.py yazılıyor"


def test_web_search_sorguyu_tirnak_icinde_gosterir() -> None:
    assert progress_text("web_search", {"query": "fusion cli"}) == "'fusion cli' web'de aranıyor"


def test_chrome_navigate_yalniz_host_gosterir() -> None:
    assert progress_text("chrome_navigate", {"url": "https://ads.google.com/anasayfa"}) == (
        "chrome ile ads.google.com açılıyor"
    )


def test_run_shell_komutu_tirnak_icinde_gosterir() -> None:
    beklenen = "kabuk komutu 'npm test' çalıştırılıyor"
    assert progress_text("run_shell", {"command": "npm test"}) == beklenen


def test_git_alt_komutunu_kullanir() -> None:
    # Araç şeması alanı `subcommand`dır (bkz. `tools/builtin.py`).
    assert progress_text("git", {"subcommand": "status"}) == "git status çalıştırılıyor"


def test_uzun_argumanlar_kirpilir() -> None:
    uzun_sorgu = "x" * 200
    sonuc = progress_text("web_search", {"query": uzun_sorgu})

    assert sonuc.startswith("'xxx")
    assert "…" in sonuc
    assert len(sonuc) < len(uzun_sorgu)


def test_eslenmemis_arac_jenerik_ama_okunabilir_cumle_kurar() -> None:
    sonuc = progress_text("mcp_ozel_arac", {})

    assert sonuc == "mcp ozel arac çalıştırılıyor"


def test_bos_argumanlarda_bile_dusmez() -> None:
    for ad in ("read_file", "web_search", "run_shell", "git", "glob", "list_dir"):
        assert isinstance(progress_text(ad, {}), str)
        assert progress_text(ad, {})

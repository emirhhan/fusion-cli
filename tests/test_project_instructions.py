"""Hedef projenin CLAUDE.md/AGENTS.md gibi talimat dosyasını okuma — saf fonksiyon."""

from __future__ import annotations

from fusion_cli.engines.agent.project_instructions import (
    MAX_CHARS,
    MAX_LINKED_CHARS,
    read_project_instructions,
)


def test_bulunan_ilk_dosya_okunur(tmp_path):
    (tmp_path / "AGENTS.md").write_text("kural: testsiz kod yok", encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert "kural: testsiz kod yok" in sonuc
    assert "AGENTS.md" in sonuc


def test_oncelik_claude_md_agents_mdden_once_gelir(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("claude kurali", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("agents kurali", encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert "claude kurali" in sonuc
    assert "agents kurali" not in sonuc


def test_dosya_yoksa_bos_dondurur(tmp_path):
    assert read_project_instructions(tmp_path) == ""


def test_bos_dosya_atlanip_bir_sonrakine_gecilir(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("   ", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("gercek kural", encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert "gercek kural" in sonuc


def test_uzun_dosya_kirpilir(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("x" * (MAX_CHARS + 500), encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert "kırpıldı" in sonuc
    assert len(sonuc) < MAX_CHARS + 500


def test_bos_projeye_de_gercek_ortam_aktarilir(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import project_instructions as instructions

    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    monkeypatch.setattr(
        "shutil.which", lambda name: "/opt/homebrew/bin/godot" if name == "godot" else None
    )
    result = instructions.read_all_instructions(tmp_path, None)
    assert str(tmp_path.resolve()) in result
    assert "Darwin" in result
    assert "arm64" in result
    assert "göreli" in result
    assert "/opt/homebrew/bin/godot" in result


# --- Talimat zinciri --------------------------------------------------------- #
#
# Bir talimat dosyası çoğu kez asıl kuralı KENDİSİ taşımaz, işaret eder:
# bu deponun CLAUDE.md'si "kod yazmadan önce RULES.md okunur" der ve mimari,
# isimlendirme, katman kuralları orada durur. İşaret edilen dosya prompta hiç
# girmiyorsa kural katmanı modelin kendi kararına kalır — modülün var oluş
# sebebi ise tam olarak bu şansı ortadan kaldırmaktır.


def test_talimat_dosyasinin_isaret_ettigi_kural_dosyasi_da_okunur(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "Kod yazmadan önce [RULES.md](RULES.md) okunur.", encoding="utf-8"
    )
    (tmp_path / "RULES.md").write_text("## Katman Sınırları\nçekirdek UI bilmez", encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert "çekirdek UI bilmez" in sonuc
    assert "RULES.md" in sonuc


def test_kok_disini_gosteren_baglanti_okunmaz(tmp_path):
    """Talimat dosyası GÜVENİLMEZ girdidir: kök dışına çıkan yol izlenmez."""
    disari = tmp_path.parent / "sizinti.md"
    disari.write_text("gizli icerik", encoding="utf-8")
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / "CLAUDE.md").write_text("bkz [dis](../sizinti.md)", encoding="utf-8")

    sonuc = read_project_instructions(proje)

    assert "gizli icerik" not in sonuc


def test_mutlak_yol_baglantisi_okunmaz(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("bkz [gecmis](/etc/hosts)", encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert "/etc/hosts" not in sonuc.replace("[gecmis](/etc/hosts)", "")


def test_url_baglantisi_okunmaz(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("bkz [dok](https://example.com/a.md)", encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert "example.com" in sonuc  # metnin kendisi kalır
    assert "<proje_kurali" not in sonuc  # ama okunmuş bir kural dosyası eklenmez


def test_kural_dosyasi_olmayan_uzantiya_dokunulmaz(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("bkz [ayar](.env)", encoding="utf-8")
    (tmp_path / ".env").write_text("API_KEY=gizli", encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert "API_KEY" not in sonuc


def test_olmayan_baglanti_ana_talimati_dusurmez(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("ana kural\nbkz [yok](YOK.md)", encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert "ana kural" in sonuc


def test_zincir_ikinci_seviyeye_inmez(tmp_path):
    """Bir seviye izlenir: derin zincir bağlam bütçesini sessizce tüketirdi."""
    (tmp_path / "CLAUDE.md").write_text("bkz [a](A.md)", encoding="utf-8")
    (tmp_path / "A.md").write_text("birinci seviye\nbkz [b](B.md)", encoding="utf-8")
    (tmp_path / "B.md").write_text("ikinci seviye", encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert "birinci seviye" in sonuc
    assert "ikinci seviye" not in sonuc


def test_baglanti_butcesi_asilmaz(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("bkz [a](A.md)", encoding="utf-8")
    (tmp_path / "A.md").write_text("x" * (MAX_LINKED_CHARS * 3), encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert sonuc.count("x") <= MAX_LINKED_CHARS

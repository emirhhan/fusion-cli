"""`fusion setup` — anahtar sorma ve hazır ders yükleme.

Gerçek terminal gerekmez: soru soran taraf enjekte edilir.
"""

from __future__ import annotations

import pytest
from rich.console import Console

from fusion_cli.cli import setup_command


@pytest.fixture
def kurulum_dizini(tmp_path, monkeypatch):
    """Kurulumun yazacağı dizini tmp_path'e al ve ders yüklemeyi sessizleştir."""
    monkeypatch.setattr(setup_command, "user_config_dir", lambda: tmp_path)
    monkeypatch.setattr(setup_command, "_seed_lessons", lambda console: None)
    return tmp_path


def _asker(*cevaplar):
    """Sırayla verilen cevapları döndüren sahte soru sorucu."""
    kuyruk = list(cevaplar)

    def _ask(prompt: str) -> str:
        return kuyruk.pop(0) if kuyruk else ""

    return _ask


def test_anahtarlar_env_dosyasina_yazilir(kurulum_dizini):
    setup_command.run_setup(Console(quiet=True), ask=_asker("sk-openrouter", "nv-nim"))

    icerik = (kurulum_dizini / ".env").read_text(encoding="utf-8")

    assert "OPENROUTER_API_KEY=sk-openrouter" in icerik
    assert "NVIDIA_NIM_API_KEY=nv-nim" in icerik


def test_nim_opsiyoneldir_bos_gecilebilir(kurulum_dizini):
    setup_command.run_setup(Console(quiet=True), ask=_asker("sk-openrouter", ""))

    icerik = (kurulum_dizini / ".env").read_text(encoding="utf-8")

    assert "OPENROUTER_API_KEY=sk-openrouter" in icerik
    assert "NVIDIA_NIM_API_KEY=\n" in icerik


def test_openrouter_bos_birakilamaz(kurulum_dizini):
    """Zorunlu anahtar boş geçilirse tekrar sorulur."""
    setup_command.run_setup(Console(quiet=True), ask=_asker("", "", "sk-nihayet", ""))

    icerik = (kurulum_dizini / ".env").read_text(encoding="utf-8")

    assert "OPENROUTER_API_KEY=sk-nihayet" in icerik


def test_var_olan_env_dosyasinin_uzerine_yazilmaz(kurulum_dizini):
    """Kurulum sihirbazı kullanıcının anahtarlarını silemez."""
    (kurulum_dizini / ".env").write_text("OPENROUTER_API_KEY=eski\n", encoding="utf-8")

    def _sorulmamali(prompt: str) -> str:  # pragma: no cover - çağrılırsa test düşer
        raise AssertionError("mevcut .env varken anahtar sorulmamalı")

    setup_command.run_setup(Console(quiet=True), ask=_sorulmamali)

    assert (kurulum_dizini / ".env").read_text(encoding="utf-8") == "OPENROUTER_API_KEY=eski\n"


def test_anahtar_dosyasi_yalnizca_sahibine_okunur(kurulum_dizini):
    setup_command.run_setup(Console(quiet=True), ask=_asker("sk-x", ""))

    kip = (kurulum_dizini / ".env").stat().st_mode & 0o777

    assert kip == 0o600, f"anahtar dosyası izni geniş: {oct(kip)}"


def test_terminal_yokken_soru_sorulmaz(kurulum_dizini, monkeypatch):
    """Boru hattında ve CI'da soru sormak kurulumu kilitlerdi."""
    monkeypatch.setattr(setup_command.sys.stdin, "isatty", lambda: False)

    setup_command.run_setup(Console(quiet=True))

    icerik = (kurulum_dizini / ".env").read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY=\n" in icerik, "şablon bırakılmalı"


def test_config_sablonu_da_olusur(kurulum_dizini):
    setup_command.run_setup(Console(quiet=True), ask=_asker("sk-x", ""))

    assert (kurulum_dizini / "config.yaml").exists()


def test_anahtar_alindiysa_tekrar_gir_denmez(kurulum_dizini, capsys):
    """Az önce girilen anahtarı tekrar istemek kullanıcıyı şaşırtır."""
    console = Console(force_terminal=False, width=200)
    setup_command.run_setup(console, ask=_asker("sk-x", ""))

    cikti = capsys.readouterr().out

    assert "anahtarlarını gir" not in cikti
    assert "fusion` yaz" in cikti


def test_anahtar_alinmadiysa_nereye_yazilacagi_soylenir(kurulum_dizini, monkeypatch, capsys):
    monkeypatch.setattr(setup_command.sys.stdin, "isatty", lambda: False)

    setup_command.run_setup(Console(force_terminal=False, width=200))

    assert "anahtarlarını gir" in capsys.readouterr().out

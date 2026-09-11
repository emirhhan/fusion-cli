"""Protokol akışı UTF-8 olmak ZORUNDA ve kodlama hatası sessizce yutulamaz.

Ölçüldü (Windows CI, beş koşu): `proje.oku` isteği 30 saniyede yanıt vermedi,
stderr BOŞ geldi. Zincir:

1. Okunan dosyanın içeriği "Fusion hazır" — `ı` (U+0131) cp1252'de YOK.
2. `proje.listele` cevabı yalnız dosya adları taşıyor (ASCII) ve yazılıyor;
   `proje.oku` cevabı dosya İÇERİĞİNİ taşıyor ve `sys.stdout.write`
   `UnicodeEncodeError` fırlatıyor.
3. `UnicodeEncodeError`, `ValueError`'ın ALT SINIFI. Yazıcı
   `except (BrokenPipeError, ValueError)` ile onu yakalayıp `SystemExit(0)`
   veriyordu: süreç sessizce cevapsız kalıyor.

Sonuç yalnız CI'yı değil kullanıcıyı vuruyordu: Windows'ta Türkçe karakter içeren
bir dosyayı okumak oturumu sessizce öldürüyordu.
"""

from __future__ import annotations

import io

import pytest

from fusion_cli.appserver import server as server_module


class _Cp1252Stream(io.TextIOBase):
    """Windows'un varsayılan konsol akışını taklit eder."""

    def write(self, text: str) -> int:
        text.encode("cp1252")  # Türkçe karakterde UnicodeEncodeError
        return len(text)

    def flush(self) -> None:
        return None


def test_kodlama_hatasi_sessiz_cikisa_donusmez(monkeypatch):
    """Kodlama hatası SystemExit(0) ile yutulursa arıza teşhis edilemez hâle gelir."""
    monkeypatch.setattr(server_module.sys, "stdout", _Cp1252Stream())

    with pytest.raises(UnicodeEncodeError):
        server_module._stdout_writer('{"icerik": "Fusion hazır"}')


def test_kopan_boru_hala_sessizce_durdurur(monkeypatch):
    """Yazılamayan kanala olay biriktirmek bellek sızdırır; bu davranış korunur."""

    class _Kopuk(io.TextIOBase):
        def write(self, text: str) -> int:
            raise BrokenPipeError

    monkeypatch.setattr(server_module.sys, "stdout", _Kopuk())

    with pytest.raises(SystemExit):
        server_module._stdout_writer("{}")


def test_stdio_utf8e_ayarlanir(monkeypatch):
    """Protokol JSON'u işletim sisteminin yereline bakmadan UTF-8 olmalı."""
    kayit: list[dict[str, object]] = []

    class _Akis(io.TextIOBase):
        encoding = "cp1252"

        def reconfigure(self, **kwargs: object) -> None:
            kayit.append(kwargs)

    monkeypatch.setattr(server_module.sys, "stdout", _Akis())
    monkeypatch.setattr(server_module.sys, "stdin", _Akis())

    server_module.force_utf8_stdio()

    assert len(kayit) == 2
    assert all(item.get("encoding") == "utf-8" for item in kayit), kayit

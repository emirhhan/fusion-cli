"""Küçük düzeltmeler: görsel bağlam tahmini, onay mesajı (A1-43, A1-44)."""

from __future__ import annotations

from fusion_cli.core.types import Message
from fusion_cli.engines.agent import denial
from fusion_cli.engines.agent.history import IMAGE_CHARS_ESTIMATE, total_chars


def test_gorsel_ekli_mesaj_bagam_buyuklugune_katki_yapar():
    duz = [Message("user", "bak")]
    gorselli = [Message("user", "bak", images=("data:image/png;base64,AAAA",) * 2)]

    assert total_chars(gorselli) - total_chars(duz) == 2 * IMAGE_CHARS_ESTIMATE


def test_onay_alinamadi_mesaji_dosya_yazmayi_onaysiz_vaat_etmez():
    metin = denial.APPROVAL_UNAVAILABLE_MESSAGE

    assert "dosya araçları onay istemez" not in metin
    assert "salt okuyan" in metin


def test_cop_listesi_sinirlidir_en_yeniler_gosterilir(monkeypatch):
    import time
    from types import SimpleNamespace

    from fusion_cli.engines.agent import history_tools

    simdi = time.time()
    girdiler = [
        SimpleNamespace(id=f"id{i}", deleted_at=simdi - i, original=f"/p/{i}.txt")
        for i in range(50)
    ]
    monkeypatch.setattr(history_tools, "list_trash", lambda _dizin: girdiler)
    monkeypatch.setattr(history_tools, "trash_dir", lambda: None)

    satirlar = history_tools._trash_lines()

    assert len([s for s in satirlar if s.startswith("- ")]) == history_tools.MAX_TRASH_LINES
    assert "id0" in satirlar[1] and "20 girdi daha" in satirlar[-1]

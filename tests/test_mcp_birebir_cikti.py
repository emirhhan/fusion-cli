"""MCP çıktı sınırları birebir (#240)."""

from __future__ import annotations

from mcp.types import CallToolResult, TextContent

from fusion_cli.mcp_bridge import output_limits
from fusion_cli.mcp_bridge.content import normalize_call_result


def test_kucuk_cikti_aynen_buyuk_basarili_cikti_dosyaya(tmp_path):
    assert output_limits.limit_output("kısa", ok=True, directory=tmp_path) == "kısa"
    buyuk = "a" * 60_000
    sonuc = output_limits.limit_output(buyuk, ok=True, directory=tmp_path)
    (dosya,) = tmp_path.iterdir()
    assert str(dosya) in sonuc and dosya.read_text() == buyuk
    assert len(sonuc) < 3000


def test_token_siniri_ortam_degiskeniyle_ve_arac_meta_siniri():
    metin = "b" * 45_000  # ~11.250 token, 50k karakter altı
    assert output_limits.limit_output(metin, ok=True, environ={}) == metin
    assert "kaydedildi" in output_limits.limit_output(
        metin, ok=True, environ={"MAX_MCP_OUTPUT_TOKENS": "5000"}, directory=None
    )
    assert output_limits.declared_limit({"anthropic/maxResultSizeChars": 900_000}) == 500_000
    assert (
        output_limits.limit_output("c" * 200_000, ok=True, declared_chars=500_000) == "c" * 200_000
    )


def test_hata_metninin_basi_ve_sonu_tutulur():
    metin = "B" * 5000 + "orta" * 2000 + "S" * 5000
    sonuc = output_limits.limit_output(metin, ok=False)
    assert sonuc.startswith("B" * 5000) and sonuc.endswith("S" * 5000)
    assert "orta" not in sonuc


def test_eski_20000_kirpmasi_kalkti(monkeypatch, tmp_path):
    monkeypatch.setattr(output_limits, "results_dir", lambda: tmp_path)
    metin = "x" * 30_000
    sonuc = normalize_call_result(CallToolResult(content=[TextContent(type="text", text=metin)]))
    assert sonuc.output == metin


def test_kaydedilen_dosya_ilk_andan_0600_ile_acilir(tmp_path, monkeypatch):
    import os

    acilan: list[int] = []
    gercek_open = os.open

    def _izle(path, flags, mode=0o777, *args, **kwargs):
        acilan.append(mode)
        return gercek_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr(output_limits.os, "open", _izle)

    output_limits.limit_output("b" * 60_000, ok=True, directory=tmp_path)

    (dosya,) = tmp_path.iterdir()
    assert acilan == [0o600]
    assert dosya.stat().st_mode & 0o777 == 0o600


def test_eski_kayitlar_saklama_suresinden_sonra_temizlenir(tmp_path):
    import os
    import time

    eski = tmp_path / "mcp-eski.txt"
    eski.write_text("x")
    yeni = tmp_path / "mcp-yeni.txt"
    yeni.write_text("y")
    baska = tmp_path / "kullanici.txt"
    baska.write_text("z")
    gecmis = time.time() - (output_limits.RETENTION_DAYS + 1) * 86_400
    os.utime(eski, (gecmis, gecmis))
    os.utime(baska, (gecmis, gecmis))

    output_limits.limit_output("c" * 60_000, ok=True, directory=tmp_path)

    assert not eski.exists() and yeni.exists() and baska.exists()


def test_kisitli_kipte_kaydedilen_cikti_okunabilir_baska_dis_yol_okunamaz(tmp_path, monkeypatch):
    import pytest

    from fusion_cli.core.errors import PathAccessError
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools.files import resolve_path

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "veri"))
    proje = tmp_path / "proje"
    proje.mkdir()
    sonuc = output_limits.limit_output("d" * 60_000, ok=True)
    (dosya,) = output_limits.results_dir().iterdir()
    assert str(dosya) in sonuc
    context = ToolContext(root=proje, restrict_to_root=True)

    assert resolve_path(context, str(dosya)) == dosya.resolve()
    with pytest.raises(PathAccessError):
        resolve_path(context, str(dosya), write=True)
    disari = tmp_path / "veri" / "baska.txt"
    disari.write_text("gizli")
    with pytest.raises(PathAccessError):
        resolve_path(context, str(disari))

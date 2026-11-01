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
    assert output_limits.limit_output("c" * 200_000, ok=True, declared_chars=500_000) == "c" * 200_000


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

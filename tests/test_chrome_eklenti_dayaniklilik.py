"""Chrome eklentisi: sekme seçimi ve panel yeniden bağlanma davranışının kaynak güvenceleri."""

from __future__ import annotations

from pathlib import Path

EXTENSION = Path(__file__).resolve().parents[1] / "chrome-extension"


def test_tab_select_http_olmayan_sekmeyi_anlamli_hatayla_reddeder() -> None:
    """R1-31. Ölçüldü (30 Ekim): tab.url yoksa `new URL(undefined)` 'Invalid URL' atıyordu."""
    core = (EXTENSION / "core.js").read_text(encoding="utf-8")
    secim = core[core.index('command.islem === "tab_select"') :]
    secim = secim[: secim.index('command.islem === "tab_close"')]
    assert secim.index("Yalnız http(s) sekmeleri") < secim.index("new URL(tab.url)")


def test_panel_dinleme_ustel_bekler_ve_hatayi_tekrarlamaz() -> None:
    """R1-33. Ölçüldü (30 Ekim): kopuk bağlantıda her 2 sn'de aynı hata yazılıyordu."""
    panel = (EXTENSION / "panel.js").read_text(encoding="utf-8")
    assert "MAX_RETRY_MS" in panel and "2 ** listenFailures" in panel
    # Hata/rozet iyileşmesi test_remediation_permission_js gerçek taşıma regresyonunda ölçülür.


def test_panel_uc_izin_modu_sunar_varsayilan_otomatik() -> None:
    """#434: Claude in Chrome modları: Manually / Automatically approve, Skip all approvals."""
    html = (EXTENSION / "panel.html").read_text(encoding="utf-8")
    secici = html[
        html.index('<select id="mode"') : html.index("</select>", html.index('<select id="mode"'))
    ]
    assert secici.count("<option") == 3
    for name in ("Manually approve", "Automatically approve", "Skip all approvals"):
        assert name in secici
    assert 'value="edits"' not in secici and 'value="plan"' not in secici
    panel = (EXTENSION / "panel.js").read_text(encoding="utf-8")
    assert 'const PANEL_MODES = ["security", "auto", "bypass"]' in panel
    assert ': settings.mod ? "security" : "auto"' in panel

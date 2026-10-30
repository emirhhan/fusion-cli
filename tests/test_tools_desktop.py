"""macOS masaüstü araçları izin, yol ve sonuç sözleşmesini korur."""

from __future__ import annotations

import subprocess

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import build_request
from fusion_cli.tools import desktop
from fusion_cli.tools.builtin import build_registry


def test_macos_disinda_acik_hata_doner(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(desktop.sys, "platform", "linux")

    result = desktop.desktop_click({"x": 1, "y": 2}, ToolContext(root=tmp_path))

    assert not result.ok
    assert "macOS" in result.output


def test_uygulama_adi_kabuga_girmeden_acilir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(desktop.subprocess, "run", fake_run)
    name = "TextEdit; $(touch /tmp/yan-etki)"

    result = desktop.desktop_open({"app": name}, ToolContext(root=tmp_path))

    assert result.ok
    assert calls == [["open", "-a", name]]


def test_erisilebilirlik_izni_yokken_tiklama_yapilmaz(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setattr(desktop, "_framework", lambda: object())
    monkeypatch.setattr(desktop, "_trusted", lambda framework: False)
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(desktop, "_post_mouse_click", lambda framework, x, y: calls.append((x, y)))

    result = desktop.desktop_click({"x": 50, "y": 40}, ToolContext(root=tmp_path))

    assert not result.ok
    assert "Erişilebilirlik" in result.output
    assert calls == []


def test_tiklama_koordinatlari_dogrulanir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    for x in (True, -1, "3"):
        assert not desktop.desktop_click({"x": x, "y": 2}, ToolContext(root=tmp_path)).ok


def test_izinli_tiklama_kuvars_olayina_gider(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    framework = object()
    monkeypatch.setattr(desktop, "_framework", lambda: framework)
    monkeypatch.setattr(desktop, "_trusted", lambda loaded: True)
    calls: list[tuple[object, int, int]] = []
    monkeypatch.setattr(
        desktop, "_post_mouse_click", lambda loaded, x, y: calls.append((loaded, x, y))
    )

    result = desktop.desktop_click({"x": 50, "y": 40}, ToolContext(root=tmp_path))

    assert result.ok
    assert calls == [(framework, 50, 40)]


def test_metin_sonucta_sizdirilmaz(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setattr(desktop, "_framework", lambda: object())
    monkeypatch.setattr(desktop, "_trusted", lambda loaded: True)
    typed: list[str] = []
    monkeypatch.setattr(desktop, "_post_text", lambda loaded, value: typed.append(value))

    result = desktop.desktop_type({"text": "özel metin"}, ToolContext(root=tmp_path))

    assert result.ok
    assert typed == ["özel metin"]
    assert "özel metin" not in result.output


def test_tus_ve_kaydirma_izinli_oturuma_gider(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    framework = object()
    monkeypatch.setattr(desktop, "_framework", lambda: framework)
    monkeypatch.setattr(desktop, "_trusted", lambda loaded: True)
    keys: list[tuple[int, bool, bool]] = []
    scrolls: list[int] = []
    monkeypatch.setattr(
        desktop,
        "_post_key",
        lambda loaded, code, *, command, shift: keys.append((code, command, shift)),
    )
    monkeypatch.setattr(desktop, "_post_scroll", lambda loaded, lines: scrolls.append(lines))
    context = ToolContext(root=tmp_path)

    assert desktop.desktop_key({"key": "a", "command": True}, context).ok
    assert desktop.desktop_scroll({"lines": -3}, context).ok
    assert keys == [(0, True, False)]
    assert scrolls == [-3]


def test_bilinmeyen_tus_ve_asiri_kaydirma_reddedilir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    context = ToolContext(root=tmp_path)

    assert not desktop.desktop_key({"key": "cmd+rm"}, context).ok
    assert not desktop.desktop_scroll({"lines": 101}, context).ok


def test_masaustu_eylemleri_onay_akisini_atlamaz() -> None:
    registry = build_registry()
    for name in ("desktop_click", "desktop_type", "desktop_key", "desktop_scroll"):
        tool = registry.get(name)
        assert tool is not None and tool.mutating
        assert not build_request(tool, {}).unattended_safe


# --- Dalga 4 (T1-43) -----------------------------------------------------------------


import pytest as _pytest  # noqa: E402


@_pytest.mark.parametrize(
    ("ad", "kod"),
    [
        ("return", 36),
        ("esc", 53),
        ("delete", 51),
        ("home", 115),
        ("end", 119),
        ("pageup", 116),
        ("pagedown", 121),
        ("f1", 122),
        ("f12", 111),
        ("l", 37),
        ("t", 17),
        ("r", 15),
        ("n", 45),
        ("1", 18),
        ("0", 29),
    ],
)
def test_genisletilmis_tus_adlari_cozulur(ad, kod):
    assert desktop.resolve_key(ad) == kod


def test_bilinmeyen_tus_none_doner():
    assert desktop.resolve_key("cmd+rm") is None


def test_option_ve_control_bayraklari_iletilir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setattr(desktop, "_framework", lambda: object())
    monkeypatch.setattr(desktop, "_trusted", lambda loaded: True)
    alinan: list[dict] = []
    monkeypatch.setattr(
        desktop, "_post_key", lambda loaded, code, **bayrak: alinan.append({"code": code, **bayrak})
    )

    sonuc = desktop.desktop_key({"key": "left", "option": True}, ToolContext(root=tmp_path))

    assert sonuc.ok and alinan[0]["option"] is True and alinan[0]["code"] == 123


# --- Parite P-032: tuş dizgisi, tekrar, basılı tutma ------------------------------------


def _izinli(monkeypatch) -> list[dict]:
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setattr(desktop, "_framework", lambda: object())
    monkeypatch.setattr(desktop, "_trusted", lambda loaded: True)
    alinan: list[dict] = []
    monkeypatch.setattr(
        desktop, "_post_key", lambda loaded, code, **bayrak: alinan.append({"code": code, **bayrak})
    )
    return alinan


def test_tus_dizgisi_sirayla_gonderilir(tmp_path, monkeypatch) -> None:
    """Ölçüldü (31 Ekim): `desktop_key` tek tuş alıyordu; 'cmd+shift+4 enter' reddediliyordu."""
    alinan = _izinli(monkeypatch)

    sonuc = desktop.desktop_key({"key": "cmd+shift+4 enter"}, ToolContext(root=tmp_path))

    assert sonuc.ok, sonuc.output
    assert [(k["code"], k["command"], k["shift"]) for k in alinan] == [
        (21, True, True),
        (36, False, False),
    ]


def test_tekrar_sayisi_ve_basili_tutma(tmp_path, monkeypatch) -> None:
    alinan = _izinli(monkeypatch)

    sonuc = desktop.desktop_key(
        {"key": "down", "repeat": 3, "hold_ms": 250}, ToolContext(root=tmp_path)
    )

    assert sonuc.ok
    assert len(alinan) == 3 and all(k["hold_ms"] == 250 for k in alinan)


def test_eski_boolean_bayraklar_dizgiyle_birlesir(tmp_path, monkeypatch) -> None:
    alinan = _izinli(monkeypatch)

    assert desktop.desktop_key({"key": "shift+tab", "command": True}, ToolContext(root=tmp_path)).ok
    assert alinan[0]["command"] is True and alinan[0]["shift"] is True


def test_asiri_tekrar_ve_tutma_reddedilir(tmp_path, monkeypatch) -> None:
    _izinli(monkeypatch)
    context = ToolContext(root=tmp_path)

    assert not desktop.desktop_key({"key": "a", "repeat": 0}, context).ok
    assert not desktop.desktop_key({"key": "a", "repeat": 999}, context).ok
    assert not desktop.desktop_key({"key": "a", "hold_ms": 99_999}, context).ok
    assert not desktop.desktop_key({"key": "cmd+"}, context).ok

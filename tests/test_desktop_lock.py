"""Tek oturum kilidi: canlı başka süreç tutuyorsa masaüstü eylemi reddedilir (P-033)."""

from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import desktop, desktop_lock, desktop_mouse


def test_bos_kilit_alinir_ve_ayni_surec_tazeler(tmp_path) -> None:
    yol = tmp_path / "oturum.lock"

    assert desktop_lock.claim(pid=100, now=10.0, path=yol) is None
    assert desktop_lock.claim(pid=100, now=20.0, path=yol) is None
    assert desktop_lock._read(yol) == (100, 20.0)


def test_canli_baska_surec_tutuyorsa_reddedilir(tmp_path, monkeypatch) -> None:
    yol = tmp_path / "oturum.lock"
    monkeypatch.setattr(desktop_lock, "_is_alive", lambda pid: True)
    desktop_lock.claim(pid=100, now=10.0, path=yol)

    hata = desktop_lock.claim(pid=200, now=11.0, path=yol)

    assert hata is not None and "süreç 100" in hata
    assert desktop_lock._read(yol) == (100, 10.0)


def test_olu_ya_da_bayat_sahip_devralinir(tmp_path, monkeypatch) -> None:
    yol = tmp_path / "oturum.lock"
    desktop_lock.claim(pid=100, now=10.0, path=yol)

    monkeypatch.setattr(desktop_lock, "_is_alive", lambda pid: False)
    assert desktop_lock.claim(pid=200, now=11.0, path=yol) is None
    monkeypatch.setattr(desktop_lock, "_is_alive", lambda pid: True)
    assert desktop_lock.claim(pid=300, now=11.0 + desktop_lock.LOCK_STALE_S + 1, path=yol) is None
    assert desktop_lock._read(yol) == (300, 11.0 + desktop_lock.LOCK_STALE_S + 1)


def test_bozuk_kilit_dosyasi_engel_degil_ve_birakma_yalniz_sahibe(tmp_path) -> None:
    yol = tmp_path / "oturum.lock"
    yol.write_text("{bozuk", encoding="utf-8")

    assert desktop_lock.claim(pid=100, now=1.0, path=yol) is None
    desktop_lock.release(pid=200, path=yol)
    assert yol.exists()
    desktop_lock.release(pid=100, path=yol)
    assert not yol.exists()


def test_fare_ve_klavye_araclari_kilidi_kontrol_eder(tmp_path, monkeypatch) -> None:
    """Ölçüldü (31 Ekim): iki Fusion süreci aynı anda olay gönderebiliyordu."""
    for module in (desktop, desktop_mouse):
        monkeypatch.setattr(module, "_mac_only", lambda: None)
        monkeypatch.setattr(module, "_framework", lambda: object())
        monkeypatch.setattr(module, "_trusted", lambda loaded: True)
    monkeypatch.setattr(desktop_lock, "claim", lambda **_: "Başka bir Fusion oturumu kullanıyor.")
    gonderilen: list[str] = []
    monkeypatch.setattr(
        desktop_mouse, "_post_mouse", lambda loaded, plan: gonderilen.append("fare")
    )
    monkeypatch.setattr(desktop, "_post_text", lambda loaded, value: gonderilen.append("metin"))
    context = ToolContext(root=tmp_path)

    fare = desktop_mouse.desktop_click({"x": 1, "y": 1}, context)
    metin = desktop.desktop_type({"text": "a"}, context)

    assert not fare.ok and not metin.ok and "Başka bir Fusion" in fare.output
    assert gonderilen == []

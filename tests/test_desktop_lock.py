"""Tek oturum kilidi: canlı başka tur tutuyorsa masaüstü eylemi reddedilir (P-033)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from fusion_cli.core.desktop_frame import DesktopFrame
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import desktop, desktop_lock, desktop_mouse
from fusion_cli.tools.desktop_lock import LockOwner


def test_bos_kilit_alinir_ve_ayni_tur_tazeler(tmp_path) -> None:
    yol = tmp_path / "oturum.lock"

    assert desktop_lock.claim(pid=100, token="t1", now=10.0, path=yol) is None
    assert desktop_lock.claim(pid=100, token="t1", now=20.0, path=yol) is None
    assert desktop_lock._read(yol) == LockOwner(100, "t1", 20.0, "süreç 100")


def test_canli_baska_surec_tutuyorsa_reddedilir(tmp_path, monkeypatch) -> None:
    yol = tmp_path / "oturum.lock"
    monkeypatch.setattr(desktop_lock, "_is_alive", lambda pid: True)
    desktop_lock.claim(pid=100, token="a", now=10.0, path=yol, label="Fusion CLI · proje")

    hata = desktop_lock.claim(pid=200, token="b", now=11.0, path=yol)

    # #429: hata kilidi tutan oturumu adıyla anar.
    assert hata is not None and "Fusion CLI · proje" in hata and "oturumdan çık" in hata
    assert desktop_lock._read(yol) == LockOwner(100, "a", 10.0, "Fusion CLI · proje")


def test_ayni_surecte_baska_sohbet_de_bekler(tmp_path, monkeypatch) -> None:
    """Ölçüldü (31 Ekim): kilit yalnız pid taşıdığı için aynı appserver'daki iki sohbet
    birbirini hiç görmüyordu."""
    yol = tmp_path / "oturum.lock"
    monkeypatch.setattr(desktop_lock, "_is_alive", lambda pid: True)
    desktop_lock.claim(pid=100, token="sohbet-a", now=10.0, path=yol)

    assert desktop_lock.claim(pid=100, token="sohbet-b", now=11.0, path=yol) is not None
    desktop_lock.release(pid=100, token="sohbet-a", path=yol)
    assert desktop_lock.claim(pid=100, token="sohbet-b", now=12.0, path=yol) is None


def test_olu_sahip_devralinir_canli_sahip_sureyle_devralinmaz(tmp_path, monkeypatch) -> None:
    """#429: kilit oturum çıkana kadar kalır; süreye bağlı devralma yok, ölü süreç devredilir."""
    yol = tmp_path / "oturum.lock"
    desktop_lock.claim(pid=100, token="a", now=10.0, path=yol)

    monkeypatch.setattr(desktop_lock, "_is_alive", lambda pid: False)
    assert desktop_lock.claim(pid=200, token="b", now=11.0, path=yol) is None
    monkeypatch.setattr(desktop_lock, "_is_alive", lambda pid: True)
    assert desktop_lock.claim(pid=300, token="c", now=11.0 + 86_400, path=yol) is not None
    assert desktop_lock._read(yol) == LockOwner(200, "b", 11.0, "süreç 200")


def test_bozuk_kilit_dosyasi_engel_degil_ve_birakma_yalniz_sahibe(tmp_path) -> None:
    yol = tmp_path / "oturum.lock"
    yol.write_text("{bozuk", encoding="utf-8")

    assert desktop_lock.claim(pid=100, token="a", now=1.0, path=yol) is None
    desktop_lock.release(pid=200, token="a", path=yol)
    desktop_lock.release(pid=100, token="baska", path=yol)
    assert yol.exists()
    desktop_lock.release(pid=100, token="a", path=yol)
    assert not yol.exists()
    desktop_lock.release(pid=100, token="a", path=yol)  # yok: sessiz


def test_eski_bicim_kilit_okunur(tmp_path) -> None:
    yol = tmp_path / "oturum.lock"
    yol.write_text('{"pid": 7, "touched": 3.0}', encoding="utf-8")

    assert desktop_lock._read(yol) == LockOwner(7, "", 3.0)


def test_es_zamanli_alma_tek_kazanan_birakir(tmp_path, monkeypatch) -> None:
    """Ölçüldü (31 Ekim): oku-sonra-yaz atomik değildi; boş kilidi aynı anda gören herkes
    alıyordu."""
    yol = tmp_path / "oturum.lock"
    monkeypatch.setattr(desktop_lock, "_is_alive", lambda pid: True)

    with ThreadPoolExecutor(max_workers=16) as pool:
        sonuclar = list(
            pool.map(
                lambda i: desktop_lock.claim(pid=100, token=f"tur-{i}", now=5.0, path=yol),
                range(48),
            )
        )

    assert sonuclar.count(None) == 1
    sahip = desktop_lock._read(yol)
    assert sahip is not None and sahip.token.startswith("tur-")


def test_fare_ve_klavye_araclari_kilidi_kontrol_eder(tmp_path, monkeypatch) -> None:
    """Ölçüldü (31 Ekim): iki Fusion süreci aynı anda olay gönderebiliyordu."""
    for module in (desktop, desktop_mouse):
        monkeypatch.setattr(module, "_mac_only", lambda: None)
        monkeypatch.setattr(module, "_framework", lambda: object())
        monkeypatch.setattr(module, "_trusted", lambda loaded: True)
    belirtecler: list[str] = []

    def mesgul(**kwargs: object) -> str:
        belirtecler.append(str(kwargs.get("token")))
        return "Başka bir Fusion oturumu kullanıyor."

    monkeypatch.setattr(desktop_lock, "claim", mesgul)
    gonderilen: list[str] = []
    monkeypatch.setattr(
        desktop_mouse, "_post_mouse", lambda loaded, plan: gonderilen.append("fare")
    )
    monkeypatch.setattr(desktop, "_post_text", lambda loaded, value: gonderilen.append("metin"))
    context = ToolContext(root=tmp_path)
    context.desktop.frame = DesktopFrame(100, 100, 0.0, 0.0, 100.0, 100.0, 1)

    fare = desktop_mouse.desktop_click({"x": 1, "y": 1}, context)
    metin = desktop.desktop_type({"text": "a"}, context)

    assert not fare.ok and not metin.ok and "Başka bir Fusion" in fare.output
    # CLI'de süreç = oturum (#429): belirteç boştur.
    assert gonderilen == [] and belirtecler == ["", ""]


async def test_tur_bitince_kilit_kalir_oturum_cikinca_kalkar(tmp_path, monkeypatch) -> None:
    """#429: "releases it when the session exits, not when the task finishes"."""
    from fusion_cli.cli import session
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.tools import desktop_turn

    from .fakes import AlwaysApprove, make_config

    yol = tmp_path / "oturum.lock"
    monkeypatch.setattr(desktop_lock, "lock_path", lambda: yol)
    monkeypatch.setattr(desktop_lock, "_existing_lock_path", lambda: yol)
    kalan: list[object] = []

    async def run(task, deps, **kwargs):
        assert desktop_turn.claim_lock(deps.tool_context) is None
        kalan.append(desktop_lock._read(yol))
        if task == "patla":
            raise RuntimeError("tur çöktü")
        return AgentOutcome(final_text="bitti", messages=[])

    monkeypatch.setattr(session, "run_agent", run)
    config = make_config(memory_dir=tmp_path / "memory")
    ortak = {"sinks": (), "prompter_factory": lambda drain: AlwaysApprove(), "root": tmp_path}

    await session.run_agent_task("merhaba", config, interactive=False, **ortak)
    assert kalan[0] is not None and yol.exists()
    with pytest.raises(RuntimeError):
        await session.run_agent_task("patla", config, interactive=False, **ortak)
    assert len(kalan) == 2 and yol.exists()
    desktop_turn.end_session("")
    assert not yol.exists()

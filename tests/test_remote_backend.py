"""`AppSessionBackend`: zaman aşımı, temizlik ve oturum hazırlığı hataları (R1-03, R1-04)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from fusion_cli.remote import backend as backend_module
from fusion_cli.remote.backend import AppSessionBackend


class _Session:
    """Sahte oturum: `yanit` ile istek adına göre sonuç; `sessiz` adlara hiç sonuç yazmaz."""

    def __init__(self, writer: Any) -> None:
        self.writer = writer
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.replies: dict[str, dict[str, Any]] = {}
        self.silent: set[str] = set()
        self.raising: set[str] = set()

    async def handle(self, request: Any) -> None:
        self.requests.append((request.name, request.data))
        if request.name in self.raising:
            raise RuntimeError("oturum çöktü")
        if request.name in self.silent:
            return
        data = self.replies.get(request.name, {"ok": True, "metin": "bitti"})
        self.writer(json.dumps({"tip": "sonuc", "id": request.id, "veri": data}))


def _backend(tmp_path: Path) -> tuple[AppSessionBackend, _Session]:
    holder: list[_Session] = []

    def factory(writer: Any) -> _Session:
        holder.append(_Session(writer))
        return holder[0]

    return AppSessionBackend(factory, tmp_path), holder[0]


async def test_sonuc_gelmeyen_istek_zaman_asimina_ugrar_ve_future_sizmaz(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backend_module, "CALL_RESULT_GRACE_SECONDS", 0.05)
    backend, session = _backend(tmp_path)
    session.silent.add("sohbet.listele")
    with pytest.raises(TimeoutError):
        await backend.call("sohbet.listele", {})
    assert backend._results == {}


async def test_oturum_istisnasi_future_sizdirmaz(tmp_path: Path) -> None:
    backend, session = _backend(tmp_path)
    session.raising.add("sohbet.listele")
    with pytest.raises(RuntimeError):
        await backend.call("sohbet.listele", {})
    assert backend._results == {}


async def test_tur_zaman_asimi_kesip_failed_yazar_ve_durumu_temizler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backend_module, "TURN_TIMEOUT_SECONDS", 0.05)
    backend, session = _backend(tmp_path)

    async def hang(request: Any) -> None:
        session.requests.append((request.name, request.data))
        if request.name == "tur.calistir":
            await asyncio.sleep(30)
            return
        session.writer(json.dumps({"tip": "sonuc", "id": request.id, "veri": {"ok": True}}))

    session.handle = hang  # type: ignore[method-assign]
    events: list[tuple[str, dict[str, Any]]] = []
    await asyncio.wait_for(
        backend.start("r1", "görev", lambda kind, payload: events.append((kind, payload))), 5
    )
    assert events[-1][0] == "failed"
    assert "tur.kes" in [name for name, _ in session.requests]
    assert backend._active_run is None and backend._sink is None
    assert backend._results == {}


async def test_start_istisnada_aktif_gorev_ve_sink_temizlenir(tmp_path: Path) -> None:
    backend, session = _backend(tmp_path)
    session.raising.add("tur.calistir")
    with pytest.raises(RuntimeError):
        await backend.start("r1", "görev", lambda *_: None)
    assert backend._active_run is None and backend._sink is None
    assert backend._results == {}


async def test_gecersiz_kok_gorevi_failed_yapar_ve_tur_calistirmaz(tmp_path: Path) -> None:
    backend, session = _backend(tmp_path)
    session.replies["oturum.baslat"] = {"ok": False, "metin": "Proje kökü geçerli değil."}
    backend.prepare_run("r1", {"root": "/yok", "chat_id": "c1"})
    events: list[tuple[str, dict[str, Any]]] = []
    await backend.start("r1", "görev", lambda kind, payload: events.append((kind, payload)))
    assert [name for name, _ in session.requests] == ["oturum.baslat"]
    assert events[-1] == ("failed", {"summary": "Proje kökü geçerli değil."})


async def test_kademe_secilemezse_gorev_failed_olur(tmp_path: Path) -> None:
    backend, session = _backend(tmp_path)
    session.replies["kademe.sec"] = {"ok": False, "metin": "Kademe yok."}
    backend.prepare_run("r1", {"tier": "x"})
    events: list[tuple[str, dict[str, Any]]] = []
    await backend.start("r1", "görev", lambda kind, payload: events.append((kind, payload)))
    assert [name for name, _ in session.requests] == ["kademe.sec"]
    assert events[-1][0] == "failed"


def _goal_session(session: _Session, turns: list[dict[str, Any]], on_turn: Any = None) -> None:
    """`tur.calistir` sırayla `turns` sonuçlarını döndürür; diğer istekler 'ok'."""

    async def handle(request: Any) -> None:
        session.requests.append((request.name, request.data))
        data: dict[str, Any] = {"ok": True}
        if request.name == "tur.calistir":
            data = turns.pop(0)
            if on_turn is not None:
                await on_turn()
        session.writer(json.dumps({"tip": "sonuc", "id": request.id, "veri": data}))

    session.handle = handle  # type: ignore[method-assign]


async def test_uzak_gorev_hedef_devamini_surer_ve_karari_ozete_yazar(tmp_path: Path) -> None:
    """Ölçüldü (31 Ekim): uzak istemci (`/goal` etkin sohbette) `hedef_devam`ı yok sayıyordu;
    hedef ilk turdan sonra telefonda hiç ilerlemiyor, karar metni de görünmüyordu."""
    backend, session = _backend(tmp_path)
    _goal_session(
        session,
        [
            {
                "ok": True,
                "metin": "bir test kırık",
                "hedef": {"eylem": "devam", "metin": "◎ Hedef henüz karşılanmadı"},
                "hedef_devam": "Hedefi sürdür",
            },
            {"ok": True, "metin": "hepsi yeşil", "hedef": {"eylem": "tamam", "metin": "✓ Hedef"}},
        ],
    )
    events: list[tuple[str, dict[str, Any]]] = []

    await backend.start("r1", "testleri düzelt", lambda kind, p: events.append((kind, p)))

    turlar = [data["gorev"] for name, data in session.requests if name == "tur.calistir"]
    assert turlar == ["testleri düzelt", "Hedefi sürdür"]
    assert events[-1][0] == "done"
    assert "hepsi yeşil" in events[-1][1]["summary"] and "✓ Hedef" in events[-1][1]["summary"]


async def test_uzak_gorev_iptal_edilince_hedef_devami_baslamaz(tmp_path: Path) -> None:
    backend, session = _backend(tmp_path)

    async def kes() -> None:
        await backend.cancel("r1")

    _goal_session(
        session,
        [{"ok": True, "metin": "yarım", "hedef": {"metin": "◎"}, "hedef_devam": "sürdür"}],
        on_turn=kes,
    )
    await backend.start("r1", "görev", lambda *_: None)

    assert [name for name, _ in session.requests].count("tur.calistir") == 1

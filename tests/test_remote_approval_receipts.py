"""Gerçek host makbuzu, telefon teyidi ve cihaz ekran güveni davranışları."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fusion_cli.appserver.bridges import PendingQuestions
from fusion_cli.appserver.session import AppSession
from fusion_cli.memory.run_store import SqliteRunStore
from fusion_cli.remote.approval_confirmation import ApprovalConfirmations
from fusion_cli.remote.backend import AppSessionBackend
from fusion_cli.remote.devices import DeviceRegistry
from fusion_cli.remote.rpc import RemoteService
from fusion_cli.remote.tasks import TaskStore
from tests.test_remote_service import FakeBackend, FakeClock


async def test_backend_gercek_host_makbuzu_karari_tek_kez_uygular(tmp_path: Path) -> None:
    pending = PendingQuestions()
    identifier, future = pending.new_question()

    def factory(writer: Any) -> AppSession:
        # Yalnız gerçek host cevap rotası çalışır; motor ve kullanıcı dizini kurulmaz.
        session = AppSession.__new__(AppSession)
        session.pending = pending
        session._writer = writer
        return session

    backend = AppSessionBackend(factory, tmp_path)
    assert await backend.answer(identifier, {"secim": "once"})
    answer = await future
    assert answer["secim"] == "once" and answer["decisionId"]
    assert await backend.answer(identifier, {"secim": "once"})
    assert not await backend.answer(identifier, {"secim": "deny"})
    assert not await backend.answer("kapanmis", {"secim": "once"})


def test_teyit_cihaz_gorev_soru_karar_icerik_ve_sureye_bagli_tek_kullanimlik() -> None:
    clock = FakeClock()
    confirmations = ApprovalConfirmations(clock)
    payload = {"arac": "desktop_click", "hedef": "Gönder"}
    token = confirmations.issue("d", "r", "q", "once", payload)
    for device, run, question, choice, content in [
        ("baska", "r", "q", "once", payload),
        ("d", "baska", "q", "once", payload),
        ("d", "r", "baska", "once", payload),
        ("d", "r", "q", "session", payload),
        ("d", "r", "q", "once", {"hedef": "Başka"}),
    ]:
        assert not confirmations.consume(token, device, run, question, choice, content)
    assert confirmations.consume(token, "d", "r", "q", "once", payload)
    assert not confirmations.consume(token, "d", "r", "q", "once", payload)
    token = confirmations.issue("d", "r", "q", "once", payload)
    clock.value += 121
    assert not confirmations.consume(token, "d", "r", "q", "once", payload)


def make_service(tmp_path: Path) -> tuple[RemoteService, DeviceRegistry, FakeBackend, FakeClock]:
    clock = FakeClock()
    registry = DeviceRegistry(tmp_path / "devices.json", clock)
    backend = FakeBackend()
    service = RemoteService(
        clock=clock,
        registry=registry,
        backend=backend,
        store=TaskStore(SqliteRunStore(tmp_path / "runs.sqlite3", clock=clock)),
    )
    return service, registry, backend, clock


_YAZMA_SORUSU = {
    "tur": "onay",
    "tehlike": "Yıkıcı işlem",
    "secenekler": [{"deger": "once"}, {"deger": "deny"}],
}


@pytest.mark.parametrize("tool", ["desktop_click", "mcp__write", "unknown_tool", "run_shell"])
async def test_kapsamsiz_telefon_ikinci_teyitle_bile_onay_veremez(
    tmp_path: Path, tool: str
) -> None:
    """R1-01: ikinci teyit, işlemin gerektirdiği kapsamın eksikliğini kapatmaz."""
    service, registry, backend, _clock = make_service(tmp_path)
    phone = registry.add("Tel", "signed", frozenset({"agent.run"}))
    service._questions["q"] = ("run", {**_YAZMA_SORUSU, "arac": tool})

    cevap = await service.call(phone, "approvals.respond", {"questionId": "q", "choice": "once"})
    teyit = await service.call(phone, "approvals.challenge", {"questionId": "q", "choice": "once"})
    red = await service.call(phone, "approvals.respond", {"questionId": "q", "choice": "deny"})

    assert (cevap.error, teyit.error) == ("yetki_yok", "yetki_yok")
    assert red.ok  # Reddetmek her zaman serbest.
    assert backend.answers == [("q", {"secim": "deny"})]


@pytest.mark.parametrize("tool", ["desktop_click", "mcp__write", "unknown_tool", "run_shell"])
async def test_kapsamli_telefon_yuksek_etkili_onayi_ikinci_teyitle_verir(
    tmp_path: Path, tool: str
) -> None:
    service, registry, backend, _clock = make_service(tmp_path)
    phone = registry.add("Tel", "signed", frozenset({"agent.run", "project.write"}))
    service._questions["q"] = ("run", {**_YAZMA_SORUSU, "arac": tool})
    initial = await service.call(phone, "approvals.respond", {"questionId": "q", "choice": "once"})
    assert initial.error == "step_up" and backend.answers == []
    challenge = await service.call(
        phone, "approvals.challenge", {"questionId": "q", "choice": "once"}
    )
    accepted = await service.call(
        phone,
        "approvals.respond",
        {
            "questionId": "q",
            "choice": "once",
            "confirmation": challenge.data["challengeId"],
        },
    )
    assert accepted.ok and accepted.data["accepted"]
    assert phone.scopes == frozenset({"agent.run", "project.write"})


async def test_sunulmayan_oturum_karari_ve_imzasiz_teyit_reddedilir(tmp_path: Path) -> None:
    service, registry, _backend, _clock = make_service(tmp_path)
    question = {"tur": "onay", "arac": "run_shell", "secenekler": [{"deger": "once"}]}
    service._questions["q"] = ("run", question)
    for channel in ("signed", "telegram"):
        phone = registry.add("Tel", channel, frozenset({"agent.run"}))
        assert not (
            await service.call(
                phone,
                "approvals.challenge",
                {
                    "questionId": "q",
                    "choice": "session",
                },
            )
        ).ok
    assert not (
        await service.call(
            phone,
            "approvals.challenge",
            {
                "questionId": "q",
                "choice": "once",
            },
        )
    ).ok


async def test_ekran_guveni_baska_cihaza_ve_telegrama_tasinmaz(tmp_path: Path) -> None:
    service, registry, _backend, _clock = make_service(tmp_path)
    phone = registry.add("Tel", "signed", frozenset({"desktop.observe"}))
    telegram = registry.add("Bot", "telegram", frozenset({"desktop.observe"}))
    other = registry.add("Başka", "signed", frozenset({"desktop.observe"}))
    await service.call(phone, "screen.request", {"remember": True})
    service.approve_screen(phone.device_id)
    assert not (
        await service.call(telegram, "screen.request", {"remember": True, "confirmed": True})
    ).ok
    assert (await service.call(other, "screen.request", {})).data["state"] == "pending"
    await service.call(phone, "devices.revoke", {})
    assert not registry.get(phone.device_id).screen_trusted  # type: ignore[union-attr]
    assert service.screen_gate.status(phone.device_id)[0] == "none"


async def test_oturum_karari_yalniz_sunuldugunda_ve_ikinci_teyitle_verilir(tmp_path: Path) -> None:
    service, registry, backend, _clock = make_service(tmp_path)
    phone = registry.add("Tel", "signed", frozenset({"agent.run", "project.write"}))
    service._questions["q"] = (
        "run",
        {
            "tur": "onay",
            "arac": "run_shell",
            "secenekler": [{"deger": "session"}],
        },
    )
    request = {"questionId": "q", "choice": "session"}
    assert (await service.call(phone, "approvals.respond", request)).error == "step_up"
    challenge = await service.call(phone, "approvals.challenge", request)
    assert (
        await service.call(
            phone,
            "approvals.respond",
            {
                **request,
                "confirmation": challenge.data["challengeId"],
            },
        )
    ).ok
    assert backend.answers == [("q", {"secim": "session"})]


async def test_host_kabul_etmediginde_rpc_basari_bildirmez(tmp_path: Path) -> None:
    service, registry, _backend, _clock = make_service(tmp_path)

    def factory(writer: Any) -> AppSession:
        session = AppSession.__new__(AppSession)
        session.pending = PendingQuestions()
        session._writer = writer
        return session

    service._backend = AppSessionBackend(factory, tmp_path)
    phone = registry.add("Tel", "signed", frozenset({"agent.run", "project.write"}))
    service._questions["q"] = (
        "run",
        {
            "tur": "onay",
            "arac": "run_shell",
            "secenekler": [{"deger": "once"}],
        },
    )
    result = await service.call(phone, "approvals.respond", {"questionId": "q", "choice": "once"})
    assert not result.ok and result.error == "cevap_reddedildi"
    assert "q" in service._questions
    assert not await service.answer_from_desktop("q", "once")


async def test_masaustu_yaniti_gercek_host_makbuzuyla_ilerler(tmp_path: Path) -> None:
    service, _registry, _backend, _clock = make_service(tmp_path)
    pending = PendingQuestions()
    identifier, future = pending.new_question()

    def factory(writer: Any) -> AppSession:
        session = AppSession.__new__(AppSession)
        session.pending = pending
        session._writer = writer
        return session

    service._backend = AppSessionBackend(factory, tmp_path)
    service._questions[identifier] = (
        "run",
        {
            "tur": "onay",
            "arac": "run_shell",
            "secenekler": [{"deger": "once"}],
        },
    )
    assert await service.answer_from_desktop(identifier, "once")
    assert (await future)["secim"] == "once"
    assert identifier not in service._questions

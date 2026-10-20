"""Uzaktan görev servisi: eşleştirme, imza, yetki, step-up, idempotency, bind politikası."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from fusion_cli.remote.asgi import RemoteApp
from fusion_cli.remote.bind import BindPolicy, BindRefusedError, validate_bind
from fusion_cli.remote.devices import DeviceRegistry
from fusion_cli.remote.pairing import PairingError, PairingService
from fusion_cli.remote.rate_limit import FailureLimiter
from fusion_cli.remote.redaction import notification_summary, redact_payload
from fusion_cli.remote.rpc import RemoteService
from fusion_cli.remote.scopes import DEFAULT_SCOPES, parse_scopes
from fusion_cli.remote.signing import SignatureVerifier, sign
from fusion_cli.remote.tasks import TaskStore


class FakeClock:
    def __init__(self) -> None:
        self.value = 1_000_000.0

    def now(self) -> float:
        return self.value

    def monotonic(self) -> float:
        return self.value


class FakeBackend:
    """Sahte yürütücü: soru sorabilir, bekleyebilir, iptal edilebilir."""

    def __init__(self) -> None:
        self.started: list[str] = []
        self.answers: list[tuple[str, dict[str, Any]]] = []
        self.release = asyncio.Event()
        self.ask: dict[str, Any] | None = None
        self.options: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses: dict[str, dict[str, Any]] = {}

    def prepare_run(self, run_id: str, options: dict[str, Any]) -> None:
        self.options[run_id] = options

    async def call(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, data))
        return self.responses.get(name, {"ok": True})

    async def start(self, run_id: str, prompt: str, sink: Any) -> None:
        self.started.append(prompt)
        sink("started", {})
        if self.ask is not None:
            sink(
                "question",
                {
                    "questionId": "q1",
                    "secenekler": [{"deger": "once"}, {"deger": "deny"}],
                    **self.ask,
                },
            )
        await self.release.wait()
        sink("done", {"summary": "bitti sk-abcdefghijklmnopqrstuv"})

    async def cancel(self, run_id: str) -> bool:
        self.release.set()
        return True

    async def answer(self, question_id: str, answer: dict[str, Any]) -> bool:
        self.answers.append((question_id, answer))
        return True

    def pause_supported(self) -> bool:
        return False

    def kits(self) -> list[dict[str, Any]]:
        return [
            {"slug": "acik", "title": "Açık", "remote_allowed": True, "prompt": "kit işi"},
            {"slug": "kapali", "remote_allowed": False, "prompt": "x"},
        ]


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.clock = FakeClock()
        counter = iter(range(1, 10_000))
        self.registry = DeviceRegistry(
            tmp_path / "devices.json",
            self.clock,
            token_bytes=lambda n: bytes(next(counter) % 256 for _ in range(n)),
        )
        self.pairing = PairingService(
            self.registry, self.clock, token_bytes=lambda n: bytes(range(n))
        )
        self.backend = FakeBackend()
        self.service = RemoteService(
            clock=self.clock,
            registry=self.registry,
            store=TaskStore(
                self.clock, token_bytes=lambda n: bytes(next(counter) % 256 for _ in range(n))
            ),
            backend=self.backend,
        )
        self.limiter = FailureLimiter(self.clock)
        self.app = RemoteApp(
            service=self.service,
            registry=self.registry,
            pairing=self.pairing,
            verifier=SignatureVerifier(self.clock),
            limiter=self.limiter,
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://127.0.0.1"
        )
        self.sequence = 0

    def pair(self, scopes: list[str] | None = None) -> tuple[str, bytes]:
        code, _ = self.pairing.begin(scopes)
        self.pairing.submit(code, "Telefon")
        device = self.pairing.approve(code)
        claimed = self.pairing.claim(code)
        assert claimed is not None
        return device.device_id, device.secret

    async def rpc(
        self,
        device_id: str,
        secret: bytes,
        method: str,
        params: dict[str, Any] | None = None,
        **over: Any,
    ) -> httpx.Response:
        self.sequence = over.get("sequence", self.sequence + 1)
        body = json.dumps({"method": method, "params": params or {}}).encode()
        timestamp = int(self.clock.now()) + over.get("skew", 0)
        nonce = over.get("nonce", f"n{self.sequence}")
        signature = sign(secret, "POST", "/v1/rpc", timestamp, nonce, self.sequence, body)
        headers = {
            "x-fusion-device": device_id,
            "x-fusion-ts": str(timestamp),
            "x-fusion-nonce": nonce,
            "x-fusion-seq": str(self.sequence),
            "x-fusion-sig": over.get("signature", signature),
        }
        return await self.client.post("/v1/rpc", content=body, headers=headers)


@pytest.fixture
async def rig(tmp_path: Path) -> Any:
    instance = Rig(tmp_path)
    yield instance
    await instance.service.aclose()
    await instance.client.aclose()


async def test_varsayilan_kapsam_salt_okuma_ve_ajan_gorevi(rig: Rig) -> None:
    code, _ = rig.pairing.begin(None)
    rig.pairing.submit(code, "Tel")
    device = rig.pairing.approve(code)
    assert device.scopes == DEFAULT_SCOPES
    assert "project.write" not in device.scopes


async def test_eslestirme_kodu_tek_kullanimlik_ve_onaysiz_sir_vermez(rig: Rig) -> None:
    code, _ = rig.pairing.begin(None)
    rig.pairing.submit(code, "Tel")
    assert rig.pairing.claim(code) is None  # masaüstü onayı yok
    with pytest.raises(PairingError):
        rig.pairing.submit(code, "Başka")  # ikinci kullanım
    rig.pairing.approve(code)
    assert rig.pairing.claim(code) is not None
    with pytest.raises(PairingError):
        rig.pairing.claim(code)  # sır yalnız bir kez


async def test_eslestirme_kodu_suresi_dolar(rig: Rig) -> None:
    code, _ = rig.pairing.begin(None)
    rig.clock.value += 121
    with pytest.raises(PairingError):
        rig.pairing.submit(code, "Geç")


async def test_imzali_istek_calisir_imzasiz_ve_bozuk_reddedilir(rig: Rig) -> None:
    device_id, secret = rig.pair()
    ok = await rig.rpc(device_id, secret, "service.status")
    assert ok.status_code == 200 and ok.json()["ok"] is True
    bad = await rig.rpc(device_id, secret, "service.status", signature="00" * 32)
    assert bad.status_code == 401
    unsigned = await rig.client.post("/v1/rpc", content=b"{}")
    assert unsigned.status_code == 401


async def test_yeniden_oynatma_ve_eski_sira_reddedilir(rig: Rig) -> None:
    device_id, secret = rig.pair()
    first = await rig.rpc(device_id, secret, "service.status", nonce="ayni", sequence=5)
    assert first.status_code == 200
    replay = await rig.rpc(device_id, secret, "service.status", nonce="ayni", sequence=5)
    assert replay.status_code == 401
    stale = await rig.rpc(device_id, secret, "service.status", nonce="yeni", sequence=4)
    assert stale.status_code == 401


async def test_saat_sapmasi_reddedilir(rig: Rig) -> None:
    device_id, secret = rig.pair()
    late = await rig.rpc(device_id, secret, "service.status", skew=-500)
    assert late.status_code == 401


async def test_iptal_edilen_cihaz_aninda_reddedilir(rig: Rig) -> None:
    device_id, secret = rig.pair()
    assert (await rig.rpc(device_id, secret, "service.status")).status_code == 200
    rig.registry.revoke(device_id)
    assert (await rig.rpc(device_id, secret, "service.status")).status_code == 401


async def test_ust_uste_basarisiz_kimlik_kilitler(rig: Rig) -> None:
    device_id, secret = rig.pair()
    for _ in range(5):
        await rig.rpc(device_id, secret, "service.status", signature="ab" * 32)
    locked = await rig.rpc(device_id, secret, "service.status")
    assert locked.status_code == 429


async def test_yetkisiz_kapsam_reddedilir(rig: Rig) -> None:
    device_id, secret = rig.pair(["project.read"])
    response = await rig.rpc(device_id, secret, "tasks.create", {"prompt": "yap"})
    assert response.json()["error"] == "yetki_yok"


async def test_gorev_idempotent_ve_olay_sirasi_monoton(rig: Rig) -> None:
    device_id, secret = rig.pair()
    params = {"prompt": "test et", "idempotencyKey": "k1"}
    first = (await rig.rpc(device_id, secret, "tasks.create", params)).json()["data"]
    second = (await rig.rpc(device_id, secret, "tasks.create", params)).json()["data"]
    assert first["runId"] == second["runId"] and second["duplicate"] is True
    await asyncio.sleep(0)
    rig.backend.release.set()
    await asyncio.sleep(0.05)
    events = (await rig.rpc(device_id, secret, "tasks.events", {"runId": first["runId"]})).json()[
        "data"
    ]
    seqs = [event["seq"] for event in events["events"]]
    assert seqs == sorted(seqs) and seqs == list(range(1, len(seqs) + 1))
    assert len(rig.backend.started) == 1
    assert "sk-abcdefghijklmnopqrstuv" not in json.dumps(events)


async def test_step_up_onayi_uzaktan_verilemez_ama_reddedilebilir(rig: Rig) -> None:
    rig.backend.ask = {"tur": "onay", "arac": "desktop_click", "baslik": "Tıkla", "hedef": "x"}
    device_id, secret = rig.pair(["project.read", "agent.run", "desktop.control"])
    created = (await rig.rpc(device_id, secret, "tasks.create", {"prompt": "yap"})).json()["data"]
    await asyncio.sleep(0.05)
    approve = (
        await rig.rpc(
            device_id, secret, "approvals.respond", {"questionId": "q1", "choice": "once"}
        )
    ).json()
    assert approve["error"] == "step_up"
    assert rig.backend.answers == []
    deny = (
        await rig.rpc(
            device_id, secret, "approvals.respond", {"questionId": "q1", "choice": "deny"}
        )
    ).json()
    assert deny["data"]["accepted"] is True and rig.backend.answers[0][1] == {"secim": "deny"}
    rig.backend.release.set()
    assert created["runId"]


async def test_oturum_secenegi_uzaktan_kabul_edilmez(rig: Rig) -> None:
    rig.backend.ask = {"tur": "onay", "arac": "run_shell", "baslik": "Komut", "hedef": "ls"}
    device_id, secret = rig.pair(["project.read", "agent.run", "project.write"])
    await rig.rpc(device_id, secret, "tasks.create", {"prompt": "yap"})
    await asyncio.sleep(0.05)
    wide = (
        await rig.rpc(
            device_id, secret, "approvals.respond", {"questionId": "q1", "choice": "session"}
        )
    ).json()
    assert wide["error"] == "gecersiz_istek"
    once = (
        await rig.rpc(
            device_id, secret, "approvals.respond", {"questionId": "q1", "choice": "once"}
        )
    ).json()
    assert once["ok"] is True
    rig.backend.release.set()


async def test_kit_yalniz_uzaktan_izinli_ve_kapsamli(rig: Rig) -> None:
    device_id, secret = rig.pair(["kits.list", "kits.run.acik", "kits.run.kapali"])
    listed = (await rig.rpc(device_id, secret, "kits.list")).json()["data"]["kits"]
    assert [kit["slug"] for kit in listed] == ["acik"]
    blocked = (await rig.rpc(device_id, secret, "kits.run", {"slug": "kapali"})).json()
    assert blocked["error"] in {"kit_izinsiz", "yetki_yok"}
    no_scope = rig.pair(["kits.list"])
    denied = (await rig.rpc(no_scope[0], no_scope[1], "kits.run", {"slug": "acik"})).json()
    assert denied["error"] == "yetki_yok"


async def test_duraklatma_desteklenmiyorsa_sahte_basari_yok(rig: Rig) -> None:
    device_id, secret = rig.pair(["agent.pause"])
    response = (await rig.rpc(device_id, secret, "tasks.pause", {"runId": "x"})).json()
    assert response["error"] == "desteklenmiyor"


async def test_baska_cihazi_uzaktan_iptal_edemez(rig: Rig) -> None:
    first_id, first_secret = rig.pair()
    other_id, _ = rig.pair()
    denied = (
        await rig.rpc(first_id, first_secret, "devices.revoke", {"deviceId": other_id})
    ).json()
    assert denied["error"] == "yetki_yok"
    assert rig.registry.active(other_id) is not None


async def test_pwa_dosyalari_guvenlik_basliklariyla_sunulur(rig: Rig) -> None:
    response = await rig.client.get("/")
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_bind_politikasi() -> None:
    validate_bind("127.0.0.1", BindPolicy())
    for bad in ("0.0.0.0", "8.8.8.8", "::"):
        with pytest.raises(BindRefusedError):
            validate_bind(bad, BindPolicy(allow_lan=True, tls_enabled=True))
    with pytest.raises(BindRefusedError):
        validate_bind("192.168.1.10", BindPolicy())
    with pytest.raises(BindRefusedError):
        validate_bind("192.168.1.10", BindPolicy(allow_lan=True))
    validate_bind("192.168.1.10", BindPolicy(allow_lan=True, tls_enabled=True))


def test_kapsam_dogrulama_ve_sir_gizleme() -> None:
    with pytest.raises(ValueError):
        parse_scopes(["yok.boyle"])
    assert redact_payload({"token": "abc", "n": "Bearer abcdefghijklmnopqrstu"}) == {
        "token": "[gizlendi]",
        "n": "[gizlendi]",
    }
    assert len(notification_summary("a " * 500)) <= 280


def test_kayit_dosyasi_yalniz_sahibine_acik(tmp_path: Path) -> None:
    clock = FakeClock()
    registry = DeviceRegistry(tmp_path / "d.json", clock)
    registry.add("T", "signed", frozenset({"project.read"}))
    assert (tmp_path / "d.json").stat().st_mode & 0o077 == 0
    assert len(DeviceRegistry(tmp_path / "d.json", clock).list_devices()) == 1

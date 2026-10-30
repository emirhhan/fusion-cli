"""Uzaktan görev servisi: eşleştirme, imza, yetki, step-up, idempotency, bind politikası."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from fusion_cli.memory.run_store import SqliteRunStore
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
                SqliteRunStore(
                    tmp_path / "runs.sqlite3",
                    clock=self.clock,
                    token_bytes=lambda n: bytes(next(counter) % 256 for _ in range(n)),
                )
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
    # R1-20: ek önizlemeleri URL.createObjectURL (blob:) ile gösterilir; img-src bunu içermeli.
    assert "img-src 'self' data: blob:" in response.headers["content-security-policy"]
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


def test_bind_tailscale_cgnat_adresi_ozel_tunelle_kabul_edilir() -> None:
    """R1-27. Ölçüldü (30 Ekim): 100.64.0.0/10 `is_private` değil; Tailscale reddediliyordu."""
    policy = BindPolicy(allow_lan=True, trusted_tunnel=True)
    validate_bind("100.101.102.103", policy)
    with pytest.raises(BindRefusedError):
        validate_bind("100.101.102.103", BindPolicy())  # izin ve şifreli kanal yine şart
    with pytest.raises(BindRefusedError):
        validate_bind("100.128.0.1", policy)  # blok dışı: internete açık


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


async def test_rpc_isleyici_beklenmeyen_istisna_500_json_doner(rig: Rig) -> None:
    device_id, secret = rig.pair()

    async def boom(*_args: Any) -> Any:
        raise TimeoutError("yürütücü yanıt vermedi")

    rig.service.call = boom  # type: ignore[method-assign]
    response = await rig.rpc(device_id, secret, "service.status")
    assert response.status_code == 500
    assert response.json() == {"error": "sunucu_hatasi"}


async def _wrong_pair(rig: Rig, *, forwarded: str | None) -> int:
    headers = {"x-forwarded-for": forwarded} if forwarded else {}
    response = await rig.client.post(
        "/v1/pair/submit", json={"code": "YANLIS12", "deviceName": "T"}, headers=headers
    )
    return response.status_code


async def test_tunel_arkasinda_kilit_istemci_ip_sine_gore_ayrilir(rig: Rig) -> None:
    """R1-11. Ölçüldü (30 Ekim): proxy arkasında `client` hep 127.0.0.1; bir saldırganın 5 hatası
    herkesin eşleştirmesini 15 dk kilitliyordu. Güvenilir (loopback) eşten gelen
    X-Forwarded-For'un SON girdisi istemci kimliği olur."""
    for _ in range(5):
        assert await _wrong_pair(rig, forwarded="203.0.113.9") == 400
    assert await _wrong_pair(rig, forwarded="203.0.113.9") == 429  # saldırgan kilitli
    assert await _wrong_pair(rig, forwarded="198.51.100.4") == 400  # başka istemci etkilenmez
    assert await _wrong_pair(rig, forwarded=None) == 400  # başlıksız yerel çağrı da değil
    # Zincirde sahte ilk girdi sayılmaz: proxy'nin eklediği son girdi esastır.
    assert await _wrong_pair(rig, forwarded="1.1.1.1, 203.0.113.9") == 429


async def test_yavas_govde_zaman_asimiyla_kesilir_ve_yasam_dongusu_yanitlanir(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1-36. Ölçüldü (30 Ekim): gövde okumada zaman aşımı yok, lifespan iletisi yanıtsızdı."""
    monkeypatch.setattr("fusion_cli.remote.asgi.BODY_READ_TIMEOUT_SECONDS", 0.05)
    sent: list[dict[str, Any]] = []

    async def never() -> dict[str, Any]:
        await asyncio.sleep(5)
        return {}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/v1/rpc", "client": ("127.0.0.1", 1)}
    await rig.app(scope, never, send)
    assert sent[0]["status"] == 408

    messages = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])
    lifespan_sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return next(messages)

    async def collect(message: dict[str, Any]) -> None:
        lifespan_sent.append(message)

    await rig.app({"type": "lifespan"}, receive, collect)
    assert [m["type"] for m in lifespan_sent] == [
        "lifespan.startup.complete",
        "lifespan.shutdown.complete",
    ]


async def test_cevaplanmayan_onay_zaman_asiminda_reddedilir(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1-16. Ölçüldü (30 Ekim): onay beklerken zaman aşımı yoktu; telefon susarsa tur
    (6 saate dek) `run_lock`'u tutup bütün kuyruğu bloke ediyordu."""
    monkeypatch.setattr("fusion_cli.remote.rpc.APPROVAL_TIMEOUT_SECONDS", 0.05)
    rig.backend.ask = {"tur": "onay", "arac": "run_shell", "baslik": "Komut", "hedef": "ls"}
    device_id, secret = rig.pair(["project.read", "agent.run"])
    created = (await rig.rpc(device_id, secret, "tasks.create", {"prompt": "yap"})).json()["data"]
    await asyncio.sleep(0.02)
    assert rig.service.pending_questions()
    await asyncio.sleep(0.2)
    assert rig.backend.answers == [("q1", {"secim": "deny"})]
    assert rig.service.pending_questions() == []
    events = (await rig.rpc(device_id, secret, "tasks.events", {"runId": created["runId"]})).json()[
        "data"
    ]["events"]
    answered = [e for e in events if e["kind"] == "approval_answered"]
    assert answered and answered[0]["payload"]["by"] == "timeout"
    rig.backend.release.set()


async def test_zamanasimindan_once_verilen_cevap_zamanlayiciyi_iptal_eder(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("fusion_cli.remote.rpc.APPROVAL_TIMEOUT_SECONDS", 0.1)
    rig.backend.ask = {"tur": "onay", "arac": "run_shell", "baslik": "Komut", "hedef": "ls"}
    device_id, secret = rig.pair(["project.read", "agent.run", "project.write"])
    await rig.rpc(device_id, secret, "tasks.create", {"prompt": "yap"})
    await asyncio.sleep(0.02)
    ok = await rig.rpc(
        device_id, secret, "approvals.respond", {"questionId": "q1", "choice": "once"}
    )
    assert ok.json()["ok"] is True
    await asyncio.sleep(0.25)
    assert rig.backend.answers == [("q1", {"secim": "once"})]  # zaman aşımı ikinci cevap yazmaz
    rig.backend.release.set()


async def test_yuksek_yetkili_kodla_eslestirme_onay_ayari_kapaliyken_de_elle_onaylanir(
    tmp_path: Path,
) -> None:
    """R1-13. Ölçüldü (30 Ekim): requireApproval=false iken kodu bilen, seçilen yüksek
    yetkili kapsamlarla (project.write, desktop.control...) kendiliğinden eşleşiyordu."""
    clock = FakeClock()
    pairing = PairingService(
        DeviceRegistry(tmp_path / "d.json", clock), clock, require_approval=lambda: False
    )
    code, _ = pairing.begin(["project.read", "agent.run", "desktop.control"])
    pairing.submit(code, "Telefon", channel="signed")
    assert not pairing.is_approved(code)  # masaüstü onayı şart
    pairing.approve(code)
    assert pairing.is_approved(code)
    plain, _ = pairing.begin(None)
    pairing.submit(plain, "Telefon", channel="signed")
    assert pairing.is_approved(plain)  # varsayılan kapsamlar eskisi gibi kendiliğinden


async def test_olaylar_sayfalanir_ve_bekleyen_onay_olay_atilsa_da_gorunur(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1-23. Ölçüldü (30 Ekim): afterSeq=0 ile tüm olaylar (5000'e dek) tek yanıttı; eski
    approval_request olayı atılırsa bekleyen onay telefonda görünmüyordu."""
    monkeypatch.setattr("fusion_cli.remote.rpc.EVENTS_PAGE_LIMIT", 3)
    rig.backend.ask = {"tur": "onay", "arac": "run_shell", "baslik": "Komut", "hedef": "ls"}
    device_id, secret = rig.pair(["project.read", "agent.run"])
    created = (await rig.rpc(device_id, secret, "tasks.create", {"prompt": "yap"})).json()["data"]
    await asyncio.sleep(0.02)
    for index in range(6):
        rig.service._store.append(created["runId"], "delta", {"text": str(index)})
    first = (
        await rig.rpc(device_id, secret, "tasks.events", {"runId": created["runId"]})
    ).json()["data"]
    assert len(first["events"]) == 3 and first["hasMore"] is True
    assert [q["questionId"] for q in first["pending"]] == ["q1"]
    after = first["events"][-1]["seq"]
    rest: list[dict[str, Any]] = []
    while True:
        page = (
            await rig.rpc(
                device_id, secret, "tasks.events", {"runId": created["runId"], "afterSeq": after}
            )
        ).json()["data"]
        rest += page["events"]
        if not page["hasMore"]:
            break
        after = page["events"][-1]["seq"]
    assert [e["seq"] for e in first["events"] + rest] == sorted(
        e["seq"] for e in first["events"] + rest
    )
    assert len(first["events"] + rest) >= 8
    rig.backend.release.set()

"""İki kullanıcılı dikey kesit: telefon görevleri hesaplar arasında sızmaz (WP02 + WP07).

Ölçüldü (28 Ekim): telefondan hesapla giriş, parola HERHANGİ bir yerel hesaba
aitse cihazı kaydediyordu ve cihaz hiçbir hesaba bağlı değildi. B hesabının
parolasıyla giren telefon, A hesabıyla açık masaüstünde görev çalıştırabiliyor,
A'nın görevlerini listeleyip iptal edebiliyordu. Görevler bellekte olduğu için
yeniden başlatmada da kayboluyordu.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fusion_cli.memory.run_store import SqliteRunStore
from fusion_cli.remote.account_login import AccountLogin
from fusion_cli.remote.devices import DeviceRegistry
from fusion_cli.remote.rate_limit import FailureLimiter
from fusion_cli.remote.rpc import RemoteService
from fusion_cli.remote.tasks import TaskStore

from .test_remote_service import FakeBackend, FakeClock

_HESAPLAR = {("ayse", "parola-a"): "hesap-a", ("burak", "parola-b"): "hesap-b"}


class Duzenek:
    """A hesabı masaüstünde açık; iki hesabın da telefonu var."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.clock = FakeClock()
        self.registry = DeviceRegistry(tmp_path / "devices.json", self.clock)
        self.backend = FakeBackend()
        self.runs = SqliteRunStore(tmp_path / "runs.sqlite3", clock=self.clock)
        self.service = RemoteService(
            clock=self.clock,
            registry=self.registry,
            store=TaskStore(self.runs),
            backend=self.backend,
            host_tenant="hesap-a",
        )
        self.login = AccountLogin(
            authenticate=lambda i, p: _HESAPLAR.get((i, p)),
            registry=self.registry,
            limiter=FailureLimiter(self.clock),
        )

    async def telefon(self, kullanici: str, parola: str):
        return await self.login.login("istemci", kullanici, parola, f"{kullanici} telefonu")


async def test_cihaz_giris_yapilan_hesaba_baglanir(tmp_path):
    rig = Duzenek(tmp_path)

    a = await rig.telefon("ayse", "parola-a")
    b = await rig.telefon("burak", "parola-b")

    assert (a.account_id, b.account_id) == ("hesap-a", "hesap-b")
    yeniden = DeviceRegistry(tmp_path / "devices.json", rig.clock)
    assert yeniden.get(b.device_id).account_id == "hesap-b"  # type: ignore[union-attr]


async def test_baska_hesabin_telefonu_gorev_baslatamaz_ve_gormez(tmp_path):
    rig = Duzenek(tmp_path)
    a = await rig.telefon("ayse", "parola-a")
    b = await rig.telefon("burak", "parola-b")
    olusan = await rig.service.call(
        a, "tasks.create", {"prompt": "A'nın işi", "idempotencyKey": "1"}
    )
    run_id = olusan.data["runId"]

    reddedilen = await rig.service.call(
        b, "tasks.create", {"prompt": "B'nin işi", "tenantId": "hesap-a", "workspaceId": "kisisel"}
    )
    liste = await rig.service.call(b, "tasks.list", {"tenantId": "hesap-a"})
    durum = await rig.service.call(b, "tasks.status", {"runId": run_id})
    olaylar = await rig.service.call(b, "tasks.events", {"runId": run_id})
    iptal = await rig.service.call(b, "tasks.cancel", {"runId": run_id})

    assert reddedilen.error == "baska_hesap"
    assert liste.ok and liste.data["tasks"] == []
    assert (durum.error, olaylar.error, iptal.error) == ("gorev_yok",) * 3
    await asyncio.sleep(0)
    assert rig.backend.started == ["A'nın işi"]
    sahip = await rig.service.call(a, "tasks.list", {})
    assert [t["runId"] for t in sahip.data["tasks"]] == [run_id]
    rig.backend.release.set()
    await asyncio.gather(*rig.service._runs)


async def test_baska_hesabin_telefonu_onay_sorusunu_cevaplayamaz(tmp_path):
    rig = Duzenek(tmp_path)
    a = await rig.telefon("ayse", "parola-a")
    b = await rig.telefon("burak", "parola-b")
    rig.backend.ask = {"tur": "metin", "baslik": "Hangi dal?"}
    await rig.service.call(a, "tasks.create", {"prompt": "iş", "idempotencyKey": "1"})
    await asyncio.sleep(0)

    cevap = await rig.service.call(b, "approvals.respond", {"questionId": "q1", "text": "main"})

    assert cevap.error == "baska_hesap"
    assert rig.backend.answers == []
    rig.backend.release.set()
    await asyncio.gather(*rig.service._runs)


async def test_yeniden_baslatmada_yarim_is_sahibine_uzlastirma_olarak_gorunur(tmp_path):
    rig = Duzenek(tmp_path)
    a = await rig.telefon("ayse", "parola-a")
    b = await rig.telefon("burak", "parola-b")
    olusan = await rig.service.call(a, "tasks.create", {"prompt": "uzun iş", "idempotencyKey": "1"})
    await asyncio.sleep(0)
    # Masaüstü çöküyor: kilit bırakılır, görev hâlâ "running" kayıtlı.
    rig.runs._owner._handle.close()  # type: ignore[union-attr]
    for task in rig.service._runs:
        task.cancel()

    yeni = RemoteService(
        clock=rig.clock,
        registry=DeviceRegistry(tmp_path / "devices.json", rig.clock),
        store=TaskStore(SqliteRunStore(tmp_path / "runs.sqlite3", clock=rig.clock)),
        backend=FakeBackend(),
        host_tenant="hesap-a",
    )
    sahip = await yeni.call(a, "tasks.status", {"runId": olusan.data["runId"]})
    yabanci = await yeni.call(b, "tasks.status", {"runId": olusan.data["runId"]})
    tekrar = await yeni.call(a, "tasks.create", {"prompt": "uzun iş", "idempotencyKey": "1"})

    assert sahip.data["state"] == "needs_reconciliation"
    assert yabanci.error == "gorev_yok"
    # Aynı anahtar yeni yürütme açmaz: kabul edilmiş iş tekrar çalıştırılmaz.
    assert tekrar.data["duplicate"] is True and tekrar.data["runId"] == olusan.data["runId"]


async def test_ayni_anahtar_farkli_icerik_catisma_doner(tmp_path):
    rig = Duzenek(tmp_path)
    a = await rig.telefon("ayse", "parola-a")
    await rig.service.call(a, "tasks.create", {"prompt": "raporu yaz", "idempotencyKey": "k"})

    catisma = await rig.service.call(
        a, "tasks.create", {"prompt": "her şeyi sil", "idempotencyKey": "k"}
    )

    assert catisma.error == "istek_cakismasi"
    await asyncio.sleep(0)
    assert rig.backend.started == ["raporu yaz"]
    rig.backend.release.set()
    await asyncio.gather(*rig.service._runs)


async def test_baska_hesabin_telefonu_masaustu_verisine_hicbir_yontemle_erisemez(tmp_path):
    """Görev dışındaki yöntemler de (sohbet, medya, ekran, proje) masaüstündeki hesaba aittir."""
    rig = Duzenek(tmp_path)
    b = await rig.telefon("burak", "parola-b")

    for method in ("screen.request", "screen.status", "kits.list", "kits.run", "chats.list"):
        sonuc = await rig.service.call(b, method, {})
        assert sonuc.error in {"baska_hesap", "yontem_yok"}, (method, sonuc)
    for method in ("service.status", "tasks.list", "devices.revoke"):
        assert (await rig.service.call(b, method, {})).ok, method


async def test_masaustunde_hesap_degisince_kapi_yeni_hesabi_izler(tmp_path):
    rig = Duzenek(tmp_path)
    acik = {"hesap": "hesap-a"}
    rig.service = RemoteService(
        clock=rig.clock,
        registry=rig.registry,
        store=TaskStore(rig.runs),
        backend=rig.backend,
        host_tenant=lambda: acik["hesap"],
    )
    a = await rig.telefon("ayse", "parola-a")
    b = await rig.telefon("burak", "parola-b")
    acik["hesap"] = "hesap-b"

    eski = await rig.service.call(a, "tasks.create", {"prompt": "A işi", "idempotencyKey": "1"})
    yeni = await rig.service.call(b, "tasks.create", {"prompt": "B işi", "idempotencyKey": "1"})

    assert eski.error == "baska_hesap"
    assert yeni.ok
    rig.backend.release.set()
    await asyncio.gather(*rig.service._runs)


async def test_yalniz_calistirma_yetkili_cihaz_kendi_gorevini_gorur_ve_iptal_eder(tmp_path):
    rig = Duzenek(tmp_path)
    cihaz = rig.registry.add(
        "Kit", "signed", frozenset({"agent.run", "agent.cancel"}), account_id="hesap-a"
    )

    olusan = await rig.service.call(cihaz, "tasks.create", {"prompt": "iş", "idempotencyKey": "1"})
    await asyncio.sleep(0)
    iptal = await rig.service.call(cihaz, "tasks.cancel", {"runId": olusan.data["runId"]})

    assert olusan.ok and rig.backend.started == ["iş"]
    assert iptal.ok
    await asyncio.gather(*rig.service._runs)

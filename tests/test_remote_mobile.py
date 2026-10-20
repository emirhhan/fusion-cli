"""Mobil uygulama RPC'leri: sohbet, proje, model, zamanlama, ek, görsel, akış ve yetki."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

import pytest

from fusion_cli.remote.backend import AppSessionBackend
from fusion_cli.remote.controller import RemoteController
from fusion_cli.remote.devices import Device, DeviceRegistry
from fusion_cli.remote.mobile import MobileApi
from fusion_cli.remote.projects import ProjectStore
from fusion_cli.remote.rpc import RemoteService
from fusion_cli.remote.tasks import TaskStore
from fusion_cli.remote.uploads import MediaReader, UploadStore
from tests.test_remote_controller import MemorySecrets
from tests.test_remote_service import FakeBackend, FakeClock

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 32).decode()


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.clock = FakeClock()
        self.root = tmp_path / "kok"
        self.root.mkdir()
        self.backend = FakeBackend()
        self.projects = ProjectStore(tmp_path / "projects.json")
        self.uploads = UploadStore(tmp_path / "uploads", self.clock)
        lock = asyncio.Lock()
        self.lock = lock
        mobile = MobileApi(
            backend=self.backend,
            projects=self.projects,
            uploads=self.uploads,
            media=MediaReader([tmp_path]),
            clock=self.clock,
            default_root=self.root,
            session_lock=lock,
        )
        registry = DeviceRegistry(tmp_path / "d.json", self.clock)
        self.service = RemoteService(
            clock=self.clock,
            registry=registry,
            store=TaskStore(self.clock),
            backend=self.backend,
            mobile=mobile,
            run_lock=lock,
        )
        everything = frozenset({"project.read", "agent.run", "agent.cancel"})
        self.phone: Device = registry.add("Tel", "signed", everything)
        self.readonly: Device = registry.add("Salt", "signed", frozenset({"project.read"}))
        self.tmp = tmp_path

    async def call(
        self, method: str, params: dict[str, Any] | None = None, *, who: Any = None
    ) -> Any:
        return await self.service.call(who or self.phone, method, params or {})


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


async def test_proje_olustur_adlandir_sil_ve_sohbet_atama(rig: Rig) -> None:
    created = (await rig.call("projects.create", {"name": "  Mağaza  "})).data["project"]
    assert created["name"] == "Mağaza" and "root" not in created
    assert (await rig.call("projects.create", {"name": "mağaza"})).error == "proje_hata"
    assert (await rig.call("projects.create", {"name": " "})).error == "proje_hata"
    await rig.call("chats.assign", {"chatId": "c1", "projectId": created["id"]})
    listed = (await rig.call("projects.list")).data
    assert (
        listed["chatProjects"] == {"c1": created["id"]}
        and listed["projects"][0]["hasFolder"] is False
    )
    renamed = await rig.call("projects.rename", {"projectId": created["id"], "name": "Ekipman"})
    assert renamed.data["project"]["name"] == "Ekipman"
    await rig.call("projects.delete", {"projectId": created["id"]})
    assert (await rig.call("projects.list")).data == {"projects": [], "chatProjects": {}}
    assert (
        await rig.call("chats.assign", {"chatId": "c1", "projectId": "yok"})
    ).error == "proje_hata"


async def test_proje_kaydi_kalici_ve_masaustu_esitlemesi(rig: Rig, tmp_path: Path) -> None:
    rig.projects.replace(
        [
            {"id": "p1", "name": "Site", "root": str(tmp_path / "site"), "createdAt": 1},
            {"bozuk": 1},
        ],
        {"c9": "p1", "c8": "yok"},
    )
    again = ProjectStore(tmp_path / "projects.json")
    assert [p["id"] for p in again.list_projects()] == ["p1"] and again.chats() == {"c9": "p1"}
    assert (tmp_path / "projects.json").stat().st_mode & 0o077 == 0


async def test_sohbet_listesi_proje_eslemesi_ve_gecmis(rig: Rig) -> None:
    rig.projects.replace([{"id": "p1", "name": "A", "createdAt": 1}], {"c2": "p1"})
    rig.backend.responses["sohbet.listele"] = {
        "ok": True,
        "sohbetler": [
            {"sohbet_id": "c1", "baslik": "Eski", "guncelleme": 10, "mesaj_sayisi": 2},
            {"sohbet_id": "c2", "baslik": "Yeni", "guncelleme": 20, "mesaj_sayisi": 4},
        ],
    }
    chats = (await rig.call("chats.list")).data["chats"]
    assert [c["id"] for c in chats] == ["c2", "c1"] and chats[0]["projectId"] == "p1"
    assert chats[1]["projectId"] is None
    rig.backend.responses["oturum.gecmis"] = {
        "ok": True,
        "mesajlar": [
            {"rol": "kullanici", "metin": "selam", "id": "m1"},
            {"rol": "asistan", "metin": "merhaba"},
        ],
    }
    history = (await rig.call("chats.history", {"chatId": "c2"})).data["messages"]
    assert [m["role"] for m in history] == ["user", "assistant"] and history[0]["text"] == "selam"
    assert ("oturum.baslat", {"kok": str(rig.root), "sohbet_id": "c2"}) in rig.backend.calls
    assert (await rig.call("chats.history", {"chatId": "../x"})).error == "gecersiz_istek"


async def test_gorev_calisirken_sohbet_listesi_mesgul_doner(rig: Rig) -> None:
    async with rig.lock:
        assert (await rig.call("chats.list")).error == "mesgul"
        assert (await rig.call("chats.history", {"chatId": "c1"})).error == "mesgul"


async def test_mesaj_sohbete_proje_model_ve_ekle_baglanir(rig: Rig) -> None:
    project = (await rig.call("projects.create", {"name": "P"})).data["project"]
    upload = (
        await rig.call("uploads.put", {"name": "a b.png", "kind": "image", "dataBase64": PNG})
    ).data
    result = await rig.call(
        "tasks.create",
        {
            "prompt": "yap",
            "chatId": "c_abc",
            "projectId": project["id"],
            "tier": "hizli",
            "attachments": [upload["uploadId"]],
        },
    )
    assert result.ok and result.data["chatId"] == "c_abc"
    options = rig.backend.options[result.data["runId"]]
    assert options["chat_id"] == "c_abc" and options["tier"] == "hizli"
    assert options["root"] == str(rig.root)
    assert (
        options["attachments"][0]["kind"] == "image"
        and Path(options["attachments"][0]["path"]).is_file()  # noqa: ASYNC240
    )
    assert rig.projects.chats() == {"c_abc": project["id"]}


async def test_keyfi_klasor_ve_bilinmeyen_ek_reddedilir(rig: Rig) -> None:
    assert (
        await rig.call("tasks.create", {"prompt": "x", "chatId": "c1", "root": "/etc"})
    ).error == "kok_izinsiz"
    assert (
        await rig.call("tasks.create", {"prompt": "x", "attachments": ["yok"]})
    ).error == "ek_yok"
    assert (
        await rig.call("tasks.create", {"prompt": "x", "chatId": "a b"})
    ).error == "gecersiz_istek"


async def test_ek_boyut_tur_ve_yol_guvenligi(rig: Rig) -> None:
    big = base64.b64encode(b"x" * (700 * 1024 + 1)).decode()
    assert (await rig.call("uploads.put", {"name": "a.txt", "dataBase64": big})).error == "ek_hata"
    assert (
        await rig.call("uploads.put", {"name": "a.exe", "kind": "image", "dataBase64": PNG})
    ).error == "ek_hata"
    assert (await rig.call("uploads.put", {"name": "a", "dataBase64": "###"})).error == "ek_hata"
    ok = (await rig.call("uploads.put", {"name": "../../etc/pass wd.txt", "dataBase64": PNG})).data
    stored = next((rig.tmp / "uploads").glob(f"{ok['uploadId']}-*"))
    assert stored.parent == rig.tmp / "uploads" and ".." not in stored.name


async def test_gorsel_yalniz_izinli_kokten_ve_gorsel_turunde(rig: Rig) -> None:
    image = rig.tmp / "kok" / "g.png"
    image.write_bytes(b"\x89PNG....")
    shown = (await rig.call("media.get", {"path": str(image)})).data
    assert shown["mediaType"] == "image/png" and base64.b64decode(shown["dataBase64"]).startswith(
        b"\x89PNG"
    )
    outside = Path("/etc/hosts")
    assert (await rig.call("media.get", {"path": str(outside)})).error == "gorsel_hata"
    secret = rig.tmp / ".ssh" / "k.png"
    secret.parent.mkdir()
    secret.write_bytes(b"x")
    assert (await rig.call("media.get", {"path": str(secret)})).error == "gorsel_hata"
    text = rig.tmp / "kok" / "n.txt"
    text.write_text("x")
    assert (await rig.call("media.get", {"path": str(text)})).error == "gorsel_hata"
    assert (await rig.call("media.get", {"path": "goreli.png"})).error == "gorsel_hata"


async def test_model_listesi_ve_secimi(rig: Rig) -> None:
    rig.backend.responses["kademe.listele"] = {
        "ok": True,
        "kademeler": [
            {"ad": "hizli", "etiket": "Hızlı", "model": "m1"},
            {"ad": "guclu", "model": "m2"},
        ],
        "etkin": "hizli",
        "duzenlenebilir": True,
    }
    data = (await rig.call("models.list")).data
    assert data["active"] == "hizli" and [t["name"] for t in data["tiers"]] == ["hizli", "guclu"]
    assert (await rig.call("models.select", {"name": "guclu"})).data["selected"] == "guclu"
    rig.backend.responses["kademe.sec"] = {"ok": False, "metin": "kilitli"}
    assert (await rig.call("models.select", {"name": "x"})).error == "model_hata"


async def test_zamanlananlar_listele_etkinlestir_ve_simdi_calistir(rig: Rig) -> None:
    rig.backend.responses["zamanlama.liste"] = {
        "ok": True,
        "gorevler": [
            {
                "id": "z1",
                "baslik": "Rapor",
                "gorev": "raporu çıkar",
                "kok": "/baska",
                "etkin": True,
                "sonraki": 5,
            }
        ],
    }
    listed = (await rig.call("schedules.list")).data["schedules"]
    assert listed[0]["title"] == "Rapor" and listed[0]["enabled"] is True
    assert (await rig.call("schedules.enable", {"id": "z1", "enabled": False})).data["updated"]
    assert ("zamanlama.etkin", {"id": "z1", "etkin": False}) in rig.backend.calls
    run = await rig.call("schedules.run", {"id": "z1"})
    assert run.ok and rig.backend.options[run.data["runId"]]["root"] == str(
        rig.root
    )  # bilinmeyen kök → varsayılan
    assert (await rig.call("schedules.run", {"id": "yok"})).error == "gorev_yok"


async def test_yetkisiz_cihaz_yazan_cagrilari_yapamaz(rig: Rig) -> None:
    for method in (
        "projects.create",
        "uploads.put",
        "models.select",
        "schedules.enable",
        "schedules.run",
        "tasks.create",
    ):
        result = await rig.call(method, {"name": "x", "prompt": "x", "id": "z"}, who=rig.readonly)
        assert result.error == "yetki_yok", method
    assert (await rig.call("projects.list", who=rig.readonly)).ok


async def test_akan_yanit_parcalari_birlesir_ve_ara_olaydan_once_bosalir(rig: Rig) -> None:
    service = rig.service
    run = (await rig.call("tasks.create", {"prompt": "x"})).data["runId"]
    sink = service._sink_for(run)
    token = {"olay": "TokenReceived", "text": "Mer", "provisional": False}
    sink("event", token)
    sink("event", {**token, "text": "haba"})
    sink("event", {**token, "text": "ÖN", "provisional": True})
    sink("event", {"olay": "ToolExecuted", "name": "run_shell", "outcome": "ok"})
    deltas = [e.payload["text"] for e in service._store.get(run).events if e.kind == "delta"]  # type: ignore[union-attr]
    assert deltas == ["Mer", "haba"]  # ilk parça hemen, sonrakiler birleşik
    rig.clock.value += 1
    sink("event", {**token, "text": "!"})
    assert [e.payload["text"] for e in service._store.get(run).events if e.kind == "delta"][
        -1
    ] == "!"  # type: ignore[union-attr]
    rig.backend.release.set()


class _Session:
    """`AppSessionBackend` için sahte oturum: gelen istekleri kaydeder, sonucu satırla döner."""

    def __init__(self, writer: Any) -> None:
        self.writer = writer
        self.requests: list[tuple[str, dict[str, Any]]] = []

    async def handle(self, request: Any) -> None:
        self.requests.append((request.name, request.data))
        self.writer(
            json.dumps({"tip": "sonuc", "id": request.id, "veri": {"ok": True, "metin": "bitti"}})
        )


async def test_arka_uc_sohbet_model_ve_ekleri_sirayla_oturuma_iletir(tmp_path: Path) -> None:
    holder: list[_Session] = []

    def factory(writer: Any) -> _Session:
        holder.append(_Session(writer))
        return holder[0]

    backend = AppSessionBackend(factory, tmp_path)
    backend.prepare_run(
        "r1",
        {
            "chat_id": "c1",
            "root": str(tmp_path),
            "tier": "guclu",
            "attachments": [{"path": "/a", "name": "a", "kind": "file"}],
        },
    )
    events: list[tuple[str, dict[str, Any]]] = []
    await backend.start("r1", "merhaba", lambda kind, payload: events.append((kind, payload)))
    names = [name for name, _ in holder[0].requests]
    assert names == ["oturum.baslat", "kademe.sec", "tur.calistir"]
    assert holder[0].requests[0][1] == {"sohbet_id": "c1", "kok": str(tmp_path)}
    assert holder[0].requests[2][1]["ekler"][0]["path"] == "/a"
    assert events[-1] == ("done", {"summary": "bitti"})


async def test_masaustu_proje_kaydini_telefona_esitler(tmp_path: Path) -> None:
    controller = RemoteController(
        home=tmp_path,
        root=tmp_path,
        secrets=MemorySecrets(),
        session_factory=lambda writer: object(),
        clock=FakeClock(),
    )
    phone = controller._registry.add("Tel", "signed", frozenset({"project.read", "agent.run"}))
    sent = {
        "projeler": [{"id": "p1", "name": "Site", "root": str(tmp_path), "createdAt": 1}],
        "sohbetler": {"c1": "p1"},
    }
    assert (await controller.dispatch("uzak.projeler_esitle", sent))["projeler"] == 1
    listed = (await controller._service.call(phone, "projects.list", {})).data
    assert listed["projects"][0]["name"] == "Site" and listed["projects"][0]["hasFolder"] is True
    assert listed["chatProjects"] == {"c1": "p1"}
    await controller.aclose()

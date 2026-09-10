"""Oturum ömrü: istekleri karşılar, turu çalıştırır, kapanışı düzenler.

Bir süreç BİR oturum yürütür. Uygulama ikinci bir sohbet istiyorsa ikinci bir
süreç başlatır; böylece paylaşılan durum, kilit ve sahiplik sorunları hiç
doğmaz ve bir oturumun çökmesi diğerini etkilemez.

`self._state` (bir `ReplState`) TEK doğru durum kaynağıdır: yapılandırma, onay
modu, motor ve sohbet geçmişi burada yaşar. Komut akışları (`/model`,
`/security`, `/plan`…) `state.config`/`state.approval`'i DEĞİŞTİRİR; bu yüzden
tur çalıştırma ve durum bildirimi HER ZAMAN `self._state` üzerinden okur —
ayrı bir kopya tutulursa (`self._config` gibi) komutlar "uygulandı" der ama
sonraki tur eski değerle koşar (bkz. `docs/superpowers/sdd/final-fix-report.md`
C1/C4).
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..cli.repl.commands import RENDERED_COMMANDS, build_registry
from ..cli.repl.state import Engine, ReplState
from ..cli.repl.transcript_store import (
    TranscriptStore,
    delete_conversation,
    list_conversations,
    load_transcript_messages,
)
from ..config.credentials import FernetSecretStore
from ..config.keys import secret_key
from ..config.loader import load_config
from ..config.models import Config, McpServerConfig
from ..config.paths import credentials_file
from ..core.events import Event
from ..core.health import HealthRegistry
from ..engines.agent.approval import ApprovalMode
from ..engines.agent.loop import CHAT_SYSTEM_PROMPT
from ..history.sanitize import sanitize_message
from ..memory.factory import build_memory
from ..tools.capabilities import CapabilityRegistry, load_agent_prompt, load_skill_text
from ..ui import messages
from .bridges import PendingQuestions, ProtocolPrompter, ProtocolSink, Writer
from .capabilities import catalog, detail
from .commands import (
    command_choices,
    list_commands,
    render_command_text,
    run_command,
)
from .connectors import (
    add_connector,
    connector_secret_values,
    list_connectors,
    remove_connector,
    status_payload,
)
from .control import (
    connect_web_session,
    delete_secret,
    disconnect_web_session,
    provider_catalog_rows,
    save_secret,
    snapshot,
    start_web_login,
    verify_web_session,
    web_login_state,
    web_provider_cards,
)
from .history import (
    PreparedResume,
    list_sessions,
    list_sources,
    prepare_resume,
    preview_session,
    search_sessions,
)
from .instructions import get_instructions, instruction_block, save_instructions
from .lessons import get_lesson, list_lessons
from .processes import ProcessManager
from .project_status import git_status, suggested_commands
from .protocol import Reply, Request, encode_event, encode_result
from .tiers import list_tiers, select_tier
from .usage import UsageMeter, usage_status
from .voice import download_piper_model as voice_download_model
from .voice import save_settings as voice_settings
from .voice import speak as voice_speak
from .voice import status as voice_status
from .voice import stop as voice_stop
from .voice import wait_for_speech as voice_wait
from .workspace import (
    WorkspaceJournal,
    list_changes,
    list_entries,
    preview_entry,
    read_entry,
    undo_entry,
    workspace_status,
    write_entry,
)


def _build_health(config: Config) -> HealthRegistry:
    """Oturum için sağlık kaydını yapılandırma eşiklerinden kur.

    `cli/repl/loop.py::_build_health` ile aynı mantık — terminal REPL'i
    kurduğu gibi appserver da kurar, aksi halde `/health` her zaman boş
    döner ve sağlayıcı circuit breaker'ı turlar arasında hiç yaşamaz.
    """
    runtime = config.runtime
    return HealthRegistry(
        failure_threshold=runtime.circuit_failure_threshold,
        cooldown_s=runtime.circuit_cooldown_s,
        alpha=runtime.reliability_alpha,
    )


#: Modele gönderilecek tek görselin üst sınırı. Büyük bir görsel isteği şişirir,
#: çoğu uçta reddedilir ve kullanıcıya sebebi belirsiz bir hata döner.
MAX_GORSEL_BAYT = 5 * 1024 * 1024

#: Uzantıdan MIME türü. Liste dar tutulur: tanımadığımız bir türü "image/*"
#: diye göndermek uçta çözülemeyen bir yük üretir.
_GORSEL_TURLERI = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _attachment_images(value: object) -> tuple[str, ...]:
    """Görsel ekleri modele iliştirilebilir veri URI'lerine çevir.

    Eskiden ek olarak YALNIZ dosya yolu metin bağlamına giriyordu; görebilen bir
    model bile resmi hiç görmüyordu. Okunamayan, çok büyük ya da tanınmayan
    türdeki dosyalar sessizce atlanır — yol bilgisi metin bağlamında zaten
    kalır ve model gerektiğinde dosyayı araçla okuyabilir.
    """
    if not isinstance(value, list):
        return ()
    import base64

    uriler: list[str] = []
    for raw in value[:8]:
        if not isinstance(raw, dict) or raw.get("kind") != "image":
            continue
        path = raw.get("path")
        if not isinstance(path, str):
            continue
        local_path = Path(path).expanduser()
        tur = _GORSEL_TURLERI.get(local_path.suffix.casefold())
        if tur is None:
            continue
        try:
            if local_path.stat().st_size > MAX_GORSEL_BAYT:
                continue
            ham = local_path.read_bytes()
        except OSError:
            continue
        uriler.append(f"data:{tur};base64,{base64.b64encode(ham).decode('ascii')}")
    return tuple(uriler)


def _attachment_context(value: object) -> tuple[str, str | None]:
    """Eklerin yalnız güvenli metadata'sını tur bağlamına dönüştürür.

    Dosya içeriği burada okunmaz; arayüz mutlak yolu verir ve agent standart
    dosya araçları/izinleri üzerinden gerektiğinde kendisi okur.
    """
    if not isinstance(value, list):
        return "", None
    attachments: list[dict[str, str]] = []
    unavailable: list[str] = []
    for raw in value[:20]:
        if not isinstance(raw, dict):
            continue
        path = raw.get("path")
        if not isinstance(path, str) or not path.strip() or len(path) > 4096:
            continue
        local_path = Path(path).expanduser()
        if not local_path.is_absolute() or not local_path.is_file():
            unavailable.append(str(raw.get("name") or path)[:512])
            continue
        attachments.append(
            {
                "path": str(local_path),
                "name": str(raw.get("name", ""))[:512],
                "kind": "image" if raw.get("kind") == "image" else "file",
            }
        )
    if unavailable:
        names = ", ".join(unavailable[:3])
        suffix = "…" if len(unavailable) > 3 else ""
        return "", f"Ek açılamadı veya artık mevcut değil: {names}{suffix}"
    if not attachments:
        return "", None
    payload = json.dumps(attachments, ensure_ascii=False)
    return (
        "<kullanici_ekleri>\n"
        "Bu yolları kullanıcı bu tur için açıkça ekledi. İçerikleri yalnız görev "
        "gerektiriyorsa standart izin ve araç kurallarıyla oku.\n"
        f"{payload}\n"
        "</kullanici_ekleri>",
        None,
    )


class _MeteredSink:
    """Olayları yazan sink'i sarar ve tüketimi sayar.

    Sarmalama, sayacın olay akışının TAM ÜSTÜNDE durmasını sağlar: yeni bir
    çağrı yolu eklendiğinde sayaç kendiliğinden görür.
    """

    def __init__(self, inner: ProtocolSink, meter: UsageMeter) -> None:
        self._inner = inner
        self._meter = meter

    def handle(self, event: Event) -> None:
        self._meter.observe(event)
        self._inner.handle(event)


#: Sekme kimliği bildirilmeden yazılan turların gideceği sohbet.
#
# Uygulamanın ön yüzü ilk sekmesini bu kimlikle açar; ikisi aynı olmazsa açılış
# turu ile sekmenin geçmişi ayrışır.
FALLBACK_CONVERSATION_ID = "varsayilan"


class AppSession:
    """Uygulamanın sürdüğü tek oturum."""

    def __init__(self, writer: Writer, *, root: Path, home: Path) -> None:
        self._writer = writer
        self._root = root
        self._home = home
        config = load_config()
        self._secret_store = FernetSecretStore(credentials_file(), secret_key=secret_key())
        self.pending = PendingQuestions()
        self._registry = build_registry(home)
        self._state = ReplState(
            config=config,
            memory=build_memory(config, root=root),
            root=root,
            home=home,
            health=_build_health(config),
        )
        #: Uygulamanın sekmesine karşılık gelen konuşma kimliği. `oturum.baslat`
        #: ile gelir; gelmeden önce okuma proje genelini gösterir.
        self._conversation_id: str | None = None
        self._state.history = load_transcript_messages(config.memory_dir, root)
        # YAZMA kimliği asla rastgele olmaz. Ölçüldü (kullanıcının diski, 7 Eylül):
        # kimliksiz açılan depo her seferinde `session-<zaman>-<rastgele>` üretti ve
        # o konuşmalara bir daha ulaşılamadı — 110 sohbetin çoğu böyle orphan kaldı.
        # Sekme kimliği gelene kadar yazılanlar, ulaşılabilir tek bir sohbette durur.
        self._transcript_store = TranscriptStore(
            config.memory_dir, root, conversation_id=FALLBACK_CONVERSATION_ID
        )
        #: "sohbet" ya da "kod". Varsayılan SOHBET: kullanıcı boş bir pencerede
        #: "merhaba" yazdığında Fusion proje taramasıyla başlamamalı.
        self._workspace_mode = "sohbet"
        self._workspace_journal = WorkspaceJournal()
        self._processes = ProcessManager(self._state.root, writer)
        self._gateway_process_id: str | None = None
        executable = shlex.quote(sys.executable)
        self._gateway_command = (
            f"{executable} serve --host 127.0.0.1 --port 8787"
            if getattr(sys, "frozen", False)
            else f"{executable} -m fusion_cli serve --host 127.0.0.1 --port 8787"
        )
        self._all_capabilities = CapabilityRegistry(home, root)
        self._disabled_skills: set[str] = set()
        self._disabled_agents: set[str] = set()
        self._disabled_mcp: set[str] = set()
        self._pending_capability: tuple[str, str] | None = None
        self._refresh_capabilities()
        self._usage = UsageMeter()
        from ..mcp_bridge.service import McpConnectionService

        self._mcp_connections = McpConnectionService()
        self._turn: asyncio.Task[Any] | None = None

    async def handle(self, request: Request) -> None:
        """İsteği çalıştır ve sonucunu yaz. İstisna sızdırmaz."""
        try:
            data = await self._dispatch(request)
        except Exception as error:  # istek sınırı: süreç çökmemeli
            data = {"ok": False, "metin": str(error)}
        self._writer(encode_result(request.id, data))

    async def _dispatch(self, request: Request) -> dict[str, Any]:
        if request.name == "oturum.baslat":
            return self._start_session(request.data)
        if request.name == "oturum.durum":
            return self._status()
        if request.name == "oturum.gecmis":
            return {
                "ok": True,
                "mesajlar": [
                    {
                        "rol": "kullanici" if message.role == "user" else "asistan",
                        "metin": sanitize_message(message).content,
                    }
                    for message in self._state.history
                    if message.role in {"user", "assistant"}
                ],
            }
        if request.name == "sohbet.sil":
            return await self._delete_conversation(request.data)
        if request.name == "sohbet.listele":
            return self._list_conversations()
        if request.name == "kademe.listele":
            return list_tiers(self._state.config)
        if request.name == "kademe.sec":
            self._state.config, sonuc = select_tier(self._state.config, request.data)
            return sonuc
        if request.name == "gecmis.kaynaklar":
            return list_sources(self._home)
        if request.name == "gecmis.oturumlar":
            return list_sessions(self._home, self._state.root, request.data)
        if request.name == "gecmis.ara":
            return await asyncio.to_thread(
                search_sessions, self._home, self._state.root, request.data
            )
        if request.name == "gecmis.onizle":
            return preview_session(self._home, request.data)
        if request.name == "gecmis.surdur":
            prepared = prepare_resume(self._home, self._state.root, request.data)
            if isinstance(prepared, PreparedResume):
                self._state.pending_digest = prepared.digest
                self._state.history = list(prepared.messages)
                return prepared.payload
            return prepared
        if request.name == "proje.durum":
            return workspace_status(self._state.root)
        if request.name == "proje.listele":
            return list_entries(self._state.root, request.data)
        if request.name == "proje.oku":
            return read_entry(self._state.root, request.data)
        if request.name == "proje.onizle":
            return preview_entry(self._state.root, request.data)
        if request.name == "web.onizleme_dogrula":
            from .web_preview import validate_web_preview

            return await asyncio.to_thread(validate_web_preview, request.data)
        if request.name == "proje.yaz":
            return write_entry(self._state.root, request.data, self._workspace_journal)
        if request.name == "proje.degisiklikler":
            return list_changes(self._state.root, self._workspace_journal)
        if request.name == "proje.geri_al":
            return undo_entry(self._state.root, request.data, self._workspace_journal)
        if request.name == "surec.baslat":
            return await self._processes.start(request.data)
        if request.name == "surec.yaz":
            return await self._processes.write(request.data)
        if request.name == "surec.listele":
            return self._processes.list()
        if request.name == "surec.kes":
            return await self._processes.stop(request.data)
        if request.name == "proje.komut_onerileri":
            return suggested_commands(self._state.root)
        if request.name == "proje.git_durum":
            return git_status(self._state.root)
        if request.name == "yetenek.katalog":
            return catalog(
                self._all_capabilities,
                self._state.config,
                self._state.root,
                disabled_skills=self._disabled_skills,
                disabled_agents=self._disabled_agents,
                disabled_mcp=self._disabled_mcp,
            )
        if request.name == "yetenek.detay":
            return detail(
                self._all_capabilities, self._state.config, self._state.root, request.data
            )
        if request.name == "yetenek.etkinlik":
            return self._set_capability_enabled(request.data)
        if request.name == "yetenek.kullan":
            return self._select_capability(request.data)
        if request.name == "kontrol.durum":
            return self._control_status()
        if request.name == "kontrol.anahtar_kaydet":
            return save_secret(
                self._secret_store,
                str(request.data.get("saglayici", "")),
                request.data.get("deger"),
            )
        if request.name == "kontrol.anahtar_sil":
            return delete_secret(self._secret_store, str(request.data.get("saglayici", "")))
        if request.name == "kontrol.anahtar_dogrula":
            from ..config.keys import environ_snapshot
            from ..providers.api_validation import validate_api_key
            from ..providers.registry import BUILTIN_PROVIDERS

            provider_id = str(request.data.get("saglayici", ""))
            definition = next((item for item in BUILTIN_PROVIDERS if item.id == provider_id), None)
            key = environ_snapshot().get(definition.auth_env or "", "") if definition else ""
            validation = await validate_api_key(provider_id, key)
            return {"ok": validation.ok, "metin": validation.message}
        if request.name == "kontrol.gateway_baslat":
            return await self._start_gateway()
        if request.name == "kontrol.gateway_durdur":
            return await self._stop_gateway()
        if request.name == "ses.durum":
            return voice_status()
        if request.name == "ses.konus":
            result = voice_speak(request.data.get("metin"))
            if request.data.get("bekle") is True and result.get("ok") is True:
                completed = await asyncio.to_thread(
                    voice_wait, result.get("tur_id", result.get("pid"))
                )
                return {**result, "tamamlandi": completed}
            return result
        if request.name == "ses.bekle":
            turn_id = request.data.get("tur_id")
            completed = await asyncio.to_thread(voice_wait, turn_id)
            return {"ok": True, "tamamlandi": completed, "tur_id": turn_id}
        if request.name == "ses.model_indir":
            return voice_download_model(
                lambda olay: self._writer(encode_event({"olay": "SesModeliIlerleme", **olay}))
            )
        if request.name == "kullanim.durum":
            return usage_status(self._usage, self._state.health)
        if request.name == "ayar.talimat":
            return get_instructions()
        if request.name == "ayar.talimat_kaydet":
            return save_instructions(request.data.get("metin"))
        if request.name == "baglanti.listele":
            return list_connectors(self._state.config, self._mcp_connections.statuses)
        if request.name == "baglanti.ekle":
            return await self._add_connector(request.data)
        if request.name == "baglanti.dogrula":
            server = self._connector(request.data.get("ad"))
            if server is None:
                return {"ok": False, "metin": "Bağlantı bulunamadı."}
            return status_payload(await self._mcp_connections.test(server))
        if request.name == "baglanti.giris":
            server = self._connector(request.data.get("ad"))
            if server is None:
                return {"ok": False, "metin": "Bağlantı bulunamadı."}
            return status_payload(self._mcp_connections.start_login(server))
        if request.name == "baglanti.giris_durumu":
            return status_payload(
                self._mcp_connections.login_status(str(request.data.get("ad", "")))
            )
        if request.name == "baglanti.cikis":
            server = self._connector(request.data.get("ad"))
            if server is None:
                return {"ok": False, "metin": "Bağlantı bulunamadı."}
            return status_payload(await self._mcp_connections.logout(server))
        if request.name == "baglanti.sil":
            server = self._connector(request.data.get("ad"))
            if server is not None:
                await self._mcp_connections.logout(server)
            return self._change_connectors(remove_connector, request.data)
        if request.name == "ses.ayar":
            return voice_settings(request.data)
        if request.name == "ses.durdur":
            return voice_stop(request.data.get("tur_id"))
        if request.name == "saglayici.katalog":
            return provider_catalog_rows(self._state.config, self._secret_store)
        if request.name == "web.saglayicilar":
            return web_provider_cards(self._state.config)
        if request.name == "web.giris":
            from ..providers.web_browser import close_all_browser_sessions

            await close_all_browser_sessions()
            return start_web_login(request.data.get("saglayici"), request.data.get("hesap"))
        if request.name == "web.baglan":
            return self._change_web_session(
                connect_web_session, request.data.get("saglayici"), request.data.get("hesap")
            )
        if request.name == "web.cikis":
            return self._change_web_session(
                disconnect_web_session, request.data.get("saglayici"), request.data.get("hesap")
            )
        if request.name == "web.dogrula":
            sonuc = await verify_web_session(
                self._state.config, request.data.get("saglayici"), request.data.get("hesap")
            )
            from ..providers.web_control import set_login_verified

            yeni = set_login_verified(
                self._state.config,
                str(request.data.get("saglayici") or ""),
                str(request.data.get("hesap") or "main"),
                sonuc.get("ok") is True,
            )
            if yeni is not None:
                self._state.config = yeni
            return sonuc
        if request.name == "web.giris_durumu":
            return web_login_state(request.data.get("pid"))
        if request.name == "ders.listele":
            return list_lessons()
        if request.name == "ders.getir":
            return get_lesson(str(request.data.get("id", "")))
        if request.name == "komut.listele":
            return {"ok": True, "komutlar": list_commands(self._registry)}
        if request.name == "komut.calistir":
            return await self._run_command(request.data)
        if request.name == "komut.secenekler":
            return self._command_options(request.data)
        if request.name == "tur.calistir":
            attachment_context, attachment_error = _attachment_context(request.data.get("ekler"))
            if attachment_error:
                return {"ok": False, "metin": attachment_error}
            return await self._run_turn(
                str(request.data.get("gorev", "")),
                attachment_context,
                _attachment_images(request.data.get("ekler")),
            )
        if request.name == "tur.kes":
            return self._cancel_turn()
        return {"ok": False, "metin": messages.APP_UNKNOWN_REQUEST.format(name=request.name)}

    async def _delete_conversation(self, data: dict[str, Any]) -> dict[str, Any]:
        conversation_id = data.get("sohbet_id")
        root_value = data.get("kok")
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            return {"ok": False, "metin": "Sohbet kimliği zorunludur."}
        if root_value is not None and (not isinstance(root_value, str) or not root_value.strip()):
            return {"ok": False, "metin": "Proje kökü geçerli bir dizin olmalıdır."}
        root = await asyncio.to_thread(Path(root_value).expanduser) if root_value else self._root
        root = await asyncio.to_thread(root.resolve)
        current_root = await asyncio.to_thread(self._root.resolve)
        await asyncio.to_thread(
            delete_conversation, self._state.config.memory_dir, root, conversation_id
        )
        if root == current_root and conversation_id == self._transcript_store.session_id:
            self._cancel_turn()
            self._state.history = []
        return {"ok": True, "sohbet_id": conversation_id}

    def _list_conversations(self) -> dict[str, Any]:
        """Bu proje kökünde diskte duran sohbetleri listele.

        Arayüz yalnız AÇIK sekmeleri gösteriyordu; kapatılan ya da uygulama
        yeniden başlayınca geri açılmayan konuşmalara ulaşmanın yolu yoktu.
        """
        return {
            "ok": True,
            "sohbetler": [
                {
                    "sohbet_id": ref.conversation_id,
                    "kok": str(self._root.expanduser().resolve()),
                    "baslik": ref.title,
                    "guncelleme": ref.updated_at,
                    "mesaj_sayisi": ref.message_count,
                }
                for ref in list_conversations(self._state.config.memory_dir, self._root)
            ],
        }

    def _rebind_transcript(self) -> None:
        """Transcript deposunu güncel kök ve konuşma kimliğine bağla.

        Okuma ve yazma TEK yerden bağlanır; ayrı ayrı bağlanırsa biri kimliği
        alıp öteki almadığında sekme yazdığını geri okuyamaz.
        """
        self._state.history = load_transcript_messages(
            self._state.config.memory_dir, self._root, conversation_id=self._conversation_id
        )
        self._transcript_store = TranscriptStore(
            self._state.config.memory_dir, self._root, conversation_id=self._conversation_id
        )

    def _start_session(self, data: dict[str, Any]) -> dict[str, Any]:
        """`oturum.baslat`: kök dizin, ev dizini, onay modu ve motoru kurar.

        Tüm alanlar opsiyoneldir; verilmeyen alan mevcut değerinde kalır. Süreç
        `fusion app` çağrısında zaten kök/ev dizinini alır (bkz. `cli/app.py`);
        bu istek uygulamanın onay modunu ve motoru PROTOKOL üzerinden açıkça
        seçebilmesi içindir — önceden yalnız AUTO'ya çivili başlıyordu.
        """
        root_value = data.get("kok")
        capability_roots_changed = False
        # Sohbet kimliği kökten ÖNCE okunur: kök de değişiyorsa transcript yeniden
        # bağlanırken doğru kimliğe bağlanmalı, yoksa sekme bir tur boyunca proje
        # genelini gösterir.
        sohbet_value = data.get("sohbet_id")
        conversation_changed = False
        if isinstance(sohbet_value, str) and sohbet_value.strip():
            yeni_kimlik = sohbet_value.strip()
            conversation_changed = yeni_kimlik != self._conversation_id
            self._conversation_id = yeni_kimlik
        if isinstance(root_value, str) and root_value:
            self._root = Path(root_value)
            self._state.root = self._root
            self._workspace_journal.clear()
            self._processes.update_root(self._root)
            capability_roots_changed = True
        if capability_roots_changed or conversation_changed:
            self._rebind_transcript()
        home_value = data.get("ev")
        if isinstance(home_value, str) and home_value:
            self._home = Path(home_value)
            self._state.home = self._home
            capability_roots_changed = True
        if capability_roots_changed:
            self._all_capabilities = CapabilityRegistry(self._home, self._root)
            self._disabled_skills.clear()
            self._disabled_agents.clear()
            self._disabled_mcp.clear()
            self._refresh_capabilities()
        mode_error = self._apply_mode(data.get("mod"))
        if mode_error is not None:
            return mode_error
        calisma_error = self._apply_workspace_mode(data.get("kip"))
        if calisma_error is not None:
            return calisma_error
        engine_error = self._apply_engine(data.get("motor"))
        if engine_error is not None:
            return engine_error
        return self._status()

    def _apply_mode(self, value: str | None) -> dict[str, Any] | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            self._state.approval = ApprovalMode(value)
        except ValueError:
            valid = ", ".join(mode.value for mode in ApprovalMode)
            return {
                "ok": False,
                "metin": messages.RUN_UNKNOWN_MODE.format(given=value, valid=valid),
            }
        return None

    def _change_web_session(
        self,
        action: Callable[[Config, object, object], tuple[Config | None, dict[str, Any]]],
        saglayici: object,
        hesap: object,
    ) -> dict[str, Any]:
        """Web oturumunu yaz/sil ve BAŞARILIYSA oturumun yapılandırmasını güncelle."""
        yeni, sonuc = action(self._state.config, saglayici, hesap)
        if yeni is not None:
            self._state.config = yeni
        return sonuc

    def _change_connectors(
        self,
        action: Callable[[Config, object], tuple[Config | None, dict[str, Any]]],
        data: object,
    ) -> dict[str, Any]:
        """Bağlantı ekle/sil ve BAŞARILIYSA oturumun yapılandırmasını güncelle.

        Yazma başarısızsa bellekteki yapılandırma da değişmez; aksi hâlde
        kaydedilmemiş bir bağlantı bu oturumda çalışır, sonraki açılışta yok
        olurdu.
        """
        yeni, sonuc = action(self._state.config, data)
        if yeni is not None:
            self._state.config = yeni
        return sonuc

    def _connector(self, name: object) -> McpServerConfig | None:
        wanted = str(name or "")
        return next((item for item in self._state.config.mcp_servers if item.name == wanted), None)

    async def _add_connector(self, data: object) -> dict[str, Any]:
        secrets, secret_error = connector_secret_values(data)
        if secret_error is not None:
            return {"ok": False, "metin": secret_error}
        if secrets and not self._secret_store.available:
            return {
                "ok": False,
                "metin": "Sistem anahtarlığı kullanılamıyor; MCP sırrı kaydedilemedi.",
            }
        previous: dict[str, str | None] = {}
        try:
            for name, value in secrets.items():
                previous[name] = self._secret_store.get(name)
                self._secret_store.set(name, value)
        except Exception as error:
            self._restore_connector_secrets(previous)
            return {"ok": False, "metin": f"MCP sırrı kaydedilemedi: {error}"}
        yeni, sonuc = add_connector(self._state.config, data)
        if yeni is None:
            self._restore_connector_secrets(previous)
            return sonuc
        os.environ.update(secrets)
        self._state.config = yeni
        server = yeni.mcp_servers[-1]
        if server.transport.value == "streamable_http":
            status = self._mcp_connections.start_login(server)
        else:
            status = await self._mcp_connections.test(server)
        return {**sonuc, **status_payload(status), "ok": True}

    def _restore_connector_secrets(self, previous: dict[str, str | None]) -> None:
        """Başarısız bağlantı eklemesinde sır deposunu önceki hâline getir."""
        for name, value in previous.items():
            if value is None:
                self._secret_store.delete(name)
            else:
                self._secret_store.set(name, value)

    def _apply_workspace_mode(self, value: object) -> dict[str, Any] | None:
        """`kip`: "sohbet" ya da "kod".

        Sohbet kipi kendiliğinden çalışma dizinini taramaz; kod kipi eski
        davranışı sürdürür. Onay sözleşmesi İKİSİNDE DE aynıdır.
        """
        if value is None:
            return None
        text = str(value).strip().casefold()
        if text not in ("sohbet", "kod"):
            return {"ok": False, "metin": "Geçersiz kip. Seçenekler: sohbet, kod."}
        self._workspace_mode = text
        return None

    def _apply_engine(self, value: str | None) -> dict[str, Any] | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            self._state.engine = Engine(value)
        except ValueError:
            valid = ", ".join(engine.value for engine in Engine)
            return {
                "ok": False,
                "metin": messages.RUN_UNKNOWN_ENGINE.format(given=value, valid=valid),
            }
        return None

    def _status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "kok": str(self._state.root),
            "model": self._state.config.agent.model,
            "kip": self._workspace_mode,
            "mod": self._state.approval.value,
            "motor": self._state.engine.value,
        }

    def _gateway_status(self) -> dict[str, Any]:
        if self._gateway_process_id is None:
            return {"durum": "kapali", "adres": "http://127.0.0.1:8787/v1"}
        records = self._processes.list().get("surecler", [])
        record = next(
            (item for item in records if item.get("surec_id") == self._gateway_process_id), None
        )
        if record is None or record.get("durum") != "calisiyor":
            self._gateway_process_id = None
            return {"durum": "kapali", "adres": "http://127.0.0.1:8787/v1"}
        return {
            "durum": "calisiyor",
            "adres": "http://127.0.0.1:8787/v1",
            "pid": record.get("pid"),
        }

    def _control_status(self) -> dict[str, Any]:
        return snapshot(
            self._state.config,
            self._secret_store,
            root=str(self._state.root),
            approval=self._state.approval.value,
            engine=self._state.engine.value,
            gateway=self._gateway_status(),
        )

    async def _start_gateway(self) -> dict[str, Any]:
        if self._gateway_status()["durum"] == "calisiyor":
            return {"ok": False, "metin": "Gateway zaten çalışıyor."}
        result = await self._processes.start({"komut": self._gateway_command, "cwd": ""})
        if result.get("ok") is True:
            self._gateway_process_id = str(result["surec_id"])
            return {
                "ok": True,
                "durum": "calisiyor",
                "adres": "http://127.0.0.1:8787/v1",
                "pid": result.get("pid"),
            }
        return result

    async def _stop_gateway(self) -> dict[str, Any]:
        if self._gateway_process_id is None:
            return {"ok": False, "metin": "Gateway çalışmıyor."}
        process_id, self._gateway_process_id = self._gateway_process_id, None
        result = await self._processes.stop({"surec_id": process_id})
        if result.get("ok") is True:
            return {"ok": True, "durum": result.get("durum", "durduruldu")}
        return result

    async def _run_command(self, data: dict[str, Any]) -> dict[str, Any]:
        """`run_command` sonucu tel-hazır — olduğu gibi geri gönder.

        Tek istisna kendi çıktısını BASAN komutlardır: işleyicileri boş dize
        döndürdüğü için masaüstünde "çalıştırıldı" deyip hiçbir şey
        göstermiyorlardı. Onlar TUI'nin kullandığı renderer'dan metne çevrilir.
        """
        name = str(data.get("ad", ""))
        argument = str(data.get("arguman", ""))
        command = self._registry.get(name)
        if command is not None and command.name == "clear":
            # `/clear` masaüstünde EKRAN temizler. TUI'de karşılama afişini
            # yeniden basmak doğrudur çünkü terminal geçmişi yerinde kalır;
            # uygulamada aynı şeyi yapmak sohbetin içine ASCII afiş düşürüyordu.
            self._state.history.clear()
            return {"ok": True, "metin": "", "temizle": True}
        if command is not None and command.name in RENDERED_COMMANDS:
            return {
                "ok": True,
                "metin": await render_command_text(self._registry, self._state, command.name),
            }
        return run_command(
            self._registry, self._state, name, argument, secret_store=self._secret_store
        )

    def _command_options(self, data: dict[str, Any]) -> dict[str, Any]:
        """Sıradaki seçici/metin adımını döndür; yoksa `ok: False`."""
        name = str(data.get("ad", ""))
        argument = str(data.get("arguman", ""))
        payload = command_choices(self._state, name, argument)
        if payload is None:
            return {"ok": False, "metin": messages.APP_COMMAND_UNKNOWN}
        return {"ok": True, "secici": payload}

    async def _run_turn(
        self,
        task: str,
        attachment_context: str = "",
        images: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        """Görevi agent motoruyla çalıştır; olaylar tel üzerinden akar.

        Yapılandırma ve onay modu `self._state`'TEN okunur (bkz. modül
        docstring'i): `/model` ya da `/security` gibi komutlar `self._state`i
        güncelledikten HEMEN SONRAKİ turda etkili olmalı, bir tur gecikmeli
        değil.
        """
        if not task.strip():
            return {"ok": False, "metin": messages.RUN_EMPTY_TASK}
        if self._turn is not None and not self._turn.done():
            return {"ok": False, "metin": messages.APP_TURN_ALREADY_RUNNING}
        from ..cli.session import run_agent_task

        self._transcript_store.record_user(task)

        # Kullanım sayacı olayları ARADAN dinler: sayaç için ayrı bir yol
        # açmak, bazı çağrı yollarının muhasebeden düşmesine yol açardı.
        sink = _MeteredSink(ProtocolSink(self._writer), self._usage)
        prompter = ProtocolPrompter(self._writer, self.pending)
        config = self._state.config
        if self._disabled_mcp:
            config = replace(
                config,
                mcp_servers=tuple(
                    server for server in config.mcp_servers if server.name not in self._disabled_mcp
                ),
            )
        capability_context = self._take_capability_context()
        inherited_context = self._state.take_pending_digest()
        # Kullanıcının kalıcı talimatı da bağlama girer. Sistem istemi
        # DEĞİŞTİRİLMEZ: kimlik ve onay sözleşmesi orada durur.
        extra_system = "\n\n".join(
            part
            for part in (
                inherited_context,
                capability_context,
                attachment_context,
                instruction_block(),
            )
            if part
        )
        self._turn = asyncio.ensure_future(
            run_agent_task(
                task,
                config,
                sinks=(sink,),
                prompter_factory=lambda _drain: prompter,
                mode=self._state.approval,
                root=self._state.root,
                home=self._state.home,
                history=self._state.history,
                extra_system=extra_system,
                # Görsel ekler modele GERÇEKTEN gider; yol metni ayrıca kalır.
                images=images,
                system_prompt=(None if self._workspace_mode == "kod" else CHAT_SYSTEM_PROMPT),
                interactive=True,
                capabilities=self._state.capabilities,
                conversation_id=self._conversation_id or "app",
            )
        )
        try:
            outcome = await self._turn
        except asyncio.CancelledError:
            # İptal de bir sonuçtur: kaydedilmezse sekme yeniden açıldığında
            # soru cevapsız durur ve kullanıcı turun neden bittiğini göremez.
            self._transcript_store.record_assistant(messages.APP_TURN_CANCELLED)
            return {"ok": False, "metin": messages.APP_TURN_CANCELLED}
        finally:
            self._turn = None
        # Çok-turlu sohbet: bu turun ürettiği geçmiş bir SONRAKİ `tur.calistir`e
        # taşınsın diye durumda saklanır (bkz. `tui_loop.py:417` ile aynı desen).
        self._state.history = outcome.messages
        # Transcript bir BAŞARI kaydı değil, NE OLDUĞU kaydıdır.
        #
        # Ölçüldü (7 Eylül, kullanıcının Godot koşuları): plan adımı duraklayınca
        # tur `ok=False` döndü; soru diske yazıldı, cevap yazılmadı. Diskteki
        # `198b3a19…` sohbeti 8 soru ve 0 cevap taşıyor. Sekme yeniden açıldığında
        # model kendi ne dediğini göremiyor ve kaldığı yerden süremiyor — oysa
        # duraklama metni tam da devam etmek için gereken bilgidir.
        if outcome.final_text.strip():
            self._transcript_store.record_assistant(outcome.final_text)
        # Boş metinle "başarısız" dönmek kullanıcıya hiçbir şey söylemez.
        metin = outcome.final_text
        if not metin.strip() and not outcome.ok:
            metin = messages.APP_TURN_NO_ANSWER
        return {"ok": outcome.ok, "metin": metin}

    def _refresh_capabilities(self) -> None:
        self._state.capabilities = CapabilityRegistry(
            self._state.home,
            self._state.root,
            disabled_skills=frozenset(self._disabled_skills),
            disabled_agents=frozenset(self._disabled_agents),
        )

    def _known_capability(self, kind: str, name: str) -> bool:
        if kind == "beceri":
            return self._all_capabilities.get_skill(name) is not None
        if kind == "ajan":
            return self._all_capabilities.get_agent(name) is not None
        if kind == "mcp":
            return any(server.name == name for server in self._state.config.mcp_servers)
        return False

    def _set_capability_enabled(self, data: dict[str, Any]) -> dict[str, Any]:
        kind, name, enabled = str(data.get("tur", "")), str(data.get("ad", "")), data.get("etkin")
        if not isinstance(enabled, bool) or not self._known_capability(kind, name):
            return {"ok": False, "metin": "Katalog öğesi bulunamadı."}
        target = {
            "beceri": self._disabled_skills,
            "ajan": self._disabled_agents,
            "mcp": self._disabled_mcp,
        }[kind]
        target.discard(name) if enabled else target.add(name)
        self._refresh_capabilities()
        return {"ok": True, "tur": kind, "ad": name, "etkin": enabled}

    def _select_capability(self, data: dict[str, Any]) -> dict[str, Any]:
        kind, name = str(data.get("tur", "")), str(data.get("ad", ""))
        if not self._known_capability(kind, name):
            return {"ok": False, "metin": "Katalog öğesi bulunamadı."}
        self._pending_capability = (kind, name)
        return {"ok": True, "tur": kind, "ad": name, "sonraki_tur": True}

    def _take_capability_context(self) -> str:
        selected, self._pending_capability = self._pending_capability, None
        if selected is None:
            return ""
        kind, name = selected
        if kind == "beceri":
            item = self._all_capabilities.get_skill(name)
            body = load_skill_text(item.path, budget=6_000) if item else ""
            return f"# Kullanıcının açıkça seçtiği beceri: {name}\n{body}" if body else ""
        if kind == "ajan":
            item = self._all_capabilities.get_agent(name)
            body = load_agent_prompt(item.path)[:6_000] if item else ""
            return f"# Kullanıcının açıkça seçtiği uzman ajan: {name}\n{body}" if body else ""
        if kind == "mcp":
            return (
                f"Kullanıcı bu turda özellikle '{name}' MCP sunucusunun "
                "araçlarını kullanmanı istedi."
            )
        return ""

    def _cancel_turn(self) -> dict[str, Any]:
        if self._turn is None or self._turn.done():
            return {"ok": False, "metin": messages.APP_NO_RUNNING_TURN}
        self._turn.cancel()
        return {"ok": True, "metin": messages.APP_TURN_CANCELLED}

    def resolve_reply(self, reply: Reply) -> bool:
        """Uygulamanın cevabını bekleyen soruya bağla."""
        return self.pending.resolve(reply.id, reply.data)

    async def close(self) -> None:
        """Çalışan turu ve oturuma ait bütün yardımcı süreçleri kapat."""
        from ..providers.web_browser import close_all_browser_sessions
        from ..providers.web_control import stop_all_login_processes

        if self._turn is not None and not self._turn.done():
            self._turn.cancel()
        voice_stop()
        await self._mcp_connections.close()
        await self._processes.close()
        await close_all_browser_sessions()
        stop_all_login_processes()
        self.pending.cancel_all()

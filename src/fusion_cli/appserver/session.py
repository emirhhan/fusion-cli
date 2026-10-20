"""Oturum ömrü: istekleri karşılar, turu çalıştırır, kapanışı düzenler.

Bir süreç BİR oturum yürütür. Uygulama ikinci bir sohbet istiyorsa ikinci bir
süreç başlatır; böylece paylaşılan durum, kilit ve sahiplik sorunları hiç
doğmaz ve bir oturumun çökmesi diğerini etkilemez.

`self._state` (bir `ReplState`) TEK doğru durum kaynağıdır: yapılandırma, onay
modu, motor ve sohbet geçmişi burada yaşar. Komut akışları (`/model`,
`/security`, `/plan`…) `state.config`/`state.approval`'i DEĞİŞTİRİR; bu yüzden
tur çalıştırma ve durum bildirimi HER ZAMAN `self._state` üzerinden okur —
ayrı bir kopya tutulursa (`self._config` gibi) komutlar "uygulandı" der ama
sonraki tur eski değerle koşar (bkz. `geliştirme belgeleri`
C1/C4).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import re
import shlex
import sys
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import replace
from itertools import count
from pathlib import Path
from typing import Any

from ..cli.repl import macros
from ..cli.repl.commands import RENDERED_COMMANDS, build_registry
from ..cli.repl.state import Engine, ReplState
from ..cli.repl.transcript_store import (
    TranscriptStore,
    delete_conversation,
    list_conversations,
    load_transcript_messages,
    move_conversation,
    validate_conversation_move,
)
from ..config.apprentice_notice import apprentice_notice_shown, mark_apprentice_notice_shown
from ..config.credentials import FernetSecretStore
from ..config.eligibility import capability_from_spec
from ..config.keys import secret_key
from ..config.loader import load_config
from ..config.model_select import select_agent_spec
from ..config.models import Config, McpServerConfig
from ..config.paths import credentials_file
from ..core.clock import SystemClock
from ..core.concurrency import BackgroundTasks
from ..core.events import Event, EventSink, StatusChanged
from ..core.owned_thread import await_owned_thread
from ..core.reasoning import ReasoningEffort, resolve_reasoning
from ..core.remotion_browser import RemotionBrowser
from ..core.skill_context import SkillSelection
from ..core.steering import SteeringQueue
from ..core.submission import SubmissionReceipt, SubmissionRepository
from ..core.tools import TodoStatus
from ..core.turn_deadline import TurnDeadline
from ..core.types import Message
from ..engines.agent.approval import ApprovalMode, parse_mode
from ..engines.agent.child_runs import ChildRuns
from ..engines.agent.context_budget import context_budget
from ..engines.agent.loop import CHAT_SYSTEM_PROMPT, AgentOutcome
from ..engines.agent.remotion_bridge import FrameTransport
from ..engines.agent.turn_report import evidence_payload
from ..mcp_bridge.failures import STATE_LOGIN_REQUIRED
from ..memory.factory import build_memory
from ..memory.turn_journal import FileTurnJournal
from ..providers.capabilities import apprentice_active
from ..providers.health_setup import build_health
from ..remote.controller import RemoteController
from ..tools.capabilities import CapabilityRegistry, load_agent_prompt
from ..tools.safe_delete import is_container_root, project_folders
from ..tools.skill_pages import read_skill_page
from ..ui import messages
from ..ui.text import strip_thinking
from ..ui.turn_stop import turn_stopped_summary
from . import intelligence, ui_prefs
from .bridges import PendingQuestions, ProtocolPrompter, ProtocolSink, Writer
from .capabilities import catalog, detail
from .chrome_autoinstall import auto_install_async
from .chrome_bridge import ChromeBridge
from .chrome_install import install_status
from .commands import (
    command_choices,
    list_commands,
    render_command_text,
    run_command,
)
from .connectors import (
    add_connector_verified,
    connector_secret_values,
    list_connectors,
    remove_connector,
    review_connector,
    status_payload,
)
from .context_gauge import baglam_olcusu
from .control import (
    connect_web_session,
    delete_secret,
    disconnect_web_session,
    provider_catalog_rows,
    reset_apprentice_default,
    save_secret,
    snapshot,
    start_web_login,
    verify_web_session,
    web_login_state,
    web_provider_cards,
)
from .conversation_title import conversation_title
from .desktop_activity import DesktopActivity
from .desktop_dock import DesktopDock
from .desktop_routes import DESKTOP_ROUTES, dispatch_desktop
from .file_search import FileSearchIndex, search_project_files
from .history import (
    PreparedResume,
    list_sessions,
    list_sources,
    prepare_resume,
    preview_session,
    search_sessions,
)
from .history_view import visible_history
from .hosted_connectors import (
    add_hosted_connector,
    hosted_provider_rows,
    remove_hosted_connector,
    verify_hosted_connector,
)
from .image_chat import parse_image_command, run_image_command
from .image_create import create_image, image_output_dir, image_providers
from .image_flows import export_image, list_flows, load_flow, save_flow
from .image_job_artifacts import capture_reference, receipt_reads_supported
from .image_jobs import ImageJobService
from .instructions import get_instructions, instruction_block, save_instructions
from .library import LibrarySink, add_upload, remove_entry
from .local_computer import LocalComputer, native_local_computer
from .local_computer_routes import LOCAL_COMPUTER_ROUTES, dispatch_local_computer
from .mcp_catalog import list_tool_catalog
from .model_catalog import list_selectable_models
from .personal_memory import PersonalMemory
from .processes import ProcessManager
from .project_status import git_status, suggested_commands
from .protocol import Reply, Request, encode_event, encode_result
from .runtime_prefs import persist_approval, persist_engine
from .schedule import SCHEDULE_ROUTES
from .tiers import list_tiers, select_tier
from .usage import UsageMeter, usage_status
from .voice import discard_prepared_voice, play_prepared_voice, prepare_voice, warm_voice
from .voice import download_voice_model as voice_download_model
from .voice import save_settings as voice_settings
from .voice import speak as voice_speak
from .voice import status as voice_status
from .voice import stop as voice_stop
from .voice import wait_for_speech as voice_wait
from .voice_context import VoiceTurnContext, parse_voice_context
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

#: Chrome bağlıyken ajana verilen tarayıcı ilkesi. Ölçüldü (26 Eylül, Google Ads):
#: model hesap seçim ekranında durup "hesap seçmemi ister misin?" diye sordu; salt
#: okuma görevinde görevde adı geçen ya da tek uygun hesabı seçmek beklenen adımdır.
CHROME_NOTE = (
    "Bu bir tarayıcı ajanı görevidir: 'siteye gir', 'kayıt ol', 'formu doldur', 'sayfadan çıkar', "
    "'hesabımı incele' gibi isteklerde HEMEN chrome_navigate (ya da chrome_action open) ile "
    "siteyi kullanıcının Chrome'unda aç, chrome_page ile oku, tıkla, yaz, kaydır. Sunucu "
    "tarafında sayfa getirme ya da arama aracı YOKTUR ve kullanıcının girişli oturumunu "
    "görmez; adres bilinmiyorsa Chrome'da arama sitesini aç. Çift tıklama, sağ tıklama, "
    "sürükleme ve fare tekerleği chrome_action'ın double_click, right_click, drag ve wheel "
    "işlemleridir. İzin kartı açıldıysa kullanıcıya söyle ve onay gelene kadar bekle. "
    "Kullanıcı AÇIKÇA dosya, kod ya da proje isterse çalışma alanı araçlarını kullan; "
    "aksi halde iş tarayıcıdadır. "
    "İnternet sitelerindeki işler (Google Ads, Instagram, Meta, mağaza paneli, herhangi bir "
    "site) kullanıcının kendi Chrome'unda chrome_* araçlarıyla yapılır; Chrome kapalıysa Fusion "
    "onu kendisi açar. browser_* ayrı ve oturumsuz bir tarayıcıdır, yalnız yerel projeyi "
    "(localhost) denemek içindir; orada giriş sayfası görmen oturumun kapalı olduğu anlamına "
    "gelmez. Tarayıcı işlerinde okuma için gereken ara adımları (hesap veya "
    "sayfa seçimi, sekme açma, 'daha fazla göster', kaydırma) kendin yap: görevde adı geçen "
    "ya da tek uygun seçeneği seç. Yalnız giriş/şifre, ödeme ve gönderme/yayınlama/silme "
    "adımlarında dur. Sayfa gerçekten giriş istiyorsa bunu açıkça söyle. Yeni sayfada önce "
    "chrome_page'i query olmadan çağırıp sayfayı oku; adresi biliyorsan menüde arama yerine "
    "doğrudan git. Uzun sayfanın tamamı için chrome_action text (value: sayfa no); ref'i olmayan "
    "öğede screenshot alıp click_at 'x,y' kullan. Tanıtım ya da giriş sayfasına düşersen "
    "hemen 'oturum kapalı' deme: önce "
    "'tabs' ile açık sekmelere bak, sonra sitenin uygulama adresini dene (ör. Google Ads: "
    "ads.google.com/aw/overview); oturumun kapalı olduğunu ancak giriş formunu görünce söyle. "
    "Kullanıcı bir siteden component alıp projeye uygulamanı isterse önce sayfayı Chrome "
    "eklentisiyle incele, sonra çalışma alanındaki dosyaları okuyup düzenle ve sonucu "
    "doğrula. Uygulama yolunda somut bir belirsizlik veya tekrarlanan hata varsa "
    "ask_teacher ile tek net soru sor; yanıtı değerlendirip işe devam et."
)

CHROME_TURN_TOOLS = {
    "chrome_page",
    "chrome_action",
    "chrome_click",
    "chrome_type",
    "chrome_navigate",
    "todo_write",
}
#: Kod çalışma alanında panel görevi siteden aldığını projeye de uygulayabilir.
#: `web_fetch`/`web_search` BİLEREK yok: sunucu tarafı getirme kullanıcının girişli
#: oturumunu görmez. Ölçüldü (17 Ekim, Meta Ads): kod kipinde araç kısıtı yoktu,
#: model `web_fetch` seçti, tarayıcı araçlarını hiç çağırmadı.
CHROME_CODE_TURN_TOOLS = CHROME_TURN_TOOLS | {
    "read_file",
    "write_file",
    "edit_file",
    "multi_edit",
    "list_dir",
    "grep",
    "glob",
    "run_shell",
    "ask_teacher",
}


def _refresh_teacher(config: Config) -> Config:
    """Refresh web teacher without losing unsaved in-session model choices."""
    return replace(config, teacher=load_config(config.source).teacher)


#: Tur günlüğü dosya adında konuşma kimliğinin güvenli karakterleri.
_SAFE_JOURNAL_ID = re.compile(r"[^a-zA-Z0-9._-]+")

#: Modele gönderilecek tek görselin üst sınırı. Büyük bir görsel isteği şişirir,
#: çoğu uçta reddedilir ve kullanıcıya sebebi belirsiz bir hata döner.
MAX_GORSEL_BAYT = 5 * 1024 * 1024

#: İptal edilen turun kapanması için tanınan süre.
#:
#: İptal anında tarayıcı ya da alt süreç çağrısı bırakılırken birkaç yüz
#: milisaniye geçebiliyor. Bu kadarı kullanıcıyı bekletmez; daha uzun beklemek
#: ise "durdurdum, yazamıyorum" hissini uzatırdı.
TURN_CANCEL_SETTLE_S = 2.0

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


def _discard_line(_line: str) -> None:
    """Yan panel turunun satırları masaüstü teline yazılmaz (bkz. `_run_turn`)."""


#: Bütçeyle kesilen uzun işin kullanıcıya sorulmadan kaç kez sürdürüleceği.
#
# Üç: her devam turu kendi tam bütçesini alır; gerçek değişiklik yapmayan tur
# zinciri koparır (bkz. `_should_auto_continue`), bu yüzden kaçak döngü olmaz.
MAX_AUTO_CONTINUE_TURNS = 3
#: Kendiliğinden sürdürülebilen durma sebepleri. Tekrar, bozuk araç çağrısı ve
#: boş yanıt modelin kendisindeki bir sorundur; aynı modelle sürdürmek çözmez.
_AUTO_CONTINUE_REASONS = frozenset(
    {"no_progress", "inactivity", "model_calls", "tool_rounds", "deadline"}
)


def _should_auto_continue(outcome: object, auto_continues: int) -> bool:
    """Bütçeyle kesilen tur kullanıcı beklemeden sürdürülmeli mi?"""
    if auto_continues >= MAX_AUTO_CONTINUE_TURNS:
        return False
    if not getattr(outcome, "budget_stopped", False):
        return False
    if getattr(outcome, "stop_reason", None) not in _AUTO_CONTINUE_REASONS:
        return False
    todos = getattr(outcome, "todos", ())
    bekleyen = any(item.status is not TodoStatus.COMPLETED for item in todos)
    # Bu turda gerçek değişiklik yoksa sürdürmek aynı çıkmaza geri döner.
    return bekleyen and getattr(outcome, "mutating_tool_calls_made", 0) > 0


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


def _title_payload(message: object) -> dict[str, Any]:
    """`sohbet.baslik`: ilk mesajdan başlık. Model çağrılmaz (bkz. `conversation_title`)."""
    if not isinstance(message, str):
        return {"ok": False, "metin": "Başlık için mesaj metni zorunludur."}
    return {"ok": True, "baslik": conversation_title(message)}


class AppSession:
    """Uygulamanın sürdüğü tek oturum."""

    def __init__(
        self,
        writer: Writer,
        *,
        root: Path,
        home: Path,
        remotion_transport: FrameTransport | None = None,
        remotion_browser: RemotionBrowser | None = None,
        require_remotion_kit: bool = False,
        local_computer: LocalComputer | None = None,
        submission_store: SubmissionRepository | None = None,
    ) -> None:
        self._admission_lock = asyncio.Lock()
        self._closed = False
        self._voice_preparations: set[asyncio.Task[dict[str, Any]]] = set()
        self._admission_tasks: set[asyncio.Task[dict[str, Any]]] = set()
        self._model_selection_tasks: set[asyncio.Task[dict[str, Any]]] = set()
        self._image_tasks: set[asyncio.Task[dict[str, Any]]] = set()
        self._submission_task: asyncio.Task[dict[str, Any]] | None = None
        self._local_computer = local_computer
        self._writer = writer
        self._require_remotion_kit = require_remotion_kit
        self._root = root
        self._home = home
        config = load_config()
        self._secret_store = FernetSecretStore(credentials_file(), secret_key=secret_key())
        self._remote: RemoteController | None = None
        self._personal_memory = PersonalMemory(config.memory_dir)
        from ..memory.image_job_store import ImageJobStore

        self._submission_store = submission_store or ImageJobStore(
            config.memory_dir / "submission.sqlite3"
        )
        self._image_jobs = (
            ImageJobService(self._submission_store, image_output_dir())
            if isinstance(self._submission_store, ImageJobStore) and receipt_reads_supported()
            else None
        )
        self.pending = PendingQuestions()
        self._child_runs: ChildRuns | None = None
        self._steering: SteeringQueue | None = None
        self._steering_turn: str | None = None
        self._steering_requests: set[str] = set()
        self._registry = build_registry(home)
        self._state = ReplState.from_runtime_config(
            config,
            memory=build_memory(config, root=root),
            root=root,
            home=home,
            health=build_health(config),
            remotion_transport=remotion_transport,
            remotion_browser=remotion_browser,
        )
        #: Uygulamanın sekmesine karşılık gelen konuşma kimliği. `oturum.baslat`
        #: ile gelir; gelmeden önce okuma proje genelini gösterir.
        self._conversation_id: str | None = None
        #: (kök, depo projeleri) — durum her turdan sonra sorulduğu için önbellekli.
        self._depo_cache: tuple[Path, list[str]] | None = None
        #: İptal edilen turun kapanması bekleniyor mu?
        self._iptal_bekliyor = False
        self._state.history = load_transcript_messages(config.memory_dir, root)
        # YAZMA kimliği asla rastgele olmaz. Ölçüldü (kullanıcının diski, 7 Eylül):
        # kimliksiz açılan depo her seferinde `session-<zaman>-<rastgele>` üretti ve
        # o konuşmalara bir daha ulaşılamadı — 110 sohbetin çoğu böyle orphan kaldı.
        # Sekme kimliği gelene kadar yazılanlar, ulaşılabilir tek bir sohbette durur.
        self._transcript_store = TranscriptStore(
            config.memory_dir, root, conversation_id=FALLBACK_CONVERSATION_ID
        )
        #: "sohbet" ya da "kod". Varsayılan artık KOD (Faz 5, Görev 5 — "tek
        #: kutu"): arayüzdeki manuel kip düğmesi kaldırıldı, kullanıcı artık
        #: hiçbir seçim yapmıyor. Eski gerekçe ("merhaba"da proje taranmasın)
        #: geçerliliğini KORUYOR ama artık bir DEĞİŞ TOKUŞ: basit bir selamda
        #: bile proje köküne bağlanılır. Mekanizmanın kendisi (`_apply_
        #: workspace_mode`, `chat_mode`) SİLİNMEDİ — yalnızca varsayılan
        #: değişti; programatik istemciler hâlâ `kip: "sohbet"` gönderebilir.
        self._workspace_mode = "kod"
        self._workspace_journal = WorkspaceJournal()
        self._processes = ProcessManager(self._state.root, writer)
        #: `@` ile dosya anmanın kısa ömürlü dosya listesi önbelleği.
        self._file_search = FileSearchIndex()
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
        # Kullanıcının bu tur için seçtiği beceri/ajan/MCP'ler (örn. `/beceri` + `@mcp`).
        self._pending_capabilities: list[tuple[str, str]] = []
        self._taken_skill: SkillSelection | None = None
        self._refresh_capabilities()
        self._usage = UsageMeter()
        #: Yan panelin kendi konuşma geçmişi (uygulamanın sohbetinden ayrı).
        self._chrome_history: list[Message] = []
        self._chrome = ChromeBridge(
            self._chrome_turn,
            self._cancel_turn,
            self._chrome_answer,
            self._chrome_settings,
            installer=auto_install_async,
            extension_installed=lambda: bool(install_status()["eklenti_yuklu"]),
        )
        self._desktop_dock = DesktopDock(chrome=self._chrome)
        self._desktop_activity = DesktopActivity()
        from ..mcp_bridge.service import McpConnectionService

        self._mcp_connections = McpConnectionService()
        from .accounts import AccountService

        #: Hesap uçları. Depo hesaptan BAĞIMSIZ bir dosyadadır; etkin hesap
        #: süreç açılışında zaten seçilmiştir (bkz. `cli` giriş noktası).
        self._accounts = AccountService()
        #: Sağlayıcı connector panelini açan arka plan görevleri (sağlayıcı → görev).
        #: Pencere kullanıcı kapatana kadar yaşar; RPC onu beklemez.
        self._panel_tasks: dict[str, asyncio.Task[None]] = {}
        self._voice_background = BackgroundTasks()
        self._turn: asyncio.Task[Any] | None = None
        self._turn_settled = asyncio.Event()
        self._turn_settled.set()
        #: Bir makronun (`/goal` …) bir SONRAKİ tura taşıyacağı davranış kipi.
        self._next_turn_mode = macros.Mode.NONE

    async def handle(self, request: Request) -> None:
        """İsteği çalıştır ve sonucunu yaz. İstisna sızdırmaz."""
        try:
            data = await self._dispatch(request)
        except Exception as error:  # istek sınırı: süreç çökmemeli
            data = {"ok": False, "metin": str(error)}
        self._writer(encode_result(request.id, data))

    def _remote_controller(self) -> RemoteController:
        """Uzak erişim yöneticisi ilk `uzak.*` isteğinde kurulur; açılışa maliyeti yok."""
        if self._remote is None:
            root, home = self._root, self._home
            self._remote = RemoteController(
                home=home,
                root=root,
                secrets=self._secret_store,
                session_factory=lambda writer: AppSession(writer, root=root, home=home),
                navigation=self._desktop_dock,
            )
        return self._remote

    async def _chrome_turn(self, prompt: str) -> dict[str, Any]:
        """Yan panelden gelen görevi mevcut sohbetin aynı onay kapısında yürüt."""
        self._chrome.publish({"tur": "basladi"})
        result = await self._run_turn(prompt, browser_only=True)
        answer = result.get("metin")
        if isinstance(answer, str):
            # Açılışsız `</think>` de `strip_thinking` içinde ayıklanır.
            result["metin"] = strip_thinking(answer).strip()
        # Panel tur sürerken kapanıp açılabilir: sonuç akışta da durur.
        self._chrome.publish({"tur": "bitti", "ok": result.get("ok"), "metin": result.get("metin")})
        return result

    async def _chrome_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        """Yan panelin model seçici ve "Önce sor / Sormadan yap" anahtarı.

        Claude in Chrome'daki gibi panel modeli ve izin kipini kendisi seçer. Model
        masaüstündeki `/development uygula` komutuyla değişir: doğrulama aynıdır.
        """
        if data.get("yeni") is True:
            # Paneldeki "temizle": yeni panel konuşması, uygulamanın sohbeti etkilenmez.
            if self._turn is not None and not self._turn.done():
                return {"ok": False, "metin": "Görev sürerken yeni sohbet açılamaz."}
            self._chrome_history = []
        mode = data.get("mod")
        if mode is not None:
            error = self._apply_mode(mode if isinstance(mode, str) else "")
            if error is not None:
                return error
        model, source = data.get("model"), data.get("kaynak")
        if model is not None or source is not None:
            if not all(
                isinstance(v, str) and v and not re.search(r"\s", v) for v in (model, source)
            ):
                return {"ok": False, "metin": "Model ve kaynak geçersiz."}
            if self._turn is not None and not self._turn.done():
                return {"ok": False, "metin": "Görev sürerken model değiştirilemez."}
            result = await self._run_command(
                {"ad": "development", "arguman": f"uygula {source} {model}"}
            )
            if result.get("ok") is False:
                return result
        catalog = await list_selectable_models(self._state.config, workspace_mode="sohbet")
        return {
            "ok": True,
            "model": self._state.config.agent.model,
            "mod": self._state.approval.value,
            "modeller": catalog.get("modeller", []),
        }

    def _question_closed(self, question_id: str) -> None:
        """Her terminal soru sonucu tüm bağlı yüzeylerde aynı kartı kapatır."""
        self._writer(encode_event({"olay": "SoruKapandi", "id": question_id}))
        if self._chrome.running:
            self._chrome.publish({"tur": "soru_kapandi", "id": question_id})

    def _chrome_answer(self, question_id: str, data: dict[str, Any]) -> bool:
        """Yan panelin izin/soru cevabı; masaüstündeki aynı kart da kapanır."""
        return self.pending.resolve(question_id, data)

    async def _dispatch(self, request: Request) -> dict[str, Any]:
        """Model ve web yapılandırma girişleri aynı owned kabul sırasını paylaşır."""
        if request.name in {
            "kademe.sec",
            "kontrol.cirak_varsayilanina_don",
            "web.model_sec",
            "web.baglan",
            "web.cikis",
            "web.arac_olc",
            "web.dogrula",
            "web.pencere_kipi",
            "baglanti.guven",
        }:
            owned = asyncio.create_task(self._apply_model_rpc(request))
            self._model_selection_tasks.add(owned)
            owned.add_done_callback(self._model_selection_done)
            return await asyncio.shield(owned)
        return await self._dispatch_unlocked(request)

    async def _apply_model_rpc(self, request: Request) -> dict[str, Any]:
        async with self._admission_lock:
            if self._closed:
                return {"ok": False, "metin": "Oturum kapandı; model seçimi uygulanmadı."}
            return await self._dispatch_unlocked(request)

    async def _dispatch_unlocked(self, request: Request) -> dict[str, Any]:
        if request.name.startswith("uzak."):
            return await self._remote_controller().dispatch(request.name, request.data)
        if request.name == "ajan.durdur":
            identifier = request.data.get("agentId")
            if (
                self._child_runs is None
                or self._steering_turn is None
                or request.data.get("turnId") != self._steering_turn
                or not isinstance(identifier, str)
            ):
                return {"ok": False, "metin": "Etkin alt ajan görevi bulunamadı."}
            cancelled = await self._child_runs.cancel(identifier)
            return {
                "ok": cancelled,
                "agentId": identifier,
                "state": "cancelled" if cancelled else "stale",
            }
        if request.name == "tur.yonlendir":
            target = request.data.get("turnId")
            text = request.data.get("text")
            identifier = request.data.get("requestId")
            if (
                self._steering is None
                or self._iptal_bekliyor
                or target != self._steering_turn
                or not isinstance(text, str)
                or not text.strip()
                or not isinstance(identifier, str)
                or not identifier
            ):
                return {"ok": False, "metin": "Etkin görevle eşleşen yönlendirme bulunamadı."}
            if identifier not in self._steering_requests:
                self._steering_requests.add(identifier)
                self._steering.push(text)
                self.pending.cancel_all()
            return {"ok": True, "turnId": target, "requestId": identifier, "state": "queued"}
        if request.name == "soru.cevapla":
            identifier = request.data.get("questionId")
            answer = request.data.get("answer")
            if not isinstance(identifier, str) or not isinstance(answer, dict):
                return {"ok": False, "metin": "Soru kimliği veya cevap geçersiz."}
            accepted = self.pending.answer(identifier, answer)
            return {"ok": accepted, "questionId": identifier}
        if request.name in LOCAL_COMPUTER_ROUTES:
            if self._local_computer is not None:
                return await dispatch_local_computer(
                    request.name,
                    request.data,
                    self._local_computer,
                    lambda: self._state.root,
                    lambda: self._conversation_id,
                )
            # Üretim yolu: istek anındaki kök ve konuşmaya bağlı yerel gözlemci kurulur.
            # Kits'ten gelen istekte Fusion konuşması seçili olmayabilir; oturum adı sabittir.
            oturum = self._conversation_id or "fusion-app"
            return await dispatch_local_computer(
                request.name,
                request.data,
                native_local_computer(self._state.root, oturum),
                lambda: self._state.root,
                lambda: self._conversation_id or "fusion-app",
            )
        if request.name == "gorsel.saglayicilar":
            providers = {
                "ok": True,
                "secenekler": image_providers(self._state.config),
                "assetProtokolu": 1,
            }
            if self._image_jobs is not None:
                providers["isProtokolu"] = 1
            return providers
        if request.name in {
            "gorsel.is.baslat",
            "gorsel.is.durum",
            "gorsel.is.iptal",
            "gorsel.is.liste",
        }:
            return await self._image_job_request(request.name, request.data)
        if request.name == "gorsel.olustur":
            return await self._create_image_owned(request.data)
        if request.name == "gorsel.galeri":
            from .asset_bridge import catalogued_gallery, gallery_page

            if "sinir" in request.data or "cursor" in request.data:
                return await await_owned_thread(
                    gallery_page, request.data, self._state.config.memory_dir
                )
            return await await_owned_thread(catalogued_gallery, self._state.config.memory_dir)
        if request.name == "artefakt.coz":
            from .asset_bridge import resolve_asset

            return await await_owned_thread(
                resolve_asset, request.data, self._state.config.memory_dir
            )
        if request.name == "artefakt.liste":
            from .asset_bridge import asset_page

            return await await_owned_thread(asset_page, request.data, self._state.config.memory_dir)
        if request.name == "artefakt.onizle":
            from .asset_bridge import asset_preview

            return await await_owned_thread(
                asset_preview, request.data, self._state.config.memory_dir
            )
        if request.name == "gorsel.kaydet":
            return export_image(request.data)
        if request.name == "gorsel.akislar":
            return list_flows()
        if request.name == "gorsel.akis.kaydet":
            return await await_owned_thread(save_flow, request.data)
        if request.name == "gorsel.akis.yukle":
            return load_flow(request.data)
        if request.name in SCHEDULE_ROUTES:
            return SCHEDULE_ROUTES[request.name](request.data)
        if request.name == "kitaplik.liste":
            from .asset_bridge import catalogued_library

            return await await_owned_thread(
                catalogued_library, request.data, self._state.config.memory_dir
            )
        if request.name == "kitaplik.ekle":
            return add_upload(request.data)
        if request.name == "kitaplik.kaldir":
            return remove_entry(request.data)
        if request.name in DESKTOP_ROUTES:
            return await dispatch_desktop(
                self._desktop_dock, self._desktop_activity, request.name, request.data
            )
        if request.name == "chrome.baslat":
            return {"ok": True, **await self._chrome.start()}
        if request.name == "chrome.durum":
            return {"ok": True, **self._chrome.status(), **await asyncio.to_thread(install_status)}
        if request.name == "chrome.kur":
            # Köprü açık olsun ki eklenti yüklenir yüklenmez el sıkışabilsin.
            kurulum = await auto_install_async()
            if not kurulum["ok"]:
                return kurulum
            return {**kurulum, **await self._chrome.start()}
        if request.name == "araclar.algila":
            from .dev_tools import detect_dev_tools

            return await asyncio.to_thread(detect_dev_tools)
        if request.name == "chrome.durdur":
            await self._chrome.close()
            return {"ok": True}
        if request.name == "oturum.baslat":
            return self._start_session(request.data)
        if request.name == "oturum.durum":
            return self._status()
        if request.name == "oturum.gecmis":
            return {
                "ok": True,
                "mesajlar": visible_history(self._state.history),
            }
        if request.name == "sohbet.sil":
            return await self._delete_conversation(request.data)
        if request.name == "sohbet.dallan":
            from .response_actions import fork_response

            return await await_owned_thread(
                fork_response,
                self._state.config.memory_dir,
                self._root,
                self._conversation_id or FALLBACK_CONVERSATION_ID,
                list(self._state.history),
                request.data,
            )
        if request.name == "yanit.degerlendir":
            from .response_actions import save_rating

            return await await_owned_thread(
                save_rating,
                self._state.config.memory_dir,
                self._conversation_id or FALLBACK_CONVERSATION_ID,
                request.data,
            )
        if request.name == "sohbet.tasi":
            return await self._move_conversation(request.data)
        if request.name == "sohbet.listele":
            return self._list_conversations()
        if request.name == "sohbet.baslik":
            return _title_payload(request.data.get("metin"))
        if request.name == "kademe.listele":
            return list_tiers(self._state.config)
        if request.name == "kademe.sec":
            self._state.config, sonuc = select_tier(self._state.config, request.data)
            if sonuc.get("ok") is True:
                from ..cli.repl import model_flows

                applied = await asyncio.to_thread(
                    model_flows.applied_result, self._state.config, str(request.data.get("ad", ""))
                )
                sonuc = {**sonuc, "metin": applied.message}
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
                # Kullanıcının kendi devralma eylemi, o oturumun klasörlerine açık izindir.
                self._state.extra_roots = tuple(
                    dict.fromkeys((*self._state.extra_roots, *prepared.work_dirs))
                )
                self._state.history = list(prepared.messages)
                return prepared.payload
            return prepared
        if request.name == "proje.durum":
            return workspace_status(self._state.root)
        if request.name == "proje.listele":
            return list_entries(self._state.root, request.data)
        if request.name == "proje.dosya_ara":
            return search_project_files(self._file_search, self._state.root, request.data)
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
        if request.name == "kontrol.anahtar_goster":
            from .control import reveal_secret

            return reveal_secret(self._secret_store, str(request.data.get("saglayici", "")))
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
        if request.name == "kontrol.cirak_varsayilanina_don":
            # `yeni` bu metotta BAŞKA dallarda `Config | None` döndüren yardımcılarla
            # paylaşılan bir isim (mypy tek metotta tek tip çıkarır); bu dal her zaman
            # dolu bir `Config` döndürdüğü için çakışmayı önlemek üzere ayrı adlandırıldı.
            guncel_config, sonuc = reset_apprentice_default(self._state.config)
            self._state.config = guncel_config
            return sonuc
        if request.name == "kontrol.gateway_baslat":
            return await self._start_gateway()
        if request.name == "kontrol.gateway_durdur":
            return await self._stop_gateway()
        if request.name == "ses.durum":
            return voice_status()
        if request.name == "ses.isit":
            return await self._voice_worker(warm_voice, None)
        if request.name == "ses.hazirla":
            return await self._voice_worker(prepare_voice, request.data.get("metin"))
        if request.name == "ses.haziri_cal":
            return await self._voice_worker(play_prepared_voice, request.data.get("hazir_id"))
        if request.name == "ses.haziri_sil":
            return await self._voice_worker(discard_prepared_voice, request.data.get("hazir_id"))
        if request.name == "ses.konus":
            result = await self._voice_worker(voice_speak, request.data.get("metin"))
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
        if request.name == "hesap.durum":
            return self._accounts.status()
        if request.name == "hesap.kayit":
            return self._accounts.register(request.data)
        if request.name == "hesap.giris":
            return self._accounts.login(request.data)
        if request.name == "hesap.cikis":
            return self._accounts.logout()
        if request.name == "hesap.kurtar":
            return self._accounts.recover(request.data)
        if request.name == "hesap.guncelle":
            return self._accounts.update(request.data)
        if request.name == "hesap.avatar_yukle":
            return self._accounts.upload_avatar(request.data)
        if request.name == "hesap.sil":
            return self._accounts.remove(request.data)
        if request.name == "ayar.talimat":
            return get_instructions()
        if request.name == "zeka.durum":
            return intelligence.status(self._state)
        if request.name == "zeka.ayarla":
            if self._turn is not None and not self._turn.done():
                return {
                    "ok": False,
                    "metin": "Zeka ayarını değiştirmeden önce çalışan görevi durdur.",
                }
            return intelligence.apply(self._state, request.data)
        if request.name == "ayar.arayuz":
            return ui_prefs.load()
        if request.name == "ayar.arayuz_kaydet":
            return ui_prefs.save(request.data)
        if request.name == "ayar.tema":
            return {"ok": True, "tema": self._state.config.runtime.theme}
        if request.name == "ayar.tema_kaydet":
            return self._save_theme(request.data)
        if request.name == "ayar.talimat_kaydet":
            return save_instructions(request.data.get("metin"))
        if request.name == "baglanti.guven":
            if (self._turn is not None and not self._turn.done()) or (
                self._submission_task is not None and not self._submission_task.done()
            ):
                return {
                    "ok": False,
                    "metin": "Güven sınırını değiştirmeden önce çalışan görevi durdur.",
                }
            updated, result = review_connector(self._state.config, request.data)
            if updated is not None:
                self._update_connector_config(updated)
            return result
        if request.name == "baglanti.listele":
            return list_connectors(self._state.config, self._mcp_connections.statuses)
        if request.name == "baglanti.araclar":
            source_config, source_root = self._state.config, self._state.root
            server = self._connector(request.data.get("ad"))
            if server is None:
                return {"ok": False, "metin": "Bağlantı bulunamadı."}
            result = await list_tool_catalog(server)
            if source_config is not self._state.config or source_root != self._state.root:
                return {"ok": False, "metin": "Bağlantı değişti; katalog yeniden okunmalı."}
            return result
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
        if request.name == "baglanti.saglayicilar":
            return {"ok": True, "saglayicilar": hosted_provider_rows(self._state.config)}
        if request.name == "baglanti.saglayici_ekle":
            return self._change_connectors(add_hosted_connector, request.data)
        if request.name == "baglanti.saglayici_dogrula":
            yeni, sonuc = await verify_hosted_connector(self._state.config, request.data)
            if yeni is not None:
                self._state.config = yeni
            return sonuc
        if request.name == "baglanti.saglayici_sil":
            return self._change_connectors(remove_hosted_connector, request.data)
        if request.name == "baglanti.panel_ac":
            return await self._open_connector_panel(request.data)
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
        if request.name == "web.model_secenekleri":
            from ..providers.web_control import session_model_choices

            return await session_model_choices(
                self._state.config,
                str(request.data.get("saglayici") or ""),
                str(request.data.get("hesap") or "main"),
            )
        if request.name == "web.model_sec":
            from ..providers.web_control import set_session_model_choice

            yeni, sonuc = await set_session_model_choice(
                self._state.config,
                str(request.data.get("saglayici") or ""),
                str(request.data.get("hesap") or "main"),
                str(request.data.get("secim") or ""),
            )
            if yeni is not None:
                self._state.config = _refresh_teacher(yeni)
            return sonuc
        if request.name == "web.giris":
            from ..providers.web_browser import close_browser_session, normalize_account

            await close_browser_session(
                str(request.data.get("saglayici") or ""),
                normalize_account(str(request.data.get("hesap") or "main")),
            )
            return start_web_login(request.data.get("saglayici"), request.data.get("hesap"))
        if request.name == "web.baglan":
            return self._change_web_session(
                connect_web_session, request.data.get("saglayici"), request.data.get("hesap")
            )
        if request.name == "web.pencere_kipi":
            return await self._change_web_window_mode(request.data)
        if request.name == "web.cikis":
            return self._change_web_session(
                disconnect_web_session, request.data.get("saglayici"), request.data.get("hesap")
            )
        if request.name == "web.arac_olc":
            from .tool_measure import measure_tool_support

            olcum = await measure_tool_support(
                self._state.config,
                str(request.data.get("saglayici", "")),
                str(request.data.get("hesap", "main")),
            )
            # Ölçüm yapılandırmayı değiştirdi; oturum eski hâli taşımasın.
            if olcum.get("ok"):
                self._state.config = load_config()
            return olcum
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
                # Doğrulanmış web oturumu öğretmeni aynı çalışan oturumda açar.
                self._state.config = _refresh_teacher(yeni)
            return sonuc
        if request.name == "web.giris_durumu":
            return web_login_state(request.data.get("pid"))
        if request.name == "komut.listele":
            return {"ok": True, "komutlar": list_commands(self._registry)}
        if request.name == "komut.calistir":
            return await self._run_command(request.data)
        if request.name == "komut.secenekler":
            return self._command_options(request.data)
        if request.name == "model.roller":
            from .model_roles import role_state

            return await role_state(self._state.config)
        if request.name == "model.rol_ata":
            from .model_roles import assign

            yeni, sonuc = await assign(
                self._state.config,
                str(request.data.get("rol") or ""),
                request.data.get("deger"),
            )
            if yeni is not None:
                self._state.config = yeni
            return sonuc
        if request.name == "model.katalog":
            return await list_selectable_models(
                self._state.config,
                workspace_mode=str(request.data.get("kip") or "sohbet"),
            )
        if request.name == "bellek.listele":
            return await asyncio.to_thread(self._personal_memory.list)
        if request.name == "bellek.ekle":
            return await asyncio.to_thread(self._personal_memory.add, request.data.get("metin"))
        if request.name == "bellek.sil":
            return await asyncio.to_thread(self._personal_memory.delete, request.data.get("id"))
        if request.name == "bellek.etkinlestir":
            return await asyncio.to_thread(
                self._personal_memory.set_enabled, request.data.get("etkin")
            )
        if request.name == "tur.calistir":
            if isinstance(request.data.get("gonderim_id"), str):
                return await self._submit_turn(request)
            try:
                voice_context = parse_voice_context(request.data.get("sesli"))
                deadline = TurnDeadline.from_duration(request.data.get("sure_s"), SystemClock())
            except ValueError as error:
                return {"ok": False, "metin": str(error)}
            attachment_context, attachment_error = _attachment_context(request.data.get("ekler"))
            if attachment_error:
                return {"ok": False, "metin": attachment_error}
            return await self._run_turn(
                str(request.data.get("gorev", "")),
                attachment_context,
                _attachment_images(request.data.get("ekler")),
                voice_context=voice_context,
                deadline=deadline,
            )
        if request.name == "tur.kes":
            if "turnId" in request.data and request.data["turnId"] != self._steering_turn:
                return {"ok": False, "metin": "Durdurma isteği etkin görevle eşleşmiyor."}
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
        await self._submission_store.delete_conversation(
            str(self._state.config.memory_dir.resolve()),
            str(root),
            conversation_id,
        )
        if root == current_root and conversation_id == self._transcript_store.session_id:
            self._cancel_turn()
            self._state.history = []
        return {"ok": True, "sohbet_id": conversation_id}

    async def _move_conversation(self, data: dict[str, Any]) -> dict[str, Any]:
        conversation_id = data.get("sohbet_id")
        source_value = data.get("kaynak_kok")
        target_value = data.get("hedef_kok")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (conversation_id, source_value, target_value)
        ):
            return {"ok": False, "metin": "Sohbet ve iki proje kökü zorunludur."}
        assert isinstance(conversation_id, str)
        assert isinstance(source_value, str)
        assert isinstance(target_value, str)
        source = await asyncio.to_thread(lambda: Path(source_value).expanduser().resolve())
        target = await asyncio.to_thread(lambda: Path(target_value).expanduser().resolve())
        current_root = await asyncio.to_thread(self._root.resolve)
        if source == current_root and conversation_id == self._transcript_store.session_id:
            return {"ok": False, "metin": "Açık sohbeti taşıyabilmek için önce kapat."}
        if source == target:
            return {"ok": False, "metin": "Sohbet zaten bu projede."}
        profile = str(self._state.config.memory_dir.resolve())
        import sqlite3

        try:
            prepared = await self._submission_store.move_prepared(
                profile, str(source), conversation_id, str(target)
            )
            source_exists = any(
                ref.conversation_id == conversation_id
                for ref in list_conversations(self._state.config.memory_dir, source)
            )
            target_exists = any(
                ref.conversation_id == conversation_id
                for ref in list_conversations(self._state.config.memory_dir, target)
            )
            if prepared and not source_exists and target_exists:
                await self._submission_store.move_conversation(
                    profile, str(source), conversation_id, str(target)
                )
                return {"ok": True, "sohbet_id": conversation_id, "hedef_kok": str(target)}
            await asyncio.to_thread(
                validate_conversation_move,
                self._state.config.memory_dir,
                source,
                target,
                conversation_id,
            )
            await self._submission_store.prepare_move(
                profile, str(source), conversation_id, str(target)
            )
            await asyncio.to_thread(
                move_conversation,
                self._state.config.memory_dir,
                source,
                target,
                conversation_id,
            )
        except (ValueError, OSError, sqlite3.Error):
            return {"ok": False, "metin": messages.APP_SUBMISSION_STORAGE_FAILED}
        try:
            await self._submission_store.move_conversation(
                str(self._state.config.memory_dir.resolve()),
                str(source),
                conversation_id,
                str(target),
            )
        except (ValueError, OSError, sqlite3.Error):
            return {"ok": False, "metin": messages.APP_SUBMISSION_STORAGE_FAILED}
        return {"ok": True, "sohbet_id": conversation_id, "hedef_kok": str(target)}

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
                    # Diskte ilk mesajın ilk satırı durur; liste de sekmeyle
                    # AYNI sezgiselle adlandırılır, ikisi ayrışmasın.
                    "baslik": conversation_title(ref.title) or ref.title,
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
        self._restore_interrupted_turn()

    def _turn_journal(self, task: str) -> FileTurnJournal:
        """Bu konuşmanın tur günlüğü (transcript klasöründe, konuşma başına tek dosya)."""
        kimlik = _SAFE_JOURNAL_ID.sub("_", self._conversation_id or FALLBACK_CONVERSATION_ID)
        return FileTurnJournal(
            self._transcript_store.base_dir / "journals" / f"{kimlik}.json", task=task
        )

    def _restore_interrupted_turn(self) -> None:
        """Süreç tur ortasında kapandıysa o turun adımlarını geçmişe geri yükle.

        Transcript yalnız soru ve cevabı taşır; yarıda kalan turun araç adımları
        orada yoktur ve "devam et" modele hiçbir şey göstermezdi. Günlük tam
        konuşmayı taşır. Bildirim bir kez yazılır; geçmiş her açılışta yüklenir
        (yeni bir tur başlayana ya da günlük silinene kadar).
        """
        journal = self._turn_journal("")
        entry = journal.load()
        if entry is None or not entry.messages:
            return
        from ..core.turn_resume import interrupted_history

        self._state.history = interrupted_history(
            entry.messages, task=entry.task, root=str(self._state.root.resolve())
        )
        if entry.notified:
            return
        gorev = entry.task.strip()[: messages.APP_TURN_INTERRUPTED_TASK_CHARS]
        self._transcript_store.record_assistant(messages.APP_TURN_INTERRUPTED.format(gorev=gorev))
        journal.mark_notified(entry)

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
            # Önbellek kökle anahtarlı, ama eski kökün girdisi bellekte
            # kalmasın: kullanıcı projeler arasında gidip gelirken bayat bir
            # listeyle karşılaşmamalı.
            self._file_search.invalidate()
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
            mode = parse_mode(value)
            if mode is not self._state.approval:
                self._state.approval_memory.revoke()
            self._state.approval = mode
            persist_approval(self._state.config, mode)
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
            # Bağlama/çıkış öğretmen seçimini de etkiler. Dosya yazıldıktan sonra
            # tek yapılandırma kaynağından yeniden çöz.
            self._state.config = _refresh_teacher(yeni)
        return sonuc

    async def _change_web_window_mode(self, data: dict[str, Any]) -> dict[str, Any]:
        """`web.pencere_kipi`: kipi yaz; değiştiyse o sağlayıcının Chrome'unu kapat.

        Çalışan Chrome açıldığı kipte kalır; yeni kip ancak yeniden açılınca
        uygulanır. Kapatılan tarayıcı bir sonraki turda yeni kiple açılır.
        """
        from ..providers.web_browser import close_browser_session, normalize_account
        from ..providers.web_window_setting import set_window_mode

        saglayici = str(data.get("saglayici") or "")
        hesap = normalize_account(str(data.get("hesap") or "main"))
        sonuc = set_window_mode(self._state.config, saglayici, hesap, data.get("kip"))
        if sonuc.config is not None:
            self._state.config = sonuc.config
        if sonuc.is_changed:
            await close_browser_session(saglayici, hesap)
        return {
            "ok": sonuc.ok,
            "metin": sonuc.message,
            "pencere_kipi": sonuc.mode.slug if sonuc.mode is not None else None,
        }

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
            self._update_connector_config(yeni)
        return sonuc

    def _update_connector_config(self, config: Config) -> None:
        previous = {server.name: server for server in self._state.config.mcp_servers}
        current = {server.name: server for server in config.mcp_servers}
        changed = {
            name
            for name in previous.keys() | current.keys()
            if previous.get(name) != current.get(name)
        }
        for name in changed:
            self._mcp_connections.invalidate(name)
        if changed:
            self._state.approval_memory.revoke()
        self._state.config = config

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
        # Yoklama sırları ortamdan okur; bu yüzden kayıttan ÖNCE yüklenir.
        os.environ.update(secrets)
        # Ölçüldü (17 Eylül): var olmayan alan adı ve geçersiz token "eklendi"
        # oluyordu. Önce bağlanılır; yalnız çalışan ya da giriş bekleyen kaydedilir.
        yeni, sonuc = await add_connector_verified(
            self._state.config, data, probe=self._mcp_connections.verify
        )
        if yeni is None:
            for name in secrets:
                os.environ.pop(name, None)
            self._restore_connector_secrets(previous)
            return sonuc
        self._update_connector_config(yeni)
        if sonuc.get("durum") == STATE_LOGIN_REQUIRED:
            # Sunucu sağlam, yalnız OAuth girişi bekliyor: giriş penceresini
            # hemen aç ki kullanıcı ikinci bir düğmeye basmak zorunda kalmasın.
            status = self._mcp_connections.start_login(yeni.mcp_servers[-1])
            return {**sonuc, **status_payload(status), "ok": True}
        return sonuc

    async def _open_connector_panel(self, data: object) -> dict[str, Any]:
        """`baglanti.panel_ac`: sağlayıcının connector ekranını izole profilde aç.

        Giriş ve connector ekleme AYNI profilde olmak zorunda: Fusion turları o
        profili sürüyor. Başka bir tarayıcıda eklenen connector, Fusion'ın gördüğü
        oturumda görünmez.
        """
        if not isinstance(data, dict):
            return {"ok": False, "metin": "Geçersiz istek."}
        saglayici = str(data.get("saglayici", "")).strip()
        hesap = str(data.get("hesap", "") or "main").strip()
        rows = {row["id"]: row for row in hosted_provider_rows(self._state.config)}
        row = rows.get(saglayici)
        if row is None:
            return {"ok": False, "metin": "Bu sağlayıcı connector eklemeyi desteklemiyor."}
        from ..providers.web_browser import open_login_browser

        # ARKA PLANA alınır ve BEKLENMEZ. `open_login_browser` kullanıcı tarayıcıyı
        # kapatana kadar döner değil; beklenirse RPC dakikalarca açık kalır ve
        # arayüzdeki tek `busy` bayrağı bütün Bağlantılar ekranını kilitler —
        # kullanıcı donmuş sanır. `baglanti.giris` aynı sorunu `start_login` ile
        # arka plan görevine vererek çözüyor; burada da aynı desen kullanılır.
        task = self._panel_tasks.get(saglayici)
        if task is None or task.done():
            self._panel_tasks[saglayici] = asyncio.create_task(
                open_login_browser(saglayici, hesap, url=str(row["adres"]))
            )
        return {"ok": True, "adres": row["adres"]}

    def _save_theme(self, data: object) -> dict[str, Any]:
        """`ayar.tema_kaydet`: tercihi yapılandırmaya yaz.

        Hata SESSİZCE yutulmaz. Tercih eskiden webview `localStorage`'ında
        tutuluyordu ve yazma başarısız olduğunda sessizce geçiliyordu; tam bu
        sessizlik yüzünden kullanıcının seçtiği tema her açılışta unutuluyor ve
        sebebi hiçbir yerde görünmüyordu.
        """
        from dataclasses import replace as _replace

        from ..config.writer import THEME_VALUES, write_theme

        tema = str(data.get("tema", "")).strip() if isinstance(data, dict) else ""
        if tema not in THEME_VALUES:
            return {"ok": False, "metin": f"Geçersiz tema: {tema or '(boş)'}"}
        try:
            write_theme(self._state.config, tema)
        except Exception as error:
            return {"ok": False, "metin": f"Tema kaydedilemedi: {error}"}
        self._state.config = _replace(
            self._state.config, runtime=_replace(self._state.config.runtime, theme=tema)
        )
        return {"ok": True, "tema": tema}

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
            persist_engine(self._state.config, self._state.engine.value)
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
            # Sıkıştırma sürpriz olmasın: kullanıcı bağlamın dolduğunu görsün.
            "baglam": baglam_olcusu(
                self._state.history,
                budget=context_budget(
                    self._state.config,
                    select_agent_spec(self._state.config, self._state.task_type),
                ),
                last_prompt_tokens=self._usage.last_agent_prompt_tokens,
                last_prompt_model=self._usage.last_agent_model,
            ),
            # Composer'ın yanındaki sürekli-görünür rozet içindir (Faz 5,
            # Görev 1) — ikinci bir sayaç DEĞİL, `kullanim.durum`u da besleyen
            # AYNI `self._usage`'dan okunur.
            "maliyet_usd": round(self._usage.total.cost_usd, 4),
            # Kök bir proje DEPOSUYSA (Masaüstü gibi) içindeki projeler; arayüz uyarır.
            "depo": self._container_projects(),
        }

    def _container_projects(self) -> list[str]:
        """Kök birden çok proje içeriyorsa projelerin köke göreli yolları (önbellekli).

        Ölçüldü (1 Ekim olayı): Fusion `~/Desktop`'ta açıktı; "projeyi sil" bütün
        Masaüstünü hedef aldı. Kullanıcı neyin içinde çalıştığını görmeli.
        """
        root = self._state.root.resolve()
        cached = self._depo_cache
        if cached is not None and cached[0] == root:
            return cached[1]
        projects = (
            [path.relative_to(root).as_posix() for path in project_folders(root)]
            if is_container_root(root, Path.home())
            else []
        )
        self._depo_cache = (root, projects)
        return projects

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
        durum = snapshot(
            self._state.config,
            self._secret_store,
            root=str(self._state.root),
            approval=self._state.approval.value,
            engine=self._state.engine.value,
            gateway=self._gateway_status(),
        )
        durum["model"]["cirak_bildirim_goster"] = self._cirak_bildirimi_gerekli_mi()
        return durum

    def _cirak_bildirimi_gerekli_mi(self) -> bool:
        """Faz 3, Görev 2 (§6.1): web kilidiyken TEK SEFERLİK bildirim.

        `kontrol.durum` panel açılışında ilk çağrılan uçtur; agent bir web
        oturumuna kilitliyse VE bildirim daha önce hiç gösterilmediyse `True`
        döner ve işareti KALICI olarak koyar — bir daha, bu makinede hiçbir
        oturumda tekrar çıkmaz. Hiçbir arka plan kodu bunun ÖTESİNDE bir şey
        yapmaz; kullanıcı yine de mevcut web modeliyle çalışmaya devam eder.
        """
        if apprentice_active(self._state.config) or apprentice_notice_shown():
            return False
        mark_apprentice_notice_shown()
        return True

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
        previous_approval = self._state.approval
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
        if command is not None and command.name in {
            "development",
            "model",
            "level",
            "mode",
            "effort",
            "provider",
            "profiles",
        }:
            # NIM araç doğrulaması (`catalog.probe_nim_tools`) artık `run_command`'ın
            # çağırdığı `model_flows.apply_development_model` içinde TEK yerden yapılır
            # (bkz. o fonksiyonun 27 Eylül tarihli gerekçesi) — burada AYRICA
            # doğrulamak aynı canlı API çağrısını iki kez yapardı. Doğrulama ağa
            # çıkan bir çağrıdır (90s'ye kadar); bu oturumun tek event loop'unu
            # bloklamasın diye `run_command`'ın TAMAMI ayrı bir thread'de çalıştırılır
            # — eskiden yalnız doğrulama burada `asyncio.to_thread` ile sarılıyordu,
            # doğrulama aşağı taşınınca sarmalayıcı da onunla birlikte indi.
            owned = asyncio.create_task(self._apply_model_command(name, argument))
            self._model_selection_tasks.add(owned)
            owned.add_done_callback(self._model_selection_done)
            result = await asyncio.shield(owned)
        else:
            result = run_command(
                self._registry, self._state, name, argument, secret_store=self._secret_store
            )
        if self._state.approval is not previous_approval:
            self._state.approval_memory.revoke()
            persist_approval(self._state.config, self._state.approval)
        # Makrolar görevi yalnız HAZIRLAR (bkz. `cli/repl/commands.py::_macro`).
        # Terminal döngüsü hazırlanan görevi hemen çalıştırıyordu; masaüstünde bu
        # adım yoktu ve `/goal` "çalıştırılıyor…" deyip hiçbir tur başlatmıyordu.
        # Görev arayüze döner, arayüz onu normal tur olarak gönderir; kip ise o
        # tura burada taşınır.
        task, mode = self._state.take_pending()
        if not task:
            return result
        self._next_turn_mode = mode
        return {**result, "gorev": task}

    async def _apply_model_command(self, name: str, argument: str) -> dict[str, Any]:
        """Thread sona erene kadar seçim/kabul kilidi sahipliğini koru."""
        async with self._admission_lock:
            if self._closed:
                return {"ok": False, "metin": "Oturum kapandı; model seçimi uygulanmadı."}
            previous_model = self._state.config.agent.model
            result = await asyncio.to_thread(
                run_command,
                self._registry,
                self._state,
                name,
                argument,
                secret_store=self._secret_store,
            )
            if result.get("ok") is True:
                effort = self._state.config.runtime.reasoning_effort.value
                resolution = resolve_reasoning(
                    effort, capability_from_spec(self._state.config.agent)
                )
                reason = resolution.reason
                if (
                    previous_model != self._state.config.agent.model
                    and effort != "auto"
                    and resolution.applied is None
                ):
                    self._state.config = replace(
                        self._state.config,
                        runtime=replace(
                            self._state.config.runtime, reasoning_effort=ReasoningEffort.AUTO
                        ),
                    )
                    reason = f"{reason} Model değiştiği için yoğunluk auto oldu."
                    result = {**result, "metin": f"{result.get('metin', '')}\n{reason}".strip()}
                return {
                    **result,
                    "model": self._state.config.agent.model,
                    "requested_effort": effort,
                    "applied_effort": resolution.applied,
                    "effort_reason": reason,
                    "uygulama": "sonraki_tur"
                    if self._turn is not None and not self._turn.done()
                    else "hazir",
                }
            return result

    def _model_selection_done(self, task: asyncio.Task[dict[str, Any]]) -> None:
        self._model_selection_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logging.getLogger(__name__).error(
                "Model seçimi tamamlanamadı.", exc_info=task.exception()
            )

    def _command_options(self, data: dict[str, Any]) -> dict[str, Any]:
        """Sıradaki seçici/metin adımını döndür; yoksa `ok: False`."""
        name = str(data.get("ad", ""))
        argument = str(data.get("arguman", ""))
        payload = command_choices(self._state, name, argument)
        if payload is None:
            return {"ok": False, "metin": messages.APP_COMMAND_UNKNOWN}
        return {"ok": True, "secici": payload}

    async def _submit_turn(self, request: Request) -> dict[str, Any]:
        """Yanıt bekleyicisinin iptali kabul edilmiş görevi iptal etmez."""
        if self._closed:
            return {"ok": False, "metin": messages.APP_SUBMISSION_STORAGE_FAILED}
        admission = asyncio.create_task(self._admit_submission(request))
        self._admission_tasks.add(admission)
        admission.add_done_callback(self._admission_done)
        return await asyncio.shield(admission)

    def _admission_done(self, admission: asyncio.Task[dict[str, Any]]) -> None:
        self._admission_tasks.discard(admission)
        if not admission.cancelled() and admission.exception() is not None:
            logging.getLogger(__name__).error("Gönderim kabul görevi hatayla kapandı.")

    async def _admit_submission(self, request: Request) -> dict[str, Any]:
        """Kalıcı kabul, validasyon ve görev sahipliği aynı kilidi paylaşır."""
        import sqlite3

        from ..core.submission import SubmissionKey
        from .submission import receipt_payload

        key = SubmissionKey(
            str(self._state.config.memory_dir.resolve()),
            str(self._root.resolve()),
            self._conversation_id or FALLBACK_CONVERSATION_ID,
            str(request.data["gonderim_id"]),
        )
        async with self._admission_lock:
            try:
                existing = await self._submission_store.lookup(key)
                is_retry = request.data.get("yeniden_dene") is True
                if is_retry and existing is None:
                    return {"ok": False, "metin": messages.APP_SUBMISSION_MISSING}
                if existing is not None and not (
                    is_retry and existing.state.value in ("failed", "cancelled")
                ):
                    return {
                        "ok": existing.state.value
                        not in ("failed", "cancelled", "recoveryRequired"),
                        "metin": "",
                        "makbuz": receipt_payload(existing),
                    }
                task = str(request.data.get("gorev", ""))
                if not task.strip():
                    return {"ok": False, "metin": messages.RUN_EMPTY_TASK}
                attachment_context, attachment_error = _attachment_context(
                    request.data.get("ekler")
                )
                if attachment_error:
                    return {"ok": False, "metin": attachment_error}
                try:
                    voice_context = parse_voice_context(request.data.get("sesli"))
                    deadline = TurnDeadline.from_duration(request.data.get("sure_s"), SystemClock())
                except ValueError as error:
                    return {"ok": False, "metin": str(error)}
                if (self._turn is not None and not self._turn.done()) or (
                    self._submission_task is not None and not self._submission_task.done()
                ):
                    return {"ok": False, "metin": messages.APP_TURN_ALREADY_RUNNING}
                claim = await (
                    self._submission_store.retry(key)
                    if is_retry
                    else self._submission_store.claim(key)
                )
                if not claim.is_owner:
                    return {
                        "ok": False,
                        "metin": messages.APP_SUBMISSION_OBSERVATION_REQUIRED,
                        "makbuz": receipt_payload(claim.receipt),
                    }
                if self._closed:
                    await self._submission_store.finish(
                        claim.receipt, state="recoveryRequired", error_code="session_closed"
                    )
                    return {"ok": False, "metin": messages.APP_SUBMISSION_STORAGE_FAILED}
                owned = asyncio.create_task(
                    self._execute_submission(
                        claim.receipt,
                        task,
                        attachment_context,
                        _attachment_images(request.data.get("ekler")),
                        voice_context,
                        deadline,
                        self._state.config,
                    )
                )
                self._submission_task = owned
                try:
                    self._writer(
                        encode_event({"olay": "GonderimMakbuzu", **receipt_payload(claim.receipt)})
                    )
                except OSError:
                    logging.getLogger(__name__).error("Kabul makbuzu istemciye iletilemedi.")
            except (OSError, sqlite3.Error):
                return {"ok": False, "metin": messages.APP_SUBMISSION_STORAGE_FAILED}
        return await asyncio.shield(owned)

    async def _execute_submission(
        self,
        receipt: SubmissionReceipt,
        task: str,
        attachment_context: str,
        images: tuple[str, ...],
        voice_context: VoiceTurnContext | None,
        deadline: TurnDeadline | None,
        config_snapshot: Config | None = None,
    ) -> dict[str, Any]:
        """Sonuç metadata'sının sahibi transport handler değil yürütme görevidir."""
        import sqlite3

        from .submission import receipt_payload

        owned = asyncio.current_task()
        try:
            try:
                await self._submission_store.finish(receipt, state="running")
            except (OSError, sqlite3.Error):
                await self._submission_store.finish(
                    receipt, state="recoveryRequired", error_code="storage_failed"
                )
                return {"ok": False, "metin": messages.APP_SUBMISSION_STORAGE_FAILED}
            result = await self._run_turn(
                task,
                attachment_context,
                images,
                voice_context=voice_context,
                deadline=deadline,
                receipt=receipt,
                event_sequence=count(1),
                config_snapshot=config_snapshot,
            )
            state = (
                "completed"
                if result.get("ok")
                else (
                    "cancelled" if result.get("metin") == messages.APP_TURN_CANCELLED else "failed"
                )
            )
            is_retry_safe = result.pop("_retry_safe", False) is True
            terminal = await self._submission_store.finish(
                receipt,
                state=state,
                error_code=None
                if result.get("ok")
                else "no_tool_effect"
                if is_retry_safe
                else "executor_failed",
            )
            return {**result, "makbuz": receipt_payload(terminal)}
        except asyncio.CancelledError:
            await self._submission_store.finish(receipt, state="cancelled", error_code="cancelled")
            raise
        except Exception:
            logging.getLogger(__name__).error("Gönderim yürütmesi beklenmeyen hatayla bitti.")
            await self._submission_store.finish(
                receipt, state="failed", error_code="executor_failed"
            )
            raise
        finally:
            if self._submission_task is owned:
                self._submission_task = None

    async def _run_turn(
        self,
        task: str,
        attachment_context: str = "",
        images: tuple[str, ...] = (),
        *,
        voice_context: VoiceTurnContext | None = None,
        browser_only: bool = False,
        auto_continues: int = 0,
        deadline: TurnDeadline | None = None,
        receipt: SubmissionReceipt | None = None,
        event_sequence: Iterator[int] | None = None,
        config_snapshot: Config | None = None,
    ) -> dict[str, Any]:
        """Görevi agent motoruyla çalıştır; olaylar tel üzerinden akar.

        Yapılandırma ve onay modu `self._state`'TEN okunur (bkz. modül
        docstring'i): `/model` ya da `/security` gibi komutlar `self._state`i
        güncelledikten HEMEN SONRAKİ turda etkili olmalı, bir tur gecikmeli
        değil.
        """
        self._report_voice_background_failures()
        if not task.strip():
            return {"ok": False, "metin": messages.RUN_EMPTY_TASK}
        await self._iptal_edilen_turu_bekle()
        if self._turn is not None:
            return {"ok": False, "metin": messages.APP_TURN_ALREADY_RUNNING}
        from ..cli.session import open_trace, run_agent_task

        # Yan panelin konuşması uygulamanın sohbetine KARIŞMAZ: kendi geçmişi vardır,
        # diske yazılmaz, adımları ve soruları yalnız panele akar (Claude in Chrome gibi).
        if not browser_only:
            if receipt is None:
                self._transcript_store.record_user(task)
            elif receipt.attempt_id.endswith(":1") and auto_continues == 0:
                self._transcript_store.record_user(
                    task, message_id=f"{receipt.key.request_id}:user"
                )
        if voice_context is not None and not browser_only and not attachment_context and not images:
            from .voice_intents import local_voice_reply

            reply = local_voice_reply(task)
            if reply is not None:
                self._state.history = [
                    *self._state.history,
                    Message("user", task),
                    Message("assistant", reply),
                ]
                self._transcript_store.record_assistant(
                    reply, message_id=f"{receipt.key.request_id}:assistant" if receipt else None
                )
                return {"ok": True, "metin": reply, "yerel_yanit": True}
        image_command = None if browser_only else parse_image_command(task)
        if image_command is not None and not attachment_context and not images:
            ok, markdown = await run_image_command(self._state.config, image_command)
            self._state.history = [
                *self._state.history,
                Message("user", task),
                Message("assistant", markdown),
            ]
            self._transcript_store.record_assistant(
                markdown, message_id=f"{receipt.key.request_id}:assistant" if receipt else None
            )
            return {"ok": ok, "metin": markdown, "gorsel_komutu": True}
        history = self._chrome_history if browser_only else self._state.history

        # Kullanım sayacı olayları ARADAN dinler: sayaç için ayrı bir yol
        # açmak, bazı çağrı yollarının muhasebeden düşmesine yol açardı.
        writer = self._chrome.tee(_discard_line) if browser_only else self._writer
        sink = LibrarySink(
            _MeteredSink(
                ProtocolSink(writer, receipt=receipt, sequence=event_sequence), self._usage
            ),
            self._state.root,
        )
        prompter = ProtocolPrompter(
            writer,
            self.pending,
            root=self._state.root,
            element_name=self._chrome.element_name,
            namespace=receipt.attempt_id if receipt else "",
            on_closed=self._question_closed,
        )
        steering = SteeringQueue()
        child_runs = ChildRuns()
        self._child_runs = child_runs
        self._steering = steering
        self._steering_turn = receipt.attempt_id if receipt else None
        self._steering_requests.clear()
        config = config_snapshot or self._state.config
        if self._disabled_mcp:
            config = replace(
                config,
                mcp_servers=tuple(
                    server for server in config.mcp_servers if server.name not in self._disabled_mcp
                ),
            )
        capability_context = self._take_capability_context()
        selected_skill, self._taken_skill = self._taken_skill, None
        inherited_context = self._state.take_pending_digest()
        turn_mode, self._next_turn_mode = self._next_turn_mode, macros.Mode.NONE

        # Kullanıcının kalıcı talimatı da bağlama girer. Sistem istemi
        # DEĞİŞTİRİLMEZ: kimlik ve onay sözleşmesi orada durur.
        async def execute_turn() -> AgentOutcome:
            if journal is not None:
                # Çalışan tur sahipliği kurulduktan sonra I/O yap; paralel
                # istek ilk turu görünmezken ikinci bir tur başlatamasın.
                journal.save([*history, Message("user", task)])
            # Belleği okumak diske gider. Beklemeyi çalışan tur nesnesi
            # oluşturulduktan SONRA yap; aksi halde aynı anda gelen ikinci
            # istek ilk tur henüz görünmediği için üst üste başlayabilir.
            memory_block = await asyncio.to_thread(self._personal_memory.prompt_block)
            # Chrome bağlıyken tarayıcı işlerinin sınırı (bkz. `CHROME_NOTE`).
            # Köprü açıksa not verilir: eklenti o an bağlı olmasa da chrome_* Chrome'u açar.
            chrome_note = CHROME_NOTE if self._chrome.running else ""
            extra_system = "\n\n".join(
                part
                for part in (
                    chrome_note,
                    macros.mode_prompt(turn_mode),
                    inherited_context,
                    capability_context,
                    attachment_context,
                    voice_context.prompt() if voice_context else "",
                    instruction_block(),
                    memory_block,
                )
                if part
            )
            return await run_agent_task(
                task,
                config,
                remotion_transport=self._state.remotion_transport,
                remotion_browser=self._state.remotion_browser,
                require_remotion_kit=self._require_remotion_kit,
                deadline=deadline,
                sinks=(sink, self._desktop_activity, *trace_sinks),
                prompter_factory=lambda _drain: prompter,
                mode=self._state.approval,
                root=self._state.root,
                extra_roots=self._state.extra_roots,
                home=self._state.home,
                history=history,
                chrome_bridge=self._chrome,
                allowed_tools=(
                    (CHROME_CODE_TURN_TOOLS if self._workspace_mode == "kod" else CHROME_TURN_TOOLS)
                    if browser_only
                    else None
                ),
                extra_system=extra_system,
                # Görsel ekler modele GERÇEKTEN gider; yol metni ayrıca kalır.
                images=images,
                system_prompt=(
                    None if browser_only or self._workspace_mode == "kod" else CHAT_SYSTEM_PROMPT
                ),
                # Sohbet kipi çalışma alanına dokunmaz: ölçüldü, "kampanya planı
                # yap" isteği sohbette diske dosya yazıyordu (bkz. `chat_mode.py`).
                chat_mode=self._workspace_mode != "kod" and not browser_only,
                interactive=True,
                capabilities=self._state.capabilities,
                conversation_id=self._conversation_id or "app",
                step_limit=macros.mode_step_limit(turn_mode),
                workflow=macros.mode_workflow(turn_mode),
                approval_memory=self._state.approval_memory,
                steering=steering,
                child_runs=child_runs,
                selected_skill=selected_skill,
                current_approval=lambda: self._state.approval,
                # Oturumun kalıcı belleği (dersler, öğretmen planları, kod indeksi).
                # Verilmezse tur boş bellekle koşar ve hiçbir şey öğrenilmez.
                memory=self._state.memory,
                # Sekmenin sağlık kaydı: devre durumu turlar arasında yaşar.
                health=self._state.health,
                journal=journal,
                background=self._voice_background if voice_context else None,
            )

        # Tarayıcı paneli turu sekmenin konuşması değildir; günlüğe yazılmaz.
        journal = None if browser_only else self._turn_journal(task)
        # Teşhis izi: `/trace` bu turun neden düştüğünü sonradan söyleyebilsin.
        trace = None if browser_only else open_trace(config.memory_dir / "traces")
        trace_sinks: tuple[EventSink, ...] = (trace,) if trace is not None else ()
        owned_turn = asyncio.ensure_future(execute_turn())
        self._turn = owned_turn
        self._turn_settled.clear()
        try:
            outcome = await owned_turn
        except asyncio.CancelledError:
            self._iptal_bekliyor = True
            # İptal de bir sonuçtur: kaydedilmezse sekme yeniden açıldığında
            # soru cevapsız durur ve kullanıcı turun neden bittiğini göremez.
            if not browser_only:
                self._transcript_store.record_assistant(
                    messages.APP_TURN_CANCELLED,
                    message_id=f"{receipt.key.request_id}:assistant" if receipt else None,
                )
                # Durdurulan istek geçmişte kalır (Claude'daki gibi): yoksa "devam et"
                # dendiğinde model neyin yarıda kaldığını hiç görmüyordu.
                from ..core.turn_resume import interrupted_history

                entry = journal.load() if journal is not None else None
                preserved = (
                    list(entry.messages) if entry is not None else [*history, Message("user", task)]
                )
                self._state.history = interrupted_history(
                    preserved, task=task, root=str(self._state.root.resolve())
                )
                if journal is not None:
                    await await_owned_thread(journal.save, self._state.history)
            return {"ok": False, "metin": messages.APP_TURN_CANCELLED}
        finally:
            self._desktop_activity.clear()
            await child_runs.close()
            if self._turn is owned_turn:
                self._child_runs = None
                self._iptal_bekliyor = False
                self._turn = None
                self._turn_settled.set()
                self._steering = None
                self._steering_turn = None
                self._steering_requests.clear()
            if trace is not None:
                trace.close()
            # Başarısız/iptal edilmiş temizliğin araç ve soru kayıtları korunur.
        # Çok-turlu sohbet: bu turun ürettiği geçmiş bir SONRAKİ `tur.calistir`e
        # taşınsın diye durumda saklanır (bkz. `tui_loop.py:417` ile aynı desen).
        if browser_only:
            self._chrome_history = outcome.messages
            return {"ok": outcome.ok, "metin": outcome.final_text or messages.APP_TURN_NO_ANSWER}
        self._state.history = outcome.messages
        # Transcript bir BAŞARI kaydı değil, NE OLDUĞU kaydıdır.
        #
        # Ölçüldü (7 Eylül, kullanıcının Godot koşuları): plan adımı duraklayınca
        # tur `ok=False` döndü; soru diske yazıldı, cevap yazılmadı. Diskteki
        # `198b3a19…` sohbeti 8 soru ve 0 cevap taşıyor. Sekme yeniden açıldığında
        # model kendi ne dediğini göremiyor ve kaldığı yerden süremiyor — oysa
        # duraklama metni tam da devam etmek için gereken bilgidir.
        if outcome.final_text.strip():
            if receipt is None:
                self._transcript_store.record_assistant(outcome.final_text)
            else:
                self._transcript_store.record_assistant(
                    outcome.final_text, message_id=f"{receipt.key.request_id}:assistant"
                )
        # Boş metinle "başarısız" dönmek kullanıcıya hiçbir şey söylemez.
        metin = outcome.final_text
        if not metin.strip() and not outcome.ok:
            metin = (
                turn_stopped_summary(outcome.stop_reason, outcome.todos)
                if outcome.budget_stopped
                else messages.APP_TURN_NO_ANSWER
            )
            # Özet de "ne oldu" kaydıdır: sekme yeniden açıldığında "devam et"
            # turunun modeli neyin kaldığını buradan görür.
            self._transcript_store.record_assistant(
                metin, message_id=f"{receipt.key.request_id}:assistant" if receipt else None
            )
        if journal is not None:
            if outcome.ok:
                # Transcript sonucu kaydedildikten sonra tamamlanmış günlük kaldırılır.
                await await_owned_thread(journal.clear)
            else:
                preserved = list(outcome.messages)
                if metin and (not preserved or preserved[-1].content != metin):
                    preserved.append(Message("assistant", metin, harness_note=True))
                await await_owned_thread(journal.save, preserved)
        if _should_auto_continue(outcome, auto_continues) and (
            deadline is None or deadline.remaining_s() > 0
        ):
            # Uzun iş tek turun bütçesine sığmaz: gerçek değişiklik yapan ve görevi
            # bekleyen tur, kullanıcı "devam et" yazmak zorunda kalmadan sürer.
            # Geçmiş (`self._state.history`) taşındığı için model kaldığı yeri bilir.
            sink.handle(
                StatusChanged(
                    messages.APP_TURN_AUTO_CONTINUE.format(
                        n=auto_continues + 1, total=MAX_AUTO_CONTINUE_TURNS
                    )
                )
            )
            continued = await self._run_turn(
                messages.APP_TURN_AUTO_CONTINUE_TASK,
                auto_continues=auto_continues + 1,
                deadline=deadline,
                receipt=receipt,
                event_sequence=event_sequence,
                config_snapshot=config,
            )
            if receipt is not None:
                continued["_retry_safe"] = False
            return continued
        cevap: dict[str, Any] = {"ok": outcome.ok, "metin": metin}
        if receipt is not None:
            cevap["_retry_safe"] = (
                getattr(outcome, "tool_calls_made", None) == 0
                and getattr(outcome, "tool_uses", None) == ()
            )
        kanit = evidence_payload(getattr(outcome, "completion_report", None))
        if kanit is not None:
            cevap["kanit"] = kanit
        return cevap

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
        if (kind, name) not in self._pending_capabilities:
            self._pending_capabilities = [*self._pending_capabilities, (kind, name)]
        return {"ok": True, "tur": kind, "ad": name, "sonraki_tur": True}

    def _take_capability_context(self) -> str:
        self._taken_skill = None
        selected, self._pending_capabilities = self._pending_capabilities, []
        parts: list[str] = []
        for kind, name in selected:
            part = self._capability_part(kind, name)
            if part:
                parts.append(part)
        return "\n\n".join(parts)

    def _capability_part(self, kind: str, name: str) -> str:
        """Tek bir seçimin modele verilecek bağlamı; geçersizse boş."""
        if kind == "beceri":
            item = self._all_capabilities.get_skill(name)
            if item is None:
                return ""
            page = read_skill_page(item.path)
            if page.error:
                return ""
            if self._taken_skill is None:  # sayfalama izi yalnız ilk beceri için tutulur
                self._taken_skill = SkillSelection(
                    item.qualified_name, page.revision, page.next_offset
                )
            return f"# Kullanıcının açıkça seçtiği beceri: {name}\n{page.text}"
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
        self._iptal_bekliyor = True
        return {
            "ok": True,
            "state": "stopping",
            "turnId": self._steering_turn,
            "metin": "Durdurma istendi; açık işlemler kapatılıyor.",
        }

    async def _iptal_edilen_turu_bekle(self) -> None:
        """İptal edilen tur kapanana kadar kısa bir süre bekle.

        Ölçüldü (17 Eylül denetimi): tur zaman aşımına düşüp iptal edildikten
        hemen sonra gönderilen mesaj "zaten çalışan bir tur var" ile reddediliyordu.
        İptal, tarayıcı çağrısının bırakılmasıyla birkaç yüz milisaniye sürebilir;
        kullanıcıyı bu yüzden geri çevirmek yerine kısa süre beklenir.
        """
        if not self._iptal_bekliyor or self._turn is None:
            self._iptal_bekliyor = False
            return
        try:
            await asyncio.wait_for(self._turn_settled.wait(), timeout=TURN_CANCEL_SETTLE_S)
        except TimeoutError:
            return

    def resolve_reply(self, reply: Reply) -> bool:
        """Uygulamanın cevabını bekleyen soruya bağla; paneldeki kart da kapanır."""
        resolved = self.pending.resolve(reply.id, reply.data)
        if resolved and self._chrome.running:
            self._chrome.publish({"tur": "soru_kapandi", "id": reply.id})
        return resolved

    def _report_voice_background_failures(self) -> None:
        """Arka plan hatasını sır veya istem metni yazmadan görünür tut."""
        if not self._voice_background.failures:
            return
        logging.getLogger(__name__).error(
            "Sesli turun arka plan işleri tamamlanamadı.",
            extra={"failure_count": len(self._voice_background.failures)},
        )
        self._voice_background.failures.clear()

    async def _create_image_owned(self, data: dict[str, Any]) -> dict[str, Any]:
        """Doğrudan görsel RPC'si de oturum kapanışından uzun yaşayamaz."""
        if self._closed:
            return {"ok": False, "metin": "Oturum kapandı; görsel üretimi başlatılmadı."}
        task = asyncio.create_task(create_image(self._state.config, data))
        self._image_tasks.add(task)
        try:
            return await task
        finally:
            self._image_tasks.discard(task)

    async def _image_job_request(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        """İş kimliğini oturumun gerçek profil/kök/sohbet kapsamına bağla."""
        from ..config.keys import environ_snapshot
        from ..core.submission import SubmissionKey

        if self._closed or self._image_jobs is None:
            return {"ok": False, "code": "unavailable", "metin": "Görsel işi kullanılamıyor."}
        starting = name == "gorsel.is.baslat"
        listing = name == "gorsel.is.liste"
        identifier = "list" if listing else data.get("requestId" if starting else "jobId")
        if not isinstance(identifier, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", identifier
        ):
            return {"ok": False, "code": "invalid_request", "metin": "Geçersiz iş kimliği."}
        key = SubmissionKey(
            str(self._state.config.memory_dir.resolve()),
            str(self._state.root.resolve()),
            self._conversation_id or FALLBACK_CONVERSATION_ID,
            "image:" + identifier,
        )
        if listing:
            cursor, limit = data.get("sonraki", ""), data.get("limit", 20)
            if (
                set(data) - {"sonraki", "limit"}
                or not isinstance(cursor, str)
                or (cursor and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", cursor))
                or isinstance(limit, bool)
                or not isinstance(limit, int)
                or not 1 <= limit <= 50
            ):
                return {"ok": False, "code": "invalid_request", "metin": "Geçersiz iş sayfası."}
            return await self._image_jobs.list_jobs(
                key, after="image:" + cursor if cursor else "", limit=limit
            )
        if not starting:
            if set(data) != {"jobId"}:
                return {"ok": False, "code": "invalid_request", "metin": "Geçersiz iş sorgusu."}
            if name == "gorsel.is.iptal":
                return await self._image_jobs.cancel(key)
            return await self._image_jobs.status(key)
        allowed = {"requestId", "islem", "istem", "saglayici", "referans", "oran"}
        if set(data) - allowed or any(not isinstance(value, str) for value in data.values()):
            return {"ok": False, "code": "invalid_request", "metin": "Geçersiz üretim parametresi."}
        config = self._state.config
        environment = environ_snapshot()
        choices = image_providers(config, environ=environment)
        payload = {
            "islem": data.get("islem") or "uret",
            "istem": data.get("istem", "").strip(),
            "saglayici": data.get("saglayici") or (choices[0]["deger"] if choices else ""),
            "referans": data.get("referans", ""),
            "oran": data.get("oran") or "1:1",
        }
        if len(payload["istem"]) > 32768:
            return {"ok": False, "code": "invalid_request", "metin": "Görsel istemi çok uzun."}
        fingerprint_data: dict[str, object] = dict(payload)
        reference = None
        if payload["referans"]:
            from ..core.image_jobs import ImageJobConflictError

            try:
                reference = await await_owned_thread(
                    capture_reference,
                    payload["referans"],
                    image_output_dir(),
                )
            except ImageJobConflictError:
                return {
                    "ok": False,
                    "code": "invalid_request",
                    "metin": "Referans görsel doğrulanamadı.",
                }
            fingerprint_data["referansSha256"] = hashlib.sha256(reference.data).hexdigest()
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_data, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

        async def render() -> dict[str, object]:
            if reference is None:
                return await create_image(config, payload, environ=environment)
            # Dizin task başlamadan önce oluşturulur; iptal edilen disk worker'ı
            # da bitmeden context çıkmaz. Kaynak dosya artık tekrar okunmaz.
            with tempfile.TemporaryDirectory(
                prefix=".fusion-reference-", dir=image_output_dir()
            ) as temporary:
                snapshot = Path(temporary) / ("reference" + reference.suffix)
                await await_owned_thread(snapshot.write_bytes, reference.data)
                return await create_image(
                    config, {**payload, "referans": str(snapshot)}, environ=environment
                )

        return await self._image_jobs.start(key, fingerprint, render)

    async def _voice_worker(
        self, operation: Callable[[object], dict[str, Any]], value: object
    ) -> dict[str, Any]:
        """Ses dosyası kilitleri ana olay döngüsünü tutmaz; kapanış worker'ı bekler."""
        if self._closed:
            return {"ok": False, "metin": "Ses oturumu kapanıyor."}
        worker = asyncio.create_task(asyncio.to_thread(operation, value))
        self._voice_preparations.add(worker)

        def release(done: asyncio.Task[dict[str, Any]]) -> None:
            self._voice_preparations.discard(done)
            if not done.cancelled():
                done.exception()

        worker.add_done_callback(release)
        return await asyncio.shield(worker)

    async def close(self) -> None:
        """Çalışan turu ve oturuma ait bütün yardımcı süreçleri kapat."""
        from ..mcp_bridge.pool import close_mcp_pool
        from ..providers.web_browser import close_all_browser_sessions
        from ..providers.web_control import stop_all_login_processes

        self._closed = True
        if self._image_jobs is not None:
            self._image_jobs.stop_accepting()
        images = tuple(self._image_tasks)
        for image in images:
            if not image.done() and not image.cancelling():
                image.cancel()
        selections = tuple(self._model_selection_tasks)
        if selections:
            await asyncio.gather(*selections, return_exceptions=True)
        admissions = tuple(self._admission_tasks)
        for admission in admissions:
            admission.cancel()
        if admissions:
            await asyncio.gather(*admissions, return_exceptions=True)
        self._admission_tasks.difference_update(admissions)
        if self._turn is not None and not self._turn.done():
            self._turn.cancel()
        submission = self._submission_task
        if submission is not None:
            if self._turn is None:
                submission.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await submission
        await self._voice_background.close()
        self._report_voice_background_failures()
        if self._voice_preparations:
            await asyncio.gather(*self._voice_preparations, return_exceptions=True)
            self._voice_preparations.clear()
        voice_stop()
        discard_prepared_voice()
        if images:
            await asyncio.gather(*images, return_exceptions=True)
        if self._image_jobs is not None:
            await self._image_jobs.close()
        await self._submission_store.close()
        for task in self._panel_tasks.values():
            if not task.done():
                task.cancel()
        self._panel_tasks.clear()
        await close_mcp_pool()
        await self._mcp_connections.close()
        await self._chrome.close()
        await self._processes.close()
        await close_all_browser_sessions()
        stop_all_login_processes()
        if self._remote is not None:
            await self._remote.aclose()
        self.pending.cancel_all()

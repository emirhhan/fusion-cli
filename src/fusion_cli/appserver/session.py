"""Oturum istekleri, kabul edilmiş turlar ve görünür sohbetin yaşam döngüsü.

Komutlar görünür `ReplState` durumunu günceller. Yeni bir tur kabul edilirken kök,
sohbet, yapılandırma, geçmiş ve bekleyen girdiler ilk asenkron beklemeden önce alınır.
Araçlar, günlük ve sonuç bu kabul sahibine bağlı kalır; sekme değişimi çalışan turun
bağlamını değiştirmez. Açık canlı izin değişiklikleri yalnız aynı sahipte uygulanır.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import inspect
import json
import logging
import os
import re
import shlex
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from functools import partial
from itertools import count
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ..cli.repl import code_review_findings, cron_store, goal_flow, goal_store, linked_pr, macros
from ..cli.repl.agent_link import close_link
from ..cli.repl.commands import attach_skill_commands, build_registry, renders_itself
from ..cli.repl.loop_command import fire_prompt, runs_as_command
from ..cli.repl.persona_commands import persona_turn, resolve_session_persona
from ..cli.repl.skill_commands import GROUP as SKILL_GROUP
from ..cli.repl.skill_commands import model_override_allowed
from ..cli.repl.state import Engine, ReplState
from ..cli.repl.task_list import session_todos
from ..cli.repl.transcript_store import (
    TranscriptStore,
    _workspace_digest,
    delete_conversation,
    list_conversations,
    load_transcript_messages,
    move_conversation,
    validate_conversation_move,
)
from ..config.agent_launch_compat import reload_agent_launch
from ..config.apprentice_notice import apprentice_notice_shown, mark_apprentice_notice_shown
from ..config.browser_profiles import default_browser_profile_store
from ..config.credentials import FernetSecretStore
from ..config.eligibility import capability_from_spec
from ..config.keys import secret_key
from ..config.loader import load_config
from ..config.model_select import select_agent_spec
from ..config.models import Config, McpServerConfig, mcp_secret_env_names
from ..config.paths import credentials_file
from ..config.permission_rules import PermissionRuleSet
from ..config.permission_settings import auto_mode_disabled
from ..config.permissions import load_allowed_commands
from ..core.changeset import ChangeSet
from ..core.claude_chrome_names import CLAUDE_CHROME_TOOL_NAMES
from ..core.clock import SystemClock
from ..core.concurrency import BackgroundTasks
from ..core.constants import MODEL_SELECTION_CLOSE_WAIT_S
from ..core.errors import ConfigError
from ..core.events import Event, EventSink, StatusChanged, ToolExecuted, ToolStarted
from ..core.owned_thread import await_owned_thread
from ..core.plan_switch import PlanModeSwitch
from ..core.reasoning import ReasoningEffort, resolve_reasoning
from ..core.redaction import redact
from ..core.remotion_browser import RemotionBrowser
from ..core.session_cron import CronTask, SessionCron
from ..core.skill_context import SkillSelection
from ..core.steering import SteeringQueue
from ..core.submission import SubmissionKey, SubmissionReceipt, SubmissionRepository
from ..core.tools import TodoStatus
from ..core.turn_deadline import TurnDeadline
from ..core.types import Message
from ..core.worktree import WorktreeSwitch, worktree_for_path
from ..engines.agent.approval import ApprovalMode, parse_mode
from ..engines.agent.child_runs import ChildRuns
from ..engines.agent.context_budget import context_budget
from ..engines.agent.loop import CHAT_SYSTEM_PROMPT, AgentOutcome
from ..engines.agent.remotion_bridge import FrameTransport
from ..engines.agent.skill_turn import resolve_turn_model
from ..engines.agent.team_fork import run_forked_turn
from ..engines.retention import purge_local_state_daily
from ..mcp_bridge.failures import STATE_LOGIN_REQUIRED
from ..memory.factory import build_memory
from ..memory.turn_journal import FileTurnJournal, JournalEntry
from ..memory.turn_journal_codec import message_to
from ..observability.usage_log import UsageLog, new_session_id, open_usage_log
from ..providers.capabilities import apprentice_active
from ..providers.health_setup import build_health
from ..remote.controller import RemoteController
from ..tools.bundled_plugins import team_role_hint
from ..tools.capabilities import Capability, CapabilityRegistry, load_agent_prompt
from ..tools.capability_overrides import registry_from_config
from ..tools.safe_delete import is_container_root, project_folders
from ..tools.skill_commands import map_denied_tools
from ..tools.skill_pages import read_skill_page
from ..ui import messages
from ..ui.permission_dialog_messages import AUTO_MODE_SETTING_DISABLED
from ..ui.text import strip_thinking
from ..ui.turn_stop import turn_stopped_summary
from . import auto_memory, computer_routes, intelligence, pr_archive, ui_prefs
from .background_routes import BACKGROUND_ROUTES, dispatch_background
from .background_wake import BACKGROUND_WAKE_ID, background_wake_tasks
from .bridges import PendingQuestions, ProtocolPrompter, ProtocolSink, Writer
from .browser_panel import RPC_PREFIX as BROWSER_PANEL_RPC
from .browser_panel import BrowserPanel
from .bypass_policy import bypass_policy_disabled
from .capabilities import catalog, detail
from .chrome_autoinstall import auto_install_async
from .chrome_bridge import ChromeBridge
from .chrome_group import schedule_group_close
from .chrome_install import install_status
from .chrome_settings import CHROME_SETTINGS_ROUTES, dispatch_chrome_settings
from .commands import (
    command_choices,
    list_commands,
    render_command_text,
    run_command,
    select_development_model,
)
from .computer_activity import ComputerActivityWatch
from .computer_routes import COMPUTER_ROUTES
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
from .daemon_thread import run_in_daemon_thread
from .delivery_presentation import present_delivery
from .desktop_activity import DesktopActivity
from .desktop_dock import DesktopDock
from .desktop_permission_routes import (
    DESKTOP_PERMISSION_ROUTES,
    DesktopPermissionWatch,
    dispatch_desktop_permission,
)
from .desktop_routes import DESKTOP_ROUTES, dispatch_desktop
from .extension_routes import EXTENSION_ROUTES, ExtensionContext, dispatch_extension
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
from .hooks_routes import HOOK_ROUTES, dispatch_hooks
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
from .instructions import (
    get_instructions,
    instruction_block,
    save_instructions,
    set_external_imports,
)
from .keybindings_rpc import KEYBINDING_ROUTES
from .kits_browser_routes import (
    KITS_BROWSER_DESCRIBE_ROUTE,
    KITS_BROWSER_ROUTES,
    describe_kits_browser,
    dispatch_kits_browser,
)
from .kits_routes import KITS_ROUTES, dispatch_kits
from .library import LibrarySink, add_upload, remove_entry
from .local_computer import LocalComputer, native_local_computer
from .local_computer_routes import LOCAL_COMPUTER_ROUTES, dispatch_local_computer
from .mcp_catalog import list_tool_catalog, pin_tools_digest
from .mcp_project_routes import MCP_PROJECT_ROUTES, dispatch_mcp_project
from .model_catalog import list_selectable_models
from .orchestration_routes import ORCHESTRATION_ROUTES, dispatch_orchestration
from .personal_memory import PersonalMemory
from .plan_routes import plan_accept, plan_card_payload
from .processes import ProcessManager
from .project_status import git_status, suggested_commands
from .protocol import Reply, Request, encode_event, encode_result
from .visible_transcript import (
    VisibleToolRecorder,
    load_visible_transcript,
    project_visible_history,
)

if TYPE_CHECKING:
    from ..cli.repl.prefixes import ShellPrefixResult
    from ..engines.hooks.session import HookSession
from .runtime_prefs import persist_approval, persist_engine
from .sandbox_rpc import SANDBOX_ROUTES, dispatch_sandbox
from .schedule import SCHEDULE_ROUTES
from .side_chat import SIDE_CHAT_ROUTE, ask_side
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
from .wake import WakeDesk
from .workspace import (
    WorkspaceJournal,
    list_changes,
    list_entries,
    preview_entry,
    read_entry,
    record_agent_changes,
    undo_entry,
    workspace_status,
    write_entry,
)

#: Chrome bağlıyken ajana verilen tarayıcı ilkesi. Ölçüldü (26 Eylül, Google Ads):
#: model hesap seçim ekranında durup "hesap seçmemi ister misin?" diye sordu; salt
#: okuma görevinde görevde adı geçen ya da tek uygun hesabı seçmek beklenen adımdır.
CHROME_NOTE = (
    "Bu bir tarayıcı ajanı görevidir: 'siteye gir', 'kayıt ol', 'formu doldur', 'sayfadan çıkar', "
    "'hesabımı incele' gibi isteklerde HEMEN navigate ile siteyi kullanıcının "
    "Chrome'unda aç, read_page/find ile oku, computer ile tıkla, yaz, kaydır. Sunucu "
    "tarafında sayfa getirme ya da arama aracı YOKTUR ve kullanıcının girişli oturumunu "
    "görmez; adres bilinmiyorsa Chrome'da arama sitesini aç. Çift tıklama, sağ tıklama, "
    "sürükleme ve kaydırma computer'ın double_click, right_click, left_click_drag ve scroll "
    "eylemleridir. İzin kartı açıldıysa kullanıcıya söyle ve onay gelene kadar bekle. "
    "Kullanıcı AÇIKÇA dosya, kod ya da proje isterse çalışma alanı araçlarını kullan; "
    "aksi halde iş tarayıcıdadır. "
    "İnternet sitelerindeki işler (Google Ads, Instagram, Meta, mağaza paneli, herhangi bir "
    "site) kullanıcının kendi Chrome'unda claude-in-chrome araçlarıyla yapılır; "
    "Chrome kapalıysa Fusion "
    "onu kendisi açar. browser_* ayrı ve oturumsuz bir tarayıcıdır, yalnız yerel projeyi "
    "(localhost) denemek içindir; orada giriş sayfası görmen oturumun kapalı olduğu anlamına "
    "gelmez. Tarayıcı işlerinde okuma için gereken ara adımları (hesap veya "
    "sayfa seçimi, sekme açma, 'daha fazla göster', kaydırma) kendin yap: görevde adı geçen "
    "ya da tek uygun seçeneği seç. Yalnız giriş/şifre, ödeme ve gönderme/yayınlama/silme "
    "adımlarında dur. Sayfa gerçekten giriş istiyorsa bunu açıkça söyle. Yeni sayfada önce "
    "read_page ile sayfayı oku; adresi biliyorsan menüde arama yerine "
    "doğrudan git. Uzun sayfanın metni için get_page_text; ref'i olmayan "
    "öğede computer screenshot alıp left_click coordinate [x,y] kullan. "
    "Tanıtım ya da giriş sayfasına düşersen "
    "hemen 'oturum kapalı' deme: önce "
    "tabs_context_mcp ile açık sekmelere bak, sonra sitenin uygulama adresini dene "
    "(ör. Google Ads: "
    "ads.google.com/aw/overview); oturumun kapalı olduğunu ancak giriş formunu görünce söyle. "
    "Kullanıcı bir siteden component alıp projeye uygulamanı isterse önce sayfayı Chrome "
    "eklentisiyle incele, sonra çalışma alanındaki dosyaları okuyup düzenle ve sonucu "
    "doğrula. Uygulama yolunda somut bir belirsizlik veya tekrarlanan hata varsa "
    "ask_teacher ile tek net soru sor; yanıtı değerlendirip işe devam et. "
    # P-042/P-043/P-044: geliştirici araçları. Model bunları bilmezse hata ayıklama
    # isteğinde ekran görüntüsüyle tahmin yürütür.
    "Sayfa hatası ya da istek sorunu araştırırken read_console_messages (onlyErrors) ve "
    "read_network_requests (urlPattern) kullan; sayfanın yapısı için read_page "
    "filter=interactive. Kullanıcı kayıt/GIF isterse gif_creator start_recording … "
    "stop_recording."
)

CHROME_TURN_TOOLS = {
    # Claude in Chrome adları (#431); eski `chrome_*` adları gizli takma ad olarak çalışır.
    *CLAUDE_CHROME_TOOL_NAMES,
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
    # Gerçek araç adı `search_code`dir (`tools/builtin.py`); eski "grep" adında araç yok, bu yüzden
    # kod kipindeki panel turu kod araması yapamıyordu (ölçüldü 30 Ekim).
    "search_code",
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


def findings_payload(text: str) -> dict[str, Any]:
    """`/code-review` cevabındaki bulgu bloğu: temiz metin + `bulgular`; blok yoksa boş."""
    extracted = code_review_findings.extract(text)
    if extracted is None:
        return {}
    return {"metin": extracted.text, "bulgular": [dict(item) for item in extracted.findings]}


def _attachment_images(value: object) -> tuple[str, ...]:
    """Validate and read attachments through the shared bounded adapter."""
    from .attachments import attachment_images

    return attachment_images(value)


async def _attachment_images_async(value: object) -> tuple[str, ...]:
    """Ek yoksa thread'e geçmeden `()` döner; varsa diski olay döngüsü dışında okur.

    Ek olmayan yaygın durumda ek bir `await` noktası açmak, turun başlangıcını geciktirip
    hemen ardından gelen `tur.kes`in turu bulamamasına yol açıyordu.
    """
    if not isinstance(value, list) or not value:
        return ()
    return await asyncio.to_thread(_attachment_images, value)


def _attachment_context(value: object) -> tuple[str, str | None]:
    """Validate all attachments before admitting a turn."""
    from .attachments import attachment_context

    return attachment_context(value)


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


class _RetryEffectSink:
    """Conservative retry evidence; unknown tools require observation."""

    # Only fixed local readers are eligible. Shell, browser, MCP and dynamic tools
    # remain unsafe even when a particular invocation looks read-only.
    READERS = frozenset({"read_file", "list_dir", "search_code"})

    def __init__(self, inner: EventSink) -> None:
        self.inner = inner
        self.safe = True

    def handle(self, event: Event) -> None:
        if isinstance(event, (ToolStarted, ToolExecuted)) and (
            event.name not in self.READERS
            or (isinstance(event, ToolExecuted) and event.mutating is True)
        ):
            self.safe = False
        self.inner.handle(event)

    def permits_retry(
        self, entry: JournalEntry | None, prefix: tuple[dict[str, object], ...]
    ) -> bool:
        """Require the original attempt boundary and every observed/durable effect."""
        if not self.safe or entry is None:
            return False
        durable_prefix = tuple(
            message_to(message, include_images=True) for message in entry.messages[: len(prefix)]
        )
        return durable_prefix == prefix and all(
            call.name in self.READERS
            for message in entry.messages[len(prefix) :]
            for call in message.tool_calls
        )


class _MeteredSink:
    """Olayları yazan sink'i sarar ve tüketimi sayar.

    Sarmalama, sayacın olay akışının TAM ÜSTÜNDE durmasını sağlar: yeni bir
    çağrı yolu eklendiğinde sayaç kendiliğinden görür.
    """

    def __init__(
        self, inner: EventSink, meter: UsageMeter, usage_log: UsageLog | None = None
    ) -> None:
        self._inner = inner
        self._meter = meter
        self._usage_log = usage_log

    def handle(self, event: Event) -> None:
        self._meter.observe(event)
        if self._usage_log is not None:
            self._usage_log.handle(event)
        self._inner.handle(event)


#: Sekme kimliği bildirilmeden yazılan turların gideceği sohbet.
#
# Uygulamanın ön yüzü ilk sekmesini bu kimlikle açar; ikisi aynı olmazsa açılış
# turu ile sekmenin geçmişi ayrışır.
FALLBACK_CONVERSATION_ID = "varsayilan"


@dataclass(frozen=True)
class _DeliveryOwner:
    store: TranscriptStore
    key: SubmissionKey
    store_id: str
    generation: int

    def valid(self) -> bool:
        return (
            self.store.root == Path(self.key.root)
            and self.store.base_dir
            == Path(self.key.profile_id) / "transcripts" / _workspace_digest(Path(self.key.root))
            and self.store.session_id == self.store_id
        )


@dataclass(frozen=True)
class _AcceptedTurn:
    """Execution inputs belong to acceptance, independently of the visible chat."""

    state: ReplState
    visible_state: ReplState
    store: TranscriptStore
    conversation_id: str
    generation: int
    workspace_mode: str
    personal_memory: PersonalMemory
    disabled_mcp: frozenset[str]
    pending_capabilities: tuple[tuple[str, str], ...]
    catalogue: CapabilityRegistry
    next_mode: macros.Mode
    goal_continuation: str | None
    fork_requested: bool
    approval_revision: int
    approval_mode: ApprovalMode
    workspace_journal: WorkspaceJournal
    hook_source: HookSession | None
    approval_scopes: frozenset[str]


def export_payload(history: list[Message], data: dict[str, Any]) -> dict[str, Any]:
    """`sohbet.disa_aktar {bicim: markdown|json, baslik}` → maskeli dışa aktarım metni."""
    from ..core.transcript_export import default_export_name, export_json, export_markdown

    bicim = str(data.get("bicim") or "markdown").lower()
    if bicim not in ("markdown", "json"):
        return {"ok": False, "metin": "Biçim 'markdown' ya da 'json' olmalı."}
    baslik = data.get("baslik")
    title = baslik.strip() if isinstance(baslik, str) and baslik.strip() else "Fusion sohbeti"
    as_json = bicim == "json"
    text = export_json(history, title=title) if as_json else export_markdown(history, title=title)
    return {"ok": True, "metin": text, "dosya_adi": default_export_name(as_json=as_json)}


def _title_payload(message: object) -> dict[str, Any]:
    """`sohbet.baslik`: ilk mesajdan başlık. Model çağrılmaz (bkz. `conversation_title`)."""
    if not isinstance(message, str):
        return {"ok": False, "metin": "Başlık için mesaj metni zorunludur."}
    return {"ok": True, "baslik": conversation_title(message)}


def _log_purge_failure(task: asyncio.Future[Any]) -> None:
    """Arka plan temizliğinin hatası yutulmaz ama turu da bozmaz."""
    if not task.cancelled() and task.exception() is not None:
        logging.getLogger(__name__).warning("Yerel durum temizliği başarısız: %s", task.exception())


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
        # Süreç cwd'si proje kökü olmayabilir: ajan ayarları verilen kökten okunur.
        config = reload_agent_launch(load_config(), home=home, root=root, environ=os.environ)
        self._secret_store = FernetSecretStore(credentials_file(), secret_key=secret_key())
        # Ajan tarayıcısı profilleri (P-023/P-024); sır deposuyla aynı ana anahtar.
        self._browser_profiles = default_browser_profile_store()
        # Uygulama içi Tarayıcı paneli (P-045): ajanla paylaşılan tarayıcının sahibi.
        self._browser_panel = BrowserPanel(
            config=lambda: self._state.config,
            root=lambda: self._state.root,
            turn_running=lambda: self._turn is not None and not self._turn.done(),
            store=lambda: self._browser_profiles,
            save_agent_share=self._save_panel_agent,
        )
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
        #: Tur bitince modele gitmemiş yönlendirmeler (#190): arayüz bunları hemen sıradaki
        #: tur olarak yollar (Claude Code "queued messages go out without another key press").
        self._steering_leftover: list[str] = []
        self._registry = build_registry(home)
        # Beceri/komut dosyaları `/ad` olarak (P-019); defter sahteleri eski imzayı korur.
        attach_skill_commands(self._registry, lambda: self._state.capabilities)
        self._state = ReplState.from_runtime_config(
            config,
            memory=build_memory(config, root=root),
            root=root,
            home=home,
            health=build_health(config),
            remotion_transport=remotion_transport,
            remotion_browser=remotion_browser,
        )
        # Masaüstü bulgu listesi isteyen ana uygulamadır (Claude Code ReportFindings, #214).
        self._state.findings_host = True
        #: Uygulamanın sekmesine karşılık gelen konuşma kimliği. `oturum.baslat`
        #: ile gelir; gelmeden önce okuma proje genelini gösterir.
        self._conversation_id: str | None = None
        #: Son `cron.vadesi_gelenler` ile verilen görevin ilerletilmeden önceki hâli.
        self._cron_given: dict[str, CronTask] = {}
        #: Son verilen görevin istem metni; ilk `komut.calistir` bir kez tüketir (#141).
        self._cron_fire_prompt = ""
        #: Boştaki sohbeti uyandıran turlar; gönderilemeyen geri verilir (#123).
        self._wake = WakeDesk()
        #: (kök, depo projeleri) — durum her turdan sonra sorulduğu için önbellekli.
        self._depo_cache: tuple[Path, list[str]] | None = None
        #: İptal edilen turun kapanması bekleniyor mu?
        self._iptal_bekliyor = False
        #: Saklama temizliği bu süreçte çalıştı mı (bkz. `_purge_old_local_state`).
        self._local_state_purged = False
        self._local_state_purge_task: asyncio.Future[Any] | None = None
        self._child_runs = self._state.child_runs
        # Karttan auto'ya geçiş (#82) arayüzün kip rozetine bildirilir.
        self._state.on_mode_change = lambda mode: self._writer(
            encode_event({"olay": "IzinKipiDegisti", "mod": mode.value})
        )
        self._state.history = load_transcript_messages(config.memory_dir, root)
        # YAZMA kimliği asla rastgele olmaz. Ölçüldü (kullanıcının diski, 7 Eylül):
        # kimliksiz açılan depo her seferinde `session-<zaman>-<rastgele>` üretti ve
        # o konuşmalara bir daha ulaşılamadı — 110 sohbetin çoğu böyle orphan kaldı.
        # Sekme kimliği gelene kadar yazılanlar, ulaşılabilir tek bir sohbette durur.
        self._transcript_store = TranscriptStore(
            config.memory_dir, root, conversation_id=FALLBACK_CONVERSATION_ID
        )
        self._visible_generation = 0
        self._active_accepted: _AcceptedTurn | None = None
        self._hook_lease: _AcceptedTurn | None = None
        self._visible_history_imported = False
        #: "sohbet" ya da "kod". Varsayılan artık KOD (Faz 5, Görev 5 — "tek
        #: kutu"): arayüzdeki manuel kip düğmesi kaldırıldı, kullanıcı artık
        #: hiçbir seçim yapmıyor. Eski gerekçe ("merhaba"da proje taranmasın)
        #: geçerliliğini KORUYOR ama artık bir DEĞİŞ TOKUŞ: basit bir selamda
        #: bile proje köküne bağlanılır. Mekanizmanın kendisi (`_apply_
        #: workspace_mode`, `chat_mode`) SİLİNMEDİ — yalnızca varsayılan
        #: değişti; programatik istemciler hâlâ `kip: "sohbet"` gönderebilir.
        self._workspace_mode = "kod"
        self._workspace_journal = WorkspaceJournal()
        self._processes = ProcessManager(
            self._state.root,
            writer,
            hidden_env=lambda: mcp_secret_env_names(self._state.config.mcp_servers),
        )
        #: `@` ile dosya anmanın kısa ömürlü dosya listesi önbelleği.
        self._file_search = FileSearchIndex()
        self._gateway_process_id: str | None = None
        executable = shlex.quote(sys.executable)
        self._gateway_command = (
            f"{executable} serve --host 127.0.0.1 --port 8787"
            if getattr(sys, "frozen", False)
            else f"{executable} -m fusion_cli serve --host 127.0.0.1 --port 8787"
        )
        self._all_capabilities = CapabilityRegistry(
            home,
            root,
            managed_roots=tuple(Path(value) for value in config.agent_launch.managed_agent_roots),
            working_directory=root,
            extra_agent_sources=getattr(config.agent_launch, "extra_agent_sources", True),
        )
        self._disabled_skills: set[str] = set()
        self._disabled_agents: set[str] = set()
        self._disabled_mcp: set[str] = set()
        # Kullanıcının bu tur için seçtiği beceri/ajan/MCP'ler (örn. `/beceri` + `@mcp`).
        self._pending_capabilities: list[tuple[str, str]] = []
        self._taken_skill: SkillSelection | None = None
        self._refresh_capabilities()
        if config.agent_launch.default_agent:
            self._apply_persona(config.agent_launch.default_agent)
        self._usage = UsageMeter()
        #: Kalıcı kullanım günlüğü (P-056); ayar kapalıysa None. Oturum sayacı değişmez.
        self._usage_log = open_usage_log(self._state.config, session_id=new_session_id("masaustu"))
        #: Yan panelin kendi konuşma geçmişi (uygulamanın sohbetinden ayrı).
        self._chrome_history: list[Message] = []
        self._chrome_turn_id: str | None = None
        self._chrome = ChromeBridge(
            self._chrome_turn,
            self._chrome_cancel,
            self._chrome_answer,
            self._chrome_settings,
            installer=auto_install_async,
            extension_installed=lambda: bool(install_status()["eklenti_yuklu"]),
        )
        self._desktop_dock = DesktopDock(chrome=self._chrome)
        self._desktop_activity = DesktopActivity()
        self._desktop_permissions = DesktopPermissionWatch(
            lambda payload: self._writer(encode_event(payload))
        )
        # "Fusion bilgisayarı kullanıyor · Esc ile durdur" şeridi (P-033).
        self._computer_activity = ComputerActivityWatch(
            lambda payload: self._writer(encode_event(payload)),
            lambda: self._state.config.desktop,
        )
        from ..mcp_bridge.service import McpConnectionService

        self._mcp_connections = McpConnectionService()
        # Claude: kimlik doğrulama başarıyla bitince `Notification(auth_success)` (#125).
        self._mcp_connections.on_login_success = lambda server: _notify_auth(self, server)
        from .accounts import AccountService

        #: Hesap uçları. Depo hesaptan BAĞIMSIZ bir dosyadadır; etkin hesap
        #: süreç açılışında zaten seçilmiştir (bkz. `cli` giriş noktası).
        self._accounts = AccountService()
        #: Sağlayıcı connector panelini açan arka plan görevleri (sağlayıcı → görev).
        #: Pencere kullanıcı kapatana kadar yaşar; RPC onu beklemez.
        self._panel_tasks: dict[str, asyncio.Task[None]] = {}
        self._voice_background = BackgroundTasks()
        #: Kalıcı yazması başarısız olan ayarların kullanıcıya gösterilecek uyarısı.
        self._persist_warnings: list[str] = []
        self._turn: asyncio.Task[Any] | None = None
        #: `Notification(idle_prompt)` gözcüsü (P-009); ilk turda kurulur, kapanışta iptal.
        self._idle_watch: asyncio.Future[None] | None = None
        self._turn_settled = asyncio.Event()
        self._turn_settled.set()
        #: Bir makronun (`/goal` …) bir SONRAKİ tura taşıyacağı davranış kipi.
        self._next_turn_mode = macros.Mode.NONE
        #: Tur sonu `/goal` değerlendirmesi (P-058); `tur.kes` onu da durdurur.
        self._goal_task: asyncio.Task[goal_flow.GoalOutcome | None] | None = None
        #: Son değerlendirmenin ürettiği devam görevi: hedef kipi YALNIZ bu metinle gelen
        #: tura uygulanır, ilgisiz sonraki mesaja sızmaz.
        self._goal_continuation: str | None = None
        self._goal_turn_id: str | None = None
        #: Seçilen beceri `context: fork` istedi (P-054): sonraki tur fork alt ajanda koşar.
        self._fork_requested = False

    async def handle(self, request: Request) -> None:
        """İsteği çalıştır ve sonucunu yaz. İstisna sızdırmaz."""
        try:
            data = await self._dispatch(request)
        except Exception as error:  # istek sınırı: süreç çökmemeli
            # Ham istisna metni dosya yolu/URL/token parçası taşıyabilir: maskelenip gösterilir,
            # tür ve istek adı günlüğe yazılır (ölçüldü 30 Ekim: ne maske ne iz vardı).
            logging.getLogger(__name__).error(
                "İstek işlenemedi (%s): %s", request.name, type(error).__name__
            )
            data = {"ok": False, "metin": redact(str(error)[:2_000])}
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

    async def _chrome_turn(self, prompt: str, turn_id: str | None = None) -> dict[str, Any]:
        """Execute only admitted panel work; terminal events share its owner."""
        owner = turn_id or f"chrome:{uuid4().hex}"
        try:
            result = await self._run_turn(prompt, browser_only=True, chrome_turn_id=owner)
        except (Exception, asyncio.CancelledError):
            if self._chrome_turn_id == owner:
                self._chrome.publish(
                    {
                        "tur": "bitti",
                        "turnId": owner,
                        "ok": False,
                        "metin": messages.APP_TURN_NO_ANSWER,
                    }
                )
                self._chrome_turn_id = None
            raise
        result.pop("_retry_safe", None)
        result.pop("_cancelled", None)
        answer = result.get("metin")
        if isinstance(answer, str):
            result["metin"] = strip_thinking(answer).strip()
        if self._chrome_turn_id == owner:
            self._chrome.publish({"tur": "bitti", "turnId": owner, **result})
            self._chrome_turn_id = None
        if turn_id is not None:
            result["turnId"] = owner
        return result

    def _chrome_cancel(self, turn_id: str | None = None) -> dict[str, Any]:
        # Old panels without ownership can still run tasks but must reconnect to
        # the current protocol before stopping one; never stop native work.
        if not turn_id or turn_id != self._chrome_turn_id:
            return {"ok": False, "metin": "Durdurma isteği etkin panel göreviyle eşleşmiyor."}
        return self._cancel_turn()

    async def _chrome_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        """Yan panelin model seçici ve "Önce sor / Sormadan yap" anahtarı.

        Claude in Chrome'daki gibi panel modeli ve izin kipini kendisi seçer. Model
        masaüstündeki `model.sec` ile (eski `/development uygula` ile aynı uygulayıcı) değişir.
        """
        if data.get("izinler") is True or "izin_sil" in data:
            from .site_permissions import site_permission_settings

            accepted = self._active_accepted
            owns_visible = accepted is not None and self._same_accepted_chat(accepted)
            memory = (
                accepted.state.approval_memory
                if accepted is not None and owns_visible
                else self._state.approval_memory
            )
            result = await site_permission_settings(memory, data.get("izin_sil"))
            if (
                owns_visible
                and accepted is not None
                and self._same_accepted_chat(accepted)
                and isinstance(data.get("izin_sil"), str)
                and result.get("ok")
            ):
                self._state.approval_memory.forget(data["izin_sil"])
            self._sync_active_approval()
            return result
        if data.get("yeni") is True:
            # Paneldeki "temizle": yeni panel konuşması, uygulamanın sohbeti etkilenmez.
            if self._turn is not None and not self._turn.done():
                return {"ok": False, "metin": "Görev sürerken yeni sohbet açılamaz."}
            self._chrome_history = []
        mode = data.get("mod")
        if mode is not None:
            # Hiçbir şey sorulmayan kip tek istekle açılmaz: panel kullanıcıya sorup onayı
            # `bypass_onay: true` ile taşır (masaüstü arayüzündeki "İzinleri atla" onayıyla aynı).
            if (
                mode == ApprovalMode.BYPASS.value
                and self._state.approval is not ApprovalMode.BYPASS
                and data.get("bypass_onay") is not True
            ):
                return {
                    "ok": False,
                    "onay_gerekli": ApprovalMode.BYPASS.value,
                    "metin": messages.CHROME_BYPASS_CONFIRM_REQUIRED,
                }
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
            # Yapısal yol: kimlik komut dizgesine gömülmez (U1-40).
            result = await self._select_model({"kaynak": source, "model": model})
            if result.get("ok") is False:
                return result
        catalog = await list_selectable_models(self._state.config, workspace_mode="sohbet")
        return {
            "ok": True,
            "model": self._state.config.agent.model,
            "mod": self._state.approval.value,
            "modeller": catalog.get("modeller", []),
            **self._take_persist_warning(),
        }

    def _start_local_state_purge(self, memory_dir: Path) -> None:
        """30 günden eski iz/artifact/tamamlanmış checkpoint'leri süreç başına BİR kez temizle.

        Arka planda çalışır (turun ilk `await`ini ertelemez: tur kaydı ondan önce yapılmalı) ve
        günde bir damga dosyasıyla da sınırlıdır; hata turu engellemez (L1-30, M1-44).
        """
        if self._local_state_purged:
            return
        self._local_state_purged = True
        task = asyncio.ensure_future(
            asyncio.to_thread(purge_local_state_daily, memory_dir, now=time.time())
        )
        self._local_state_purge_task = task
        task.add_done_callback(_log_purge_failure)

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
            # `assign` config'i okuyup `await`ten sonra geri atar; kilitsizken aradaki başka
            # bir RPC'nin config değişikliği ezilirdi (kayıp güncelleme, ölçüldü 30 Ekim).
            "model.rol_ata",
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
            runs = self._child_runs
            expected = (
                runs.turn_for(identifier)
                if runs is not None and isinstance(identifier, str)
                else ""
            )
            if not expected and runs is not None and not runs.persistent:
                expected = self._steering_turn or ""
            if (
                runs is None
                or not expected
                or request.data.get("turnId") != expected
                or not isinstance(identifier, str)
            ):
                return {"ok": False, "metin": "Etkin alt ajan görevi bulunamadı."}
            cancelled = await runs.cancel(identifier)
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
        if request.name in MCP_PROJECT_ROUTES:
            # Proje `.mcp.json` sunucu onayı (#246): REPL istemiyle aynı kayıt.
            result, updated = dispatch_mcp_project(
                request.name, request.data, self._state.root, self._state.config
            )
            if updated is not None:
                self._state.config = updated
            return result
        if request.name in ORCHESTRATION_ROUTES:
            # Ekip panosu (P-061) ve iş akışı koşuları (P-062): araçlarla aynı depolar.
            return await dispatch_orchestration(request.name, request.data, self._state.root)
        if request.name in EXTENSION_ROUTES:
            # Eklentiler, içe aktarma, sürüm notları (P-059, P-071): `extension_routes`.
            return await self._extension_rpc(request.name, request.data)
        if request.name in KITS_ROUTES:
            # Fusion → Kit gelen kutusu (P-063); araçlarla aynı istemci.
            return await dispatch_kits(request.name, request.data)
        if request.name in KITS_BROWSER_ROUTES:
            # Kit → kullanıcının Chrome'u (P-063): onay host'ta (kitsBrowserHost) alınır;
            # burada dar eylem kümesi, adres kapısı, `runtime.disabled_tools` kapısı ve
            # metin-sadece sonuç uygulanır. `kit_tarif` onay penceresine hedefi verir.
            kapali = self._state.config.runtime.disabled_tools
            if request.name == KITS_BROWSER_DESCRIBE_ROUTE:
                return await describe_kits_browser(request.data, self._chrome, disabled=kapali)
            return await dispatch_kits_browser(request.data, self._chrome, disabled=kapali)
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
        if request.name in BACKGROUND_ROUTES:
            return dispatch_background(
                self._state, request.name, request.data, turn_owner=self._conversation_id or "app"
            )
        if request.name in KEYBINDING_ROUTES:
            return KEYBINDING_ROUTES[request.name](request.data)
        if request.name == "kitaplik.liste":
            from .asset_bridge import catalogued_library

            return await await_owned_thread(
                catalogued_library, request.data, self._state.config.memory_dir
            )
        if request.name == "kitaplik.ekle":
            return add_upload(request.data)
        if request.name == "kitaplik.kaldir":
            return remove_entry(request.data)
        if request.name in HOOK_ROUTES:
            return dispatch_hooks(request.name, self._state, request.data)
        if request.name in SANDBOX_ROUTES:
            # Ayarlar › İzinler › Sandbox (P-010); değişiklik sonraki turda uygulanır.
            yeni, sonuc = dispatch_sandbox(
                request.name, request.data, self._state.config, self._state.root
            )
            if yeni is not None:
                self._state.config = yeni
            return sonuc
        if request.name in DESKTOP_PERMISSION_ROUTES:
            # Sistem istemi bloklayıcıdır (TCC penceresi); olay döngüsü dışında.
            return await asyncio.to_thread(dispatch_desktop_permission, request.name, request.data)
        if request.name in DESKTOP_ROUTES:
            return await dispatch_desktop(
                self._desktop_dock, self._desktop_activity, request.name, request.data
            )
        if request.name == SIDE_CHAT_ROUTE:
            # Yan sohbet (#444): ana geçmişi okur, değiştirmez; araç yok.
            return await ask_side(self._state.config, list(self._state.history), request.data)
        if request.name == "chrome.baslat":
            return {"ok": True, **await self._chrome.start()}
        if request.name in CHROME_SETTINGS_ROUTES:
            # Ayarlar → Tarayıcı: izleme anahtarı ve kısayollar eklentinin deposunda yaşar.
            return await dispatch_chrome_settings(self._chrome, request.name, request.data)
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
            previous = (self._state.root, self._state.conversation_id)
            result = self._start_session(request.data)
            if result.get("ok") and previous != (self._state.root, self._state.conversation_id):
                # Sohbetten çıkış: computer use kilidi o sohbetinse kalkar (#429).
                from ..cli.session import conversation_job_scope
                from ..tools.desktop_turn import end_session

                if previous[1]:
                    end_session(conversation_job_scope(self._state.config.memory_dir, previous[1]))
                if self._active_accepted is not None or self._admission_tasks:
                    # The accepted turn owns the old scope until it settles.
                    self._state.child_runs = ChildRuns(persistent=True)
                    from ..core.background_events import BackgroundEvents

                    self._state.background_events = BackgroundEvents()
                else:
                    await self._state.reset_child_runs()
                self._child_runs = self._state.child_runs
            if result.get("ok"):
                from ..engines.hooks.opening import open_soon

                open_soon(self._state.hooks())  # SessionStart arka planda (#111)
            return result
        if request.name == "oturum.durum":
            return self._status()
        if request.name == "oturum.gecmis":
            store, generation = self._transcript_store, self._visible_generation
            loader = (
                project_visible_history
                if self._visible_history_imported
                else load_visible_transcript
            )
            history = await asyncio.to_thread(loader, store, tuple(self._state.history))
            if store is not self._transcript_store or generation != self._visible_generation:
                return {"ok": False, "metin": "Sohbet değişti; geçmişi yeniden yükleyin."}
            return {
                "ok": True,
                "mesajlar": history.rows,
                **({"gecmis_kirpildi": True} if history.truncated else {}),
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
        if request.name == "sohbet.adlandir":
            return await self._rename_conversation(request.data)
        if request.name == "sohbet.pr_durumlari":
            # Claude Desktop "Auto-archive after PR merge or close" (#443): kenar çubuğu sorar.
            ids = request.data.get("sohbetler")
            states = await asyncio.to_thread(
                pr_archive.pr_states,
                self._state.config.memory_dir,
                ids if isinstance(ids, list) else [],
            )
            return {"ok": True, "durumlar": states}
        if request.name == "sohbet.baslik":
            return _title_payload(request.data.get("metin"))
        if request.name == "sohbet.disa_aktar":
            # P-028: masaüstü ShareDialog ile REPL /export aynı üreticiyi kullanır.
            return export_payload(list(self._state.history), request.data)
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
                # Imported context replaces the current view, rather than mixing
                # the previous conversation's persisted tool rows into it.
                self._visible_generation += 1
                self._visible_history_imported = True
                self._transcript_store.record_visible_clear()
                self._state.pending_digest = prepared.digest
                # Kullanıcının kendi devralma eylemi, o oturumun klasörlerine açık izindir.
                self._state.extra_roots = tuple(
                    dict.fromkeys((*self._state.extra_roots, *prepared.work_dirs))
                )
                self._refresh_capabilities()
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
            return await await_owned_thread(
                read_entry, self._state.root, request.data, self._workspace_journal
            )
        if request.name == "proje.onizle":
            return preview_entry(self._state.root, request.data)
        if request.name == "web.onizleme_dogrula":
            from .web_preview import validate_web_preview

            return await asyncio.to_thread(validate_web_preview, request.data)
        if request.name.startswith("onizleme."):
            # Önizleme paneli (P-041): launch.json sunucuları, konsol/ağ günlüğü, ekran görüntüsü.
            from .preview_rpc import handle_preview_rpc

            return await handle_preview_rpc(self._state.root, request.name, request.data)
        if request.name == "proje.yaz":
            return write_entry(self._state.root, request.data, self._workspace_journal)
        if request.name == "proje.degisiklikler":
            # Senkron `git` çağrıları thread'de: olay döngüsünde koşarsa RPC ve onaylar donar.
            return await await_owned_thread(list_changes, self._state.root, self._workspace_journal)
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
            return await await_owned_thread(git_status, self._state.root)
        if request.name == "yetenek.katalog":
            return catalog(
                self._catalog_registry(),
                self._state.config,
                self._state.root,
                disabled_skills=self._disabled_skills,
                disabled_agents=self._disabled_agents,
                disabled_mcp=self._disabled_mcp,
                home=self._home,
            )
        if request.name == "yetenek.detay":
            return detail(
                self._catalog_registry(),
                self._state.config,
                self._state.root,
                request.data,
                home=self._home,
            )
        if request.name == "yetenek.bellek_sil":
            from .capabilities import clear_agent_memory

            return clear_agent_memory(
                self._all_capabilities, self._state.config, self._state.root, request.data
            )
        if request.name == "yetenek.etkinlik":
            return self._set_capability_enabled(request.data)
        if request.name == "yetenek.kullan":
            return self._select_capability(request.data)
        if request.name == "yetenek.yenile":
            return self._reload_capabilities()
        if request.name == "yetenek.teshis":
            return self._diagnose_capabilities()
        if request.name == "yetenek.gorunurluk_listesi":
            from .skill_visibility_rpc import list_skill_visibility

            return list_skill_visibility(self._state)
        if request.name == "yetenek.gorunurluk":
            # `/skills` paneli (#176): görünürlük `skillOverrides`'a yazılır, katalog yenilenir.
            from .skill_visibility_rpc import set_skill_visibility

            sonuc = set_skill_visibility(self._state, request.data)
            if sonuc.get("ok"):
                self._refresh_capabilities()
            return sonuc
        if request.name == "kontrol.durum":
            return self._control_status()
        if request.name.startswith("izin.") or request.name.startswith("proje.guven_"):
            return self._permissions_rpc(request)
        if request.name.startswith("oto."):
            # Otomatik kip denetçisi (P-011); bkz. `auto_review_rpc`.
            from .auto_review_rpc import handle as auto_review_rpc

            return auto_review_rpc(self._state, request)
        if request.name == "kontrol.cirak_bildirimi_goruldu":
            return self._ack_apprentice_notice()
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
            nesil = request.data.get("nesil")  # Nesilsiz istek eski sözleşmeyle çalışır.
            hazirla = prepare_voice if nesil is None else lambda m: prepare_voice(m, nesil)
            return await self._voice_worker(hazirla, request.data.get("metin"))
        if request.name == "ses.haziri_cal":
            nesil = request.data.get("nesil")
            cal = play_prepared_voice if nesil is None else lambda h: play_prepared_voice(h, nesil)
            return await self._voice_worker(cal, request.data.get("hazir_id"))
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
            return usage_status(
                self._usage,
                self._state.health,
                self._state.config.runtime.rate_limit_per_minute,
                usage_log=self._usage_log,
            )
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
            return get_instructions(self._state.root, self._home)
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
        if request.name == "ayar.dis_import_karari":
            return set_external_imports(self._state.root, dict(request.data))
        if request.name == "baglanti.guven":
            # Güvenilir kararında araç tanımı özeti ağdan okunur; tur denetiminden ÖNCE, böylece
            # beklerken başlayan bir tur güven sınırını değiştirmeden yakalanır.
            review = dict(request.data)
            pinned = self._connector(review.get("ad")) if review.get("guven") == "trusted" else None
            if pinned is not None:
                review["arac_ozeti"] = await pin_tools_digest(pinned)
            if (self._turn is not None and not self._turn.done()) or (
                self._submission_task is not None and not self._submission_task.done()
            ):
                return {
                    "ok": False,
                    "metin": "Güven sınırını değiştirmeden önce çalışan görevi durdur.",
                }
            updated, result = review_connector(self._state.config, review)
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
            result = await list_tool_catalog(server, rules=self._catalog_rules())
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
        if request.name == "baglanti.yeniden_baglan":
            # Claude Code `/mcp reconnect <sunucu>|all` (P-049): havuzdaki bağlantı düşürülür,
            # park kaydı silinir, yeniden yoklanır.
            wanted = str(request.data.get("ad", "")).strip()
            targets = [
                server
                for server in self._state.config.mcp_servers
                if wanted in ("", "all") or server.name == wanted
            ]
            if not targets:
                return {"ok": False, "metin": "Bağlantı bulunamadı."}
            statuses = [
                status_payload(await self._mcp_connections.reconnect(server)) for server in targets
            ]
            ok = all(item["ok"] for item in statuses)
            names = ", ".join(server.name for server in targets)
            metin = (
                messages.CONNECTOR_RECONNECTED if ok else messages.CONNECTOR_RECONNECT_FAILED
            ).format(names=names)
            return {"ok": ok, "sunucular": statuses, "metin": metin}
        if request.name == "baglanti.sil":
            server = self._connector(request.data.get("ad"))
            if server is not None:
                await self._mcp_connections.logout(server)
            return self._change_connectors(
                partial(remove_connector, root=self._state.root), request.data
            )
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
            # Ölçüm yalnız web oturumlarını değiştirdi: yalnız onlar diskten alınır. Tüm
            # yapılandırmayı yeniden okumak `/model` ile seçilmiş, yazılmamış model ve
            # kademeyi sessizce geri alırdı (bkz. `_refresh_teacher`).
            if olcum.get("ok"):
                self._state.config = replace(
                    self._state.config,
                    web_sessions=load_config(self._state.config.source).web_sessions,
                )
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
        if request.name.startswith("tarayici."):
            return await self._browser_profile_rpc(request)
        if request.name.startswith(BROWSER_PANEL_RPC):
            return await self._browser_panel.handle(request.name, request.data)
        if request.name in COMPUTER_ROUTES:
            return await self._computer_rpc(request)
        if request.name == "komut.listele":
            return {"ok": True, "komutlar": list_commands(self._registry)}
        if request.name == "cron.listele":
            return self._cron_list()
        if request.name == "cron.sil":
            return self._cron_delete(request.data)
        if request.name == "cron.vadesi_gelenler":
            return self._cron_due()
        if request.name == "cron.geri_ver":
            return self._cron_give_back(request.data)
        if request.name == "plan.kart":
            return plan_card_payload(self._state)
        if request.name == "plan.kabul":
            return plan_accept(self._state, request.data)
        if request.name == "komut.calistir":
            return await self._run_command(request.data)
        if request.name == "komut.secenekler":
            return await self._command_options(request.data)
        if request.name == "model.sec":
            return await self._select_model(request.data)
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
        if request.name == "otobellek.durum":
            return await asyncio.to_thread(auto_memory.status, self._state)
        if request.name == "otobellek.kaydet":
            return await asyncio.to_thread(auto_memory.save_index, self._state, request.data)
        if request.name == "otobellek.etkinlestir":
            return await asyncio.to_thread(auto_memory.set_enabled, self._state, request.data)
        if request.name == "otobellek.ice_aktar":
            return await asyncio.to_thread(auto_memory.import_external, self._state, request.data)
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
            try:
                attachment_images = await _attachment_images_async(request.data.get("ekler"))
            except ValueError as error:
                return {"ok": False, "metin": str(error)}
            direct = await self._run_turn(
                str(request.data.get("gorev", "")),
                attachment_context,
                attachment_images,
                voice_context=voice_context,
                deadline=deadline,
            )
            direct.pop("_retry_safe", None)
            direct.pop("_cancelled", None)  # makbuzsuz yolda iç işaret tele çıkmaz
            return self._with_steering_leftover(direct)
        if request.name == "tur.kes":
            owner = self._goal_turn_id if self._goal_judging() else self._steering_turn
            if "turnId" in request.data and (
                not isinstance(request.data["turnId"], str)
                or not owner
                or request.data["turnId"] != owner
            ):
                return {"ok": False, "metin": "Durdurma isteği etkin görevle eşleşmiyor."}
            # Requests without turnId retain the explicit legacy stop-current behavior.
            if self._goal_judging():
                assert self._goal_task is not None
                self._goal_task.cancel()
                return {"ok": True, "state": "stopping", "metin": messages.GOAL_STOPPED}
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
        linked_pr.save(self._state.config.memory_dir, conversation_id, None)
        await self._submission_store.delete_conversation(
            str(self._state.config.memory_dir.resolve()),
            str(root),
            conversation_id,
        )
        if root == current_root and conversation_id == self._transcript_store.session_id:
            self._visible_generation += 1
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
                    # Kullanıcının verdiği ad (`sohbet.adlandir`, CLI `/rename`) başlığı ezer.
                    "baslik": ref.name or conversation_title(ref.title) or ref.title,
                    "ad": ref.name,
                    "guncelleme": ref.updated_at,
                    "mesaj_sayisi": ref.message_count,
                }
                for ref in list_conversations(self._state.config.memory_dir, self._root)
            ],
        }

    async def _rename_conversation(self, data: dict[str, Any]) -> dict[str, Any]:
        """`sohbet.adlandir {sohbet_id?, ad}`: sohbete kalıcı ad ver; CLI `/rename` ile aynı kayıt.

        Ad transcript'e olay olarak yazılır; `sohbet.listele` ve `fusion --resume <ad>`
        aynı adı görür. Kimlik verilmezse açık sekmenin sohbeti adlandırılır.
        """
        name = data.get("ad")
        if not isinstance(name, str) or not name.strip():
            return {"ok": False, "metin": messages.SESSION_RENAME_USAGE}
        conversation_value = data.get("sohbet_id")
        conversation_id = (
            conversation_value.strip()
            if isinstance(conversation_value, str) and conversation_value.strip()
            else self._conversation_id or FALLBACK_CONVERSATION_ID
        )
        store = TranscriptStore(
            self._state.config.memory_dir, self._root, conversation_id=conversation_id
        )
        await asyncio.to_thread(store.record_name, name.strip())
        if conversation_id == self._state.conversation_id:
            self._state.conversation_name = name.strip()
        return {"ok": True, "sohbet_id": conversation_id, "ad": name.strip()}

    def _rebind_transcript(self) -> None:
        """Transcript deposunu güncel kök ve konuşma kimliğine bağla.

        Okuma ve yazma TEK yerden bağlanır; ayrı ayrı bağlanırsa biri kimliği
        alıp öteki almadığında sekme yazdığını geri okuyamaz.
        """
        self._visible_generation += 1
        if self._active_accepted is not None or self._admission_tasks:
            # A pending/accepted turn retains its live hook object. The new
            # visible chat must not restart or mutate that object's lifecycle.
            self._state.hook_session = None
        # Pending inputs belong to the conversation being left. An accepted
        # job already holds its own copy; the new chat starts without them.
        self._state.take_pending_extras()
        self._state.take_pending_digest()
        self._pending_capabilities = []
        self._next_turn_mode = macros.Mode.NONE
        self._goal_continuation = None
        self._fork_requested = False
        self._visible_history_imported = False
        self._state.history = load_transcript_messages(
            self._state.config.memory_dir, self._root, conversation_id=self._conversation_id
        )
        self._transcript_store = TranscriptStore(
            self._state.config.memory_dir, self._root, conversation_id=self._conversation_id
        )
        # Slash komutları (`/rename`) ve tur checkpoint'leri sekmenin kimliğini görsün;
        # yoksa `ReplState` açılışta ürettiği rastgele kimlikte kalırdı.
        self._state.conversation_id = self._transcript_store.session_id
        # Sekmenin `/goal` hedefi sohbetle birlikte geri gelir (P-058).
        self._state.goal = goal_store.load(
            self._state.config.memory_dir, self._state.conversation_id
        )
        # Başka sekmenin tur kayıtları ve PR künyesi bu konuşmaya ait değildir.
        self._state.checkpoints.clear()
        linked_pr.restore(self._state)
        self._restore_interrupted_turn()

    def _restore_session_agent(self) -> None:
        """Sohbetin oturum ajanını geri yükle (#16); kaydı olmayan sohbette `agent` ayarı.

        Claude Code'daki gibi sürdürülen oturum seçildiği ajanla açılır; ajan artık yoksa
        uyarı düşülür ve varsayılan araçlarla devam edilir.
        """
        from ..cli.repl import session_agent

        name = session_agent.load(self._state.config.memory_dir, self._state.conversation_id)
        wanted = name or self._state.config.agent_launch.default_agent
        current = self._state.persona.name if self._state.persona is not None else ""
        if wanted == current:
            return
        error = self._apply_persona(wanted)
        if error is not None:
            self._state.select_persona(None)
            self._note_persist_warning(messages.SESSION_AGENT_MISSING.format(name=wanted))

    def _turn_journal(self, task: str, *, accepted: _AcceptedTurn | None = None) -> FileTurnJournal:
        """Bu konuşmanın tur günlüğü (transcript klasöründe, konuşma başına tek dosya)."""
        conversation = accepted.conversation_id if accepted else self._conversation_id
        store = accepted.store if accepted else self._transcript_store
        kimlik = _SAFE_JOURNAL_ID.sub("_", conversation or FALLBACK_CONVERSATION_ID)
        return FileTurnJournal(
            store.base_dir / "journals" / f"{kimlik}.json",
            task=task,
            original_owner_id=kimlik,
        )

    def _restore_interrupted_turn(self) -> None:
        """Süreç tur ortasında kapandıysa o turun adımlarını geçmişe geri yükle.

        Transcript yalnız soru ve cevabı taşır; yarıda kalan turun araç adımları
        orada yoktur ve "devam et" modele hiçbir şey göstermezdi. Günlük tam
        konuşmayı taşır. Bildirim bir kez yazılır; geçmiş her açılışta yüklenir
        (yeni bir tur başlayana ya da günlük silinene kadar).
        """
        accepted = self._active_accepted
        if accepted is not None and self._same_accepted_chat(accepted):
            return
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
        new_root, root_error = self._validated_root(root_value)
        if root_error is not None:
            return root_error
        capability_roots_changed = False
        # Sohbet kimliği kökten ÖNCE okunur: kök de değişiyorsa transcript yeniden
        # bağlanırken doğru kimliğe bağlanmalı, yoksa sekme bir tur boyunca proje
        # genelini gösterir.
        sohbet_value = data.get("sohbet_id")
        conversation_changed = False
        if isinstance(sohbet_value, str) and sohbet_value.strip():
            yeni_kimlik = sohbet_value.strip()
            onceki_kimlik = self._conversation_id
            conversation_changed = yeni_kimlik != self._conversation_id
            self._conversation_id = yeni_kimlik
            if conversation_changed:
                # Süresi dolmamış zamanlanmış görevler aynı sekmeyle geri gelir (P-038).
                # Kimliksiz ("app") kurulan görevler yeni kimliğe taşınır; ölçüldü (31 Ekim):
                # load ile değiştirilip düşüyordu.
                memory_dir = self._state.config.memory_dir
                loaded = cron_store.load(memory_dir, yeni_kimlik)
                if onceki_kimlik is None and len(self._state.cron):
                    loaded = self._state.cron.merged(loaded)
                    cron_store.save(memory_dir, "app", SessionCron())
                self._state.cron = loaded
                self._cron_given = {}
                cron_store.save(memory_dir, yeni_kimlik, loaded)
        if new_root is not None:
            self._apply_root(new_root)
            capability_roots_changed = True
        transcript_rebound = capability_roots_changed or conversation_changed
        if transcript_rebound:
            self._rebind_transcript()
        if conversation_changed:
            # Oturum değişti (Claude: /resume): grup yalnız boş yeni sekmelerdense kapanır (#436).
            schedule_group_close(self._chrome, only_empty=True)
        home_value = data.get("ev")
        if isinstance(home_value, str) and home_value:
            self._home = Path(home_value)
            self._state.home = self._home
            capability_roots_changed = True
        if capability_roots_changed:
            # Yeni projenin `.claude/settings.json` ajan ayarları (agent, env.CLAUDE_CODE_*).
            self._state.config = reload_agent_launch(
                self._state.config, home=self._home, root=self._root, environ=os.environ
            )
            self._all_capabilities = CapabilityRegistry(
                self._home,
                self._root,
                managed_roots=tuple(
                    Path(value) for value in self._state.config.agent_launch.managed_agent_roots
                ),
                working_directory=self._root,
                extra_agent_sources=getattr(
                    self._state.config.agent_launch, "extra_agent_sources", True
                ),
            )
            self._disabled_skills.clear()
            self._disabled_agents.clear()
            self._disabled_mcp.clear()
            self._refresh_capabilities()
        if transcript_rebound and "kisilik" not in data:
            # Katalog yeni köke göre kurulduktan SONRA: proje ajanı doğru kökten çözülür.
            self._restore_session_agent()
        # `mod_kalici: false` = bu oturuma özgü geçici mod (zamanlanmış görev, U5-57): kullanıcının
        # kalıcı varsayılan izin modu config'e yazılıp değiştirilmez.
        mode_error = self._apply_mode(data.get("mod"), persist=data.get("mod_kalici") is not False)
        if mode_error is not None:
            return mode_error
        calisma_error = self._apply_workspace_mode(data.get("kip"))
        if calisma_error is not None:
            return calisma_error
        engine_error = self._apply_engine(data.get("motor"))
        if engine_error is not None:
            return engine_error
        persona_error = self._apply_persona(data.get("kisilik"))
        if persona_error is not None:
            return persona_error
        return {**self._status(), **self._take_persist_warning()}

    def _apply_persona(self, value: object) -> dict[str, Any] | None:
        """`kisilik`: ajan adı oturum kişiliği olur (P-053), `""` kapatır, yok = dokunma."""
        if value is None:
            return None
        if not isinstance(value, str):
            return {"ok": False, "metin": "Kişilik bir ajan adı ya da boş metin olmalı."}
        if not value.strip():
            self._state.select_persona(None)
            return None
        persona = resolve_session_persona(self._all_capabilities, value)
        if persona is None:
            unknown = messages.PERSONA_UNKNOWN.format(name=value.strip())
            return {"ok": False, "metin": unknown + team_role_hint(value.strip())}
        try:
            self._state.select_persona(persona)
        except ConfigError as error:
            return {"ok": False, "metin": str(error)}
        return None

    def _validated_root(self, value: object) -> tuple[Path | None, dict[str, Any] | None]:
        """`oturum.baslat{kok}`: mutlak, var olan bir dizin; tur sürerken değişmez.

        Doğrulanmayan kök sonraki dosya/git/terminal işlerini göreli ya da yanlış dizine
        bağlardı; tur sürerken kök değişince çalışan araçlar yeni kökte devam ederdi.
        """
        if not isinstance(value, str) or not value:
            return None, None
        candidate = Path(value).expanduser()
        if not candidate.is_absolute() or not candidate.is_dir():
            return None, {"ok": False, "metin": f"Proje kökü geçerli bir klasör değil: {value}"}
        try:
            changed = candidate.resolve() != self._root.resolve()
        except OSError:
            changed = True
        if changed and self._turn is not None and not self._turn.done():
            return None, {"ok": False, "metin": "Tur sürerken proje kökü değiştirilemez."}
        return candidate, None

    def _apply_mode(self, value: str | None, *, persist: bool = True) -> dict[str, Any] | None:
        if not isinstance(value, str) or not value:
            return None
        if (auto_error := self._auto_mode_refusal(value)) is not None:
            return auto_error
        try:
            mode = parse_mode(value)
        except ValueError:
            valid = ", ".join(mode.value for mode in ApprovalMode)
            return {
                "ok": False,
                "metin": messages.RUN_UNKNOWN_MODE.format(given=value, valid=valid),
            }
        if (
            mode is ApprovalMode.BYPASS
            and self._state.approval is not ApprovalMode.BYPASS
            and bypass_policy_disabled(self._state.root, self._state.home)
        ):
            # Claude: `disableBypassPermissionsMode: "disable"` (kurum politikası) kapatır (#442).
            return {"ok": False, "metin": messages.BYPASS_POLICY_DISABLED}
        if mode is not self._state.approval:
            self._state.approval_memory.revoke()
        self._state.approval = mode
        self._sync_active_approval(explicit_mode=mode)
        if persist:
            self._note_persist_warning(persist_approval(self._state.config, mode))
        return None

    def _auto_mode_refusal(self, value: str) -> dict[str, Any] | None:
        """Claude (#85): `disableAutoMode: "disable"` olan oturumda auto seçilemez."""
        if value.strip().lower() != ApprovalMode.AUTO.value:
            return None
        if self._state.approval is ApprovalMode.AUTO or not auto_mode_disabled(self._state.root):
            return None
        return {"ok": False, "metin": AUTO_MODE_SETTING_DISABLED}

    def _note_persist_warning(self, warning: str | None) -> None:
        """Kalıcı yazma uyarısını sonraki yanıta taşımak üzere sakla.

        Ölçüldü (30 Ekim): `persist_*` hata METNİ döndürüyor ama üç çağrı yeri onu yok sayıyordu;
        kayıt başarısızken kullanıcı "kaydedildi" sanıyor, yeniden açılışta seçim kayboluyordu.
        """
        if warning:
            self._persist_warnings.append(warning)

    def _take_persist_warning(self) -> dict[str, str]:
        warnings, self._persist_warnings = self._persist_warnings, []
        return {"uyari": " ".join(warnings)} if warnings else {}

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

    async def _save_panel_agent(self, value: bool) -> str:
        """Tarayıcı panelindeki paylaşım seçimini `browser.panel_agent`'a yaz; hata metni."""
        sonuc = await self._browser_profile_rpc(
            Request(id="", name="tarayici.ayar", data={"anahtar": "panel_agent", "deger": value})
        )
        return "" if sonuc.get("ok") else str(sonuc.get("metin") or "Ayar yazılamadı.")

    async def _deny_desktop_app(self, app: str, *, accepted: _AcceptedTurn | None = None) -> None:
        """Onay kartındaki "Her zaman reddet" (P-007): `desktop.denied_apps`'e yaz ve uygula."""
        state = accepted.state if accepted is not None else self._state
        sonuc, guncel = await asyncio.to_thread(computer_routes.deny_app, state.config, app)
        if not sonuc.get("ok"):
            logging.getLogger(__name__).warning(
                "Reddedilen uygulama kaydedilemedi: %s", sonuc.get("metin")
            )
        state.config = replace(state.config, desktop=guncel.desktop)
        if accepted is not None and self._accepted_is_visible(accepted):
            self._state.config = replace(self._state.config, desktop=guncel.desktop)

    async def _computer_rpc(self, request: Request) -> dict[str, Any]:
        """`bilgisayar.*` (P-006): yazma dosyaya gider; oturum yalnız `desktop:`'u günceller."""
        sonuc, guncel = await asyncio.to_thread(
            computer_routes.dispatch, self._state.config, request.name, request.data
        )
        self._state.config = replace(self._state.config, desktop=guncel.desktop)
        return sonuc

    async def _browser_profile_rpc(self, request: Request) -> dict[str, Any]:
        """`tarayici.*` (P-024): dosya/Chrome okuma ve şifreleme bloklar, thread'e alınır."""
        from . import browser_profiles as rpc
        from .kits_profile_routes import KITS_PROFILE_ROUTES, dispatch_kits_profile

        store = self._browser_profiles
        data = request.data
        if request.name == "tarayici.profiller":
            return await asyncio.to_thread(rpc.list_profiles, store, self._state.config)
        if request.name == "tarayici.dosya_onizle":
            return await asyncio.to_thread(rpc.preview_file, data)
        if request.name == "tarayici.chrome_profilleri":
            return await asyncio.to_thread(rpc.chrome_profiles, data)
        if request.name == "tarayici.ice_aktar":
            return await asyncio.to_thread(rpc.import_profile, store, data)
        if request.name == "tarayici.sil":
            return await asyncio.to_thread(rpc.delete_profile, store, data)
        if request.name in KITS_PROFILE_ROUTES:
            # Kit tarayıcısına profil (P-023): onay hostta; yanıt yalnız o iframe'e gider.
            return await asyncio.to_thread(
                dispatch_kits_profile, request.name, store, self._state.config, data
            )
        if request.name == "tarayici.web_oturumlari":
            return await asyncio.to_thread(rpc.web_sessions, data)
        if request.name == "tarayici.web_oturumu_aktar":
            return await rpc.import_from_web_session(store, data)
        if request.name == "tarayici.giris":
            return rpc.start_login(data)
        if request.name == "tarayici.giris_durumu":
            return web_login_state(data.get("pid"))
        if request.name == "tarayici.varsayilan":
            sonuc = await asyncio.to_thread(rpc.set_default, self._state.config, data, store)
            if sonuc.get("ok"):
                # Yalnız `browser.default_profile` güncellenir; `/model` ile seçilmiş, yazılmamış
                # model geri alınmaz (bkz. `web.arac_olc` ile aynı gerekçe).
                self._state.config = replace(
                    self._state.config,
                    browser=replace(
                        self._state.config.browser, default_profile=str(sonuc["varsayilan"])
                    ),
                )
            return sonuc
        if request.name == "tarayici.ayar":
            sonuc = await asyncio.to_thread(rpc.set_setting, self._state.config, data)
            if sonuc.get("ok"):
                tarayici = self._state.config.browser
                deger = bool(sonuc["deger"])
                anahtar = sonuc["anahtar"]
                # Anahtar `browser_profiles._BOOL_SETTINGS` içindedir (headless, profiles_enabled,
                # panel_agent, tools #439).
                yeni_tarayici = replace(tarayici, **{str(anahtar): deger})  # type: ignore[arg-type]
                self._state.config = replace(self._state.config, browser=yeni_tarayici)
            return sonuc
        return {"ok": False, "metin": f"Bilinmeyen tarayıcı isteği: {request.name}"}

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

    def _catalog_rules(self) -> PermissionRuleSet | None:
        """Araç kataloğunda izin durumu için güncel kurallar (#250); okunamazsa None."""
        reader = getattr(self._state, "permission_rules", None)
        if not callable(reader):
            return None
        try:
            rules = reader()
        except Exception as error:  # katalog bir görünüm; kural hatası onu düşürmez
            logging.getLogger(__name__).info(
                "izin kuralları katalog için okunamadı: %s", type(error).__name__
            )
            return None
        return rules if isinstance(rules, PermissionRuleSet) else None

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
        # Yoklama sırları ortamdan okur; bu yüzden kayıttan ÖNCE yüklenir. Başarısızlıkta
        # eski değer geri konur (ölçüldü 30 Ekim: `pop` ortamda önceden var olan sırrı siliyordu).
        env_previous = {name: os.environ.get(name) for name in secrets}
        os.environ.update(secrets)
        # Ölçüldü (17 Eylül): var olmayan alan adı ve geçersiz token "eklendi"
        # oluyordu. Önce bağlanılır; yalnız çalışan ya da giriş bekleyen kaydedilir.
        yeni, sonuc = await add_connector_verified(
            self._state.config, data, probe=self._mcp_connections.verify
        )
        if yeni is None:
            for name, old_value in env_previous.items():
                if old_value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = old_value
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
            panel = asyncio.create_task(open_login_browser(saglayici, hesap, url=str(row["adres"])))
            self._panel_tasks[saglayici] = panel
            panel.add_done_callback(partial(self._panel_task_done, saglayici))
        return {"ok": True, "adres": row["adres"]}

    def _panel_task_done(self, provider: str, task: asyncio.Task[Any]) -> None:
        """Panel görevi bitince kaydı düşür ve istisnayı oku ("never retrieved" olmasın)."""
        if self._panel_tasks.get(provider) is task:
            del self._panel_tasks[provider]
        if not task.cancelled() and task.exception() is not None:
            logging.getLogger(__name__).error(
                "Connector paneli hatayla kapandı (%s): %s",
                provider,
                type(task.exception()).__name__,
            )

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
            engine = Engine(value)
        except ValueError:
            valid = ", ".join(engine.value for engine in Engine)
            return {
                "ok": False,
                "metin": messages.RUN_UNKNOWN_ENGINE.format(given=value, valid=valid),
            }
        self._state.engine = engine
        self._note_persist_warning(persist_engine(self._state.config, engine.value))
        return None

    # --- Oturum zamanlayıcısı (P-038) ------------------------------------------- #

    def _cron_save(self) -> None:
        cron_store.save(
            self._state.config.memory_dir, self._conversation_id or "app", self._state.cron
        )

    def _cron_list(self) -> dict[str, Any]:
        """`cron.listele`: sekmenin zamanlanmış görevleri."""
        tasks = self._state.cron.list(time.time())
        return {"ok": True, "gorevler": [task.to_dict() for task in tasks]}

    def _cron_delete(self, data: dict[str, Any]) -> dict[str, Any]:
        """`cron.sil {id}`; `id: "all"` hepsini durdurur."""
        task_id = data.get("id")
        if not isinstance(task_id, str) or not task_id.strip():
            return {"ok": False, "metin": "Görev kimliği gerekli."}
        if task_id == "all":
            count = self._state.cron.clear()
        else:
            count = 1 if self._state.cron.delete(task_id) else 0
        self._cron_save()
        if count == 0:
            return {"ok": False, "metin": messages.LOOP_NOT_FOUND.format(id=task_id)}
        return {"ok": True, "silinen": count}

    def _cron_due(self) -> dict[str, Any]:
        """`cron.vadesi_gelenler`: boştaysa vadesi gelen görevleri ver ve ilerlet.

        Arayüz dönen görevleri normal tur olarak gönderir. Tur sürerken boş liste döner;
        görev düşmez, sonraki yoklamada gelir. Aynı görev iki kez verilmez (ilerletilir).
        """
        if self._turn is not None and not self._turn.done():
            return {"ok": True, "gorevler": [], "mesgul": True}
        now = time.time()
        due = self._state.cron.due(now)
        if not due:
            # Önce kanca/zamanlayıcı uyandırması, yoksa biten arka plan işi (#371); tek seferde bir.
            gorevler = self._wake.give(self._state) or background_wake_tasks(
                self._state.background_events
            )
            return {"ok": True, "gorevler": gorevler}
        verilen = []
        for task in due[:1]:
            # Gönderilemezse `cron.geri_ver` bu hâli geri koyar; vade boşa gitmez.
            self._cron_given = {task.id: task}
            self._state.cron.complete(task.id, now=now)
            gorev = fire_prompt(task, root=self._state.root, home=self._state.home)
            # Claude (#371): yalnız modelin çağırabildiği beceri komut olur; gerisi düz metin.
            duz_metin = not runs_as_command(task.prompt, self._state.capabilities)
            verilen.append(
                {"id": task.id, "gorev": gorev, "kaynak": task.source.value, "duz_metin": duz_metin}
            )
            self._cron_fire_prompt = gorev.strip()
        self._cron_save()
        return {"ok": True, "gorevler": verilen}

    def _cron_give_back(self, data: dict[str, Any]) -> dict[str, Any]:
        """`cron.geri_ver {id}`: son verilen görev gönderilemedi; önceki hâline döndür.

        Ölçüldü (31 Ekim): `cron.vadesi_gelenler` görevi vermeden önce ilerletiyordu;
        arayüz gönderemeyince o vade boşa gidiyor, tek seferlik görev kayboluyordu.
        """
        task_id = data.get("id")
        if isinstance(task_id, str) and self._wake.give_back(self._state, task_id):
            return {"ok": True}
        if task_id == BACKGROUND_WAKE_ID:
            # Olaylar kuyrukta kalır; sonraki yoklama yeniden uyandırır.
            self._state.background_events.release_wake()
            return {"ok": True}
        task = self._cron_given.get(task_id) if isinstance(task_id, str) else None
        if task is None:
            return {"ok": False, "metin": messages.LOOP_NOT_FOUND.format(id=task_id)}
        self._cron_given = {}
        self._state.cron.restore(task)
        self._cron_save()
        return {"ok": True}

    def _permissions_rpc(self, request: Request) -> dict[str, Any]:
        """İzin kuralı tablosu ve proje güveni (P-003, P-012); bkz. `permissions_rpc`."""
        from . import permissions_rpc, workspace_dirs_rpc

        root, data = self._state.root, request.data
        if request.name in workspace_dirs_rpc.NAMES:
            # Claude `/permissions` Workspace sekmesi (#83); katalog ek köklerle yenilenir.
            result = workspace_dirs_rpc.handle(self._state, request)
            if result.get("degisti"):
                self._refresh_capabilities()
            return result
        if request.name == "izin.kurallar":
            return permissions_rpc.list_rules(root, self._state.config)
        if request.name == "izin.ekle":
            return permissions_rpc.add_rule(root, data)
        if request.name == "izin.sil":
            return permissions_rpc.remove_rule(root, data)
        if request.name == "izin.engel":
            updated, result = permissions_rpc.set_block(self._state.config, data)
            if updated is not None:
                self._state.config = updated
            return result
        if request.name == "proje.guven_durum":
            return permissions_rpc.trust_status(root)
        if request.name in ("proje.guven_ver", "proje.guven_kaldir"):
            if self._turn is not None and not self._turn.done():
                return {
                    "ok": False,
                    "metin": "Güven sınırını değiştirmeden önce çalışan görevi durdur.",
                }
            result = (
                permissions_rpc.trust_grant(root)
                if request.name == "proje.guven_ver"
                else permissions_rpc.trust_revoke(root)
            )
            # Güven değişince izin listesi ve proje yapılandırması yeniden okunur; "bu
            # oturumda hep izin ver" kararları yeni sınırla taşınmaz.
            self._state.allowed_commands = load_allowed_commands(root)
            self._state.approval_memory.revoke()
            self._state.refresh_config()
            return result
        return {"ok": False, "metin": f"Bilinmeyen istek: {request.name}"}

    def _status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "kok": str(self._state.root),
            "model": self._state.config.agent.model,
            "kip": self._workspace_mode,
            "mod": self._state.approval.value,
            # Ayar/kurum politikası İzinleri atla'yı kapattıysa arayüz anahtarı kilitler (#442).
            "bypass_kapali": bypass_policy_disabled(self._state.root, self._state.home),
            "motor": self._state.engine.value,
            # Oturum kişiliği (P-053); yoksa None. Composer'daki seçici bunu gösterir.
            "kisilik": (
                {"ad": self._state.persona.name, "unvan": self._state.persona.title}
                if self._state.persona is not None
                else None
            ),
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
            # Oturumun bağlı olduğu PR (P-057); yoksa None. Sohbet şeridi rozeti gösterir.
            "pr": (
                {
                    "numara": self._state.linked_pr.number,
                    "url": self._state.linked_pr.url,
                    "depo": self._state.linked_pr.repo,
                }
                if self._state.linked_pr is not None
                else None
            ),
            # Bir ayar dosyası `disableAutoMode: "disable"` diyorsa kip seçici auto'yu gizler (#85).
            "auto_kapali": auto_mode_disabled(self._state.root),
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
        # Proje güveni (P-012): Ayarlar › İzinler satırı ve güven şeridi buradan okur.
        from . import permissions_rpc

        guven = permissions_rpc.trust_status(self._state.root)
        durum["izin"]["guven"] = {
            "guvenildi": guven["guvenildi"],
            "neden": guven["neden"],
            "dusurulen_bolumler": guven["dusurulen_bolumler"],
            "yok_sayilan_dosyalar": guven["yok_sayilan_dosyalar"],
            "yuklenmeyen_araclar": guven["yuklenmeyen_araclar"],
        }
        return durum

    def _cirak_bildirimi_gerekli_mi(self) -> bool:
        """Faz 3, Görev 2 (§6.1): web kilidiyken TEK SEFERLİK bildirim — YAN ETKİSİZ.

        agent bir web oturumuna kilitliyse VE bildirim daha önce görüldü diye
        işaretlenmediyse `True` döner. İşareti bu okuma KOYMAZ: `kontrol.durum`
        arayüzde arka planda da yoklanır (aktif model çipi), bildirim henüz
        gösterilmeden işaret konursa hem arayüzde hem terminalde sonsuza dek
        kaybolurdu. Ölçüldü (30 Ekim, S2-51): iki ardışık `kontrol.durum` ikinciyi
        `False` yapıyordu. İşareti arayüz bildirimi gerçekten gösterince
        `kontrol.cirak_bildirimi_goruldu` ile koyar (bkz. `_ack_apprentice_notice`).
        """
        return not (apprentice_active(self._state.config) or apprentice_notice_shown())

    def _ack_apprentice_notice(self) -> dict[str, Any]:
        """`kontrol.cirak_bildirimi_goruldu`: bildirim görüldü, bir daha çıkmasın (idempotent)."""
        if mark_apprentice_notice_shown():
            return {"ok": True}
        return {"ok": False, "metin": messages.APPRENTICE_NOTICE_ACK_FAILED}

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
        previous_history = self._state.history
        previous_binding = (self._state.root, self._state.conversation_id)
        name = str(data.get("ad", ""))
        argument = str(data.get("arguman", ""))
        # Zamanlanmış görevin ateşlediği `/beceri` satırının fork'u beklenir (Claude Code #141).
        fired, self._cron_fire_prompt = self._cron_fire_prompt, ""
        self._state.line_scheduled = bool(fired) and fired == f"/{name} {argument}".strip()
        command = self._registry.get(name)
        turn_running = (self._turn is not None and not self._turn.done()) or self._goal_judging()
        if turn_running and command is not None and data.get("kuyruktan") is not True:
            from ..cli.repl.busy_commands import IMMEDIATE_COMMANDS

            if command.name not in IMMEDIATE_COMMANDS:
                # Claude Code (#209): tur sürerken yalnız belgelenen anlık komutlar çalışır;
                # diğerleri kuyruğa girer, arayüz tur bitince `kuyruktan: true` ile yollar.
                return {"ok": True, "metin": "", "kuyruk": True}
        if command is not None and command.name == "cd" and turn_running:
            # İşleyici ek klasörleri ve oturum izinlerini sıfırlar; tur sürerken kök değişmez.
            return {"ok": False, "metin": "Tur sürerken proje kökü değiştirilemez."}
        if (
            command is not None
            and command.name == "bypass"
            and bypass_policy_disabled(self._state.root, self._state.home)
        ):
            return {"ok": False, "metin": messages.BYPASS_POLICY_DISABLED}
        if command is not None and command.name == "clear":
            # `/clear` masaüstünde EKRAN temizler. TUI'de karşılama afişini
            # yeniden basmak doğrudur çünkü terminal geçmişi yerinde kalır;
            # uygulamada aynı şeyi yapmak sohbetin içine ASCII afiş düşürüyordu.
            # `/reset`, `/new` artık `/clear` takma adı (#185). Masaüstü sohbet kimliğini
            # kendi sekmesi yönetir; geçmiş ve hook oturumu Claude `/clear` gibi yenilenir.
            self._visible_generation += 1
            self._visible_history_imported = False
            self._transcript_store.record_visible_clear()
            self._state.reset_history()
            if not turn_running:
                # REPL/TUI'de `/clear` yeni sohbet kimliği açtığı için eski sohbetin arka plan
                # ajanları kapanır ve görev sahibi yenilenir; masaüstünde kimlik sekmede kalır,
                # aynı sonuç burada açıkça kurulur (`/reset` artık `/clear` takma adı, #185).
                await self._state.reset_child_runs()
                self._child_runs = self._state.child_runs
            # Claude in Chrome: /clear oturum sekme grubunu kapatır (#436); tur sürüyorsa
            # yalnız boş grup kapanır, süren işin sekmesi elinden alınmaz.
            schedule_group_close(self._chrome, only_empty=turn_running)
            return {"ok": True, "metin": "", "temizle": True}
        if command is not None and renders_itself(command.name, argument):
            rendered: dict[str, Any] = {
                "ok": True,
                "metin": await render_command_text(
                    self._registry, self._state, command.name, argument
                ),
            }
            # `/doctor` sorun bulunca düzeltme turu hazırlar (#212); arayüz onu tur yapar.
            task, mode = self._state.take_pending()
            if task:
                self._next_turn_mode = mode
                rendered["gorev"] = task
            return rendered
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
            result = await self._owned_model_change(
                partial(
                    run_command,
                    self._registry,
                    self._state,
                    name,
                    argument,
                    secret_store=self._secret_store,
                )
            )
        elif command is not None and command.group == SKILL_GROUP:
            # Beceri gövdesindeki !`cmd` komutları komut başına 10 sn'ye kadar bloklayan
            # `subprocess.run` yapar; olay döngüsünde koşarsa akış/iptal/RPC donar
            # (ölçüldü 31 Ekim). İşleyici yalnız bekleyen görev/bağlam alanlarını yazar.
            result = await asyncio.to_thread(
                run_command,
                self._registry,
                self._state,
                name,
                argument,
                secret_store=self._secret_store,
            )
        else:
            result = run_command(
                self._registry, self._state, name, argument, secret_store=self._secret_store
            )
        if (command is not None and command.name == "reset") or previous_binding != (
            self._state.root,
            self._state.conversation_id,
        ):
            await self._state.reset_child_runs()
            self._child_runs = self._state.child_runs
        if self._state.approval is not previous_approval:
            self._state.approval_memory.revoke()
            self._sync_active_approval(explicit_mode=self._state.approval)
            self._note_persist_warning(persist_approval(self._state.config, self._state.approval))
            result = {**result, **self._take_persist_warning()}
        if command is not None and command.name in {"rewind", "undo"}:
            # Dosyalar tur başına döndü; çalışma alanı günlüğündeki "geri al" kayıtları
            # bayatlamasın (değişiklikler paneli artık olmayan farkı göstermesin).
            self._drop_reverted_journal_entries()
            if self._state.history is not previous_history:
                # Konuşma geri sarıldı: arayüz sohbet panosunu kalan geçmişe kessin. Ölçüldü
                # (31 Ekim): sinyal yokken pano tüm eski mesajları göstermeye devam ediyor,
                # kullanıcı modelin hâlâ bildiğini sanıyordu.
                result = {**result, "gecmis": visible_history(self._state.history)}
        if command is not None and command.name in {"worktree", "cd"}:
            # `/worktree <ad>`, `cik` ya da `/cd <yol>` (P-072) oturum kökünü değiştirdi:
            # masaüstü köküyle aynı yoldan (`oturum.baslat{kok}`) hizala, yeni kökü söyle.
            result = {**result, **self._adopt_state_root()}
            result = await self._flush_hook_events(result)
        # Makrolar görevi yalnız HAZIRLAR (bkz. `cli/repl/commands.py::_macro`).
        # Terminal döngüsü hazırlanan görevi hemen çalıştırıyordu; masaüstünde bu
        # adım yoktu ve `/goal` "çalıştırılıyor…" deyip hiçbir tur başlatmıyordu.
        # Görev arayüze döner, arayüz onu normal tur olarak gönderir; kip ise o
        # tura burada taşınır.
        self._cron_save()
        if text := self._state.take_pending_input():
            # `/rewind` konuşmayı sardıysa hedef istem giriş kutusuna döner (#200).
            result = {**result, "girdi": text}
        task, mode = self._state.take_pending()
        if not task:
            return result
        self._next_turn_mode = mode
        return {**result, "gorev": task}

    async def _prefix_reply(
        self, task: str, *, state: ReplState | None = None
    ) -> dict[str, Any] | None:
        """`! komut` ve `# not` yerel cevap döner; `@dosya` blokları sonraki turun bağlamına girer.

        Ölçüldü (31 Ekim): masaüstünde önekler düz mesaj olarak modele gidiyordu (yarım
        yüzey). Terminal yüzeyiyle aynı saf fonksiyonlar (`cli/repl/prefixes.py`) kullanılır;
        kabuk çıktısı Markdown çiti içinde arayüze yazılır, bağlam bloğu maskeli ve etiketli.
        """
        from ..cli.repl import prefixes
        from ..cli.repl.loop import apply_mentions

        state = state or self._state

        if (command := prefixes.shell_command(task)) is not None:
            result = await self._live_shell(command, state=state)
            parts: list[str] = []
            if result.output:
                parts.append(f"```text\n$ {command}\n{result.output.rstrip()}\n```")
            follow_up = ""
            if result.context_block:
                from ..cli.repl import shell_mode

                if shell_mode.responds_to_bash_commands(state.root, state.home):
                    # Claude Code (#219): çıktı bağlama girince model kendiliğinden yanıtlar;
                    # arayüz bu görevi kullanıcı mesajı göstermeden tur olarak başlatır.
                    follow_up = shell_mode.follow_up_task(command)
                else:
                    parts.append(messages.SHELL_PREFIX_CONTEXT_NOTE)
            parts.extend(result.notes)
            reply: dict[str, Any] = {
                "ok": result.ok,
                "metin": "\n\n".join(parts),
                "yerel_yanit": True,
            }
            return {**reply, "gorev": follow_up} if follow_up else reply
        for mention_note in apply_mentions(task, state):
            # Arayüze ayrı not kanalı yok; okunamayan anma günlüğe düşer, tur yine çalışır.
            logging.getLogger(__name__).info("@anma: %s", mention_note)
        return None

    def _with_steering_leftover(self, result: dict[str, Any]) -> dict[str, Any]:
        """Tüketilmemiş yönlendirmeleri sonuca ekle; arayüz sıradaki tur olarak yollar."""
        leftover, self._steering_leftover = self._steering_leftover, []
        return {**result, "kalan_yonlendirme": leftover} if leftover else result

    async def _live_shell(
        self, command: str, *, state: ReplState | None = None
    ) -> ShellPrefixResult:
        """`! komut` çıktısı komut sürerken `KabukCiktisi` olayıyla akar (#219)."""
        from ..cli.repl import prefixes

        def _emit(payload: dict[str, Any]) -> None:
            try:
                self._writer(encode_event({"olay": "KabukCiktisi", "komut": command, **payload}))
            except (OSError, ValueError):
                logging.getLogger(__name__).debug("kabuk çıktısı iletilemedi")

        try:
            return await prefixes.run_shell_prefix(
                state or self._state, command, on_chunk=lambda text: _emit({"parca": text})
            )
        finally:
            _emit({"bitti": True})

    def _ensure_idle_watch(self) -> None:
        """Girdi bekleyen sekme boşta kalınca `Notification(idle_prompt)` (P-009)."""
        if self._idle_watch is not None or self._closed:
            return
        from ..cli.repl import hook_events

        log = logging.getLogger(__name__)
        self._idle_watch = hook_events.start_idle_watch(
            self._state,
            lambda: self._turn is not None and not self._turn.done(),
            lambda text: log.warning("boşta bildirimi kancası: %s", text),
        )

    async def _flush_hook_events(self, result: dict[str, Any]) -> dict[str, Any]:
        """`/cd` kuyruğa aldığı `CwdChanged` kancasını gönder (P-009); kök değişmediyse atar.

        Tur sürerken kök geri alınır (`_adopt_state_root`): o durumda olay gönderilmez.
        """
        from ..cli.repl import hook_events

        session = self._state.hook_session
        if session is None:
            return result
        if result.get("ok") is False:
            session.drop_deferred()
            return result
        lines = await hook_events.flush(self._state)
        if not lines:
            return result
        text = "\n".join(part for part in (str(result.get("metin") or ""), *lines) if part)
        return {**result, "metin": text}

    def _adopt_state_root(self) -> dict[str, Any]:
        """Slash komutu `state.root`'u değiştirdiyse sekmenin kökünü ona taşı (`kok` döner)."""
        try:
            changed = self._state.root.resolve() != self._root.resolve()
        except OSError:
            changed = True
        if not changed:
            return {}
        if self._turn is not None and not self._turn.done():
            self._state.root = self._root
            return {"ok": False, "metin": "Tur sürerken proje kökü değiştirilemez."}
        self._apply_root(self._state.root)
        # Konuşma AYNI sohbettir: geçmiş, tur checkpoint'leri ve kimlik korunur; yalnız
        # depo yeni köke bağlanır (çalışma ağacı projenin transcript anahtarını paylaşır).
        # Ölçüldü (31 Ekim): `_rebind_transcript` geçmişi yeni kökten yeniden yüklüyor,
        # /worktree sonrası model önceki konuşmayı bilmiyordu.
        self._transcript_store = TranscriptStore(
            self._state.config.memory_dir,
            self._root,
            conversation_id=self._transcript_store.session_id,
        )
        self._all_capabilities = CapabilityRegistry(
            self._home,
            self._root,
            managed_roots=tuple(
                Path(value) for value in self._state.config.agent_launch.managed_agent_roots
            ),
            working_directory=self._root,
            extra_agent_sources=getattr(
                self._state.config.agent_launch, "extra_agent_sources", True
            ),
        )
        self._disabled_skills.clear()
        self._disabled_agents.clear()
        self._disabled_mcp.clear()
        self._refresh_capabilities()
        return {"kok": str(self._root.resolve())}

    def _apply_root(self, new_root: Path) -> bool:
        """Kökü değiştir ve köke bağlı yardımcıları sıfırla; kök gerçekten değiştiyse True."""
        root_changed = new_root.resolve() != self._root.resolve()
        self._root = new_root
        self._state.root = self._root
        # Künye kökten türetilir: sekme bir çalışma ağacı köküyle açılırsa `/worktree cik`
        # çalışır; başka projeye geçilirse eski ağacın künyesi kalmaz.
        self._state.worktree = worktree_for_path(self._root)
        if root_changed:
            # Başka bir projenin dizin izinleri ve "bu oturumda hep izin ver" kararları
            # yeni projeye taşınmaz.
            self._state.extra_roots = ()
            self._state.approval_memory.revoke()
        self._workspace_journal = WorkspaceJournal()
        self._processes.update_root(self._root)
        # Önbellek kökle anahtarlı, ama eski kökün girdisi bellekte
        # kalmasın: kullanıcı projeler arasında gidip gelirken bayat bir
        # listeyle karşılaşmamalı.
        self._file_search.invalidate()
        return root_changed

    def _drop_reverted_journal_entries(self) -> None:
        """İçeriği kayıt öncesi hâline eşit olan dosyaların günlük girdisini düşür."""
        for entry in self._workspace_journal.latest():
            path = self._state.root / entry.path
            try:
                current: bytes | None = path.read_bytes()
            except FileNotFoundError:
                current = None
            except OSError:
                continue
            if current == (entry.before if entry.existed else None):
                self._workspace_journal.pop(entry.path)

    async def _select_model(self, data: dict[str, Any]) -> dict[str, Any]:
        """`model.sec {kaynak, model}`: yapısal model seçimi (U1-40).

        `/development uygula` komut dizgesiyle AYNI kabul kilidi, thread ve sonuç zarfı;
        yalnız girdi dizgeden değil alanlardan gelir (bkz. `select_development_model`).
        """
        return await self._owned_model_change(
            partial(select_development_model, self._state, data.get("kaynak"), data.get("model"))
        )

    async def _owned_model_change(self, runner: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        """Model değişimini sahipli görev yap: iptal edilen bekleyici kilidi bırakmaz."""
        owned = asyncio.create_task(self._apply_model_change(runner))
        self._model_selection_tasks.add(owned)
        owned.add_done_callback(self._model_selection_done)
        return await asyncio.shield(owned)

    async def _apply_model_change(self, runner: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        """Thread sona erene kadar seçim/kabul kilidi sahipliğini koru."""
        async with self._admission_lock:
            if self._closed:
                return {"ok": False, "metin": "Oturum kapandı; model seçimi uygulanmadı."}
            previous_model = self._state.config.agent.model
            # Daemon thread: NIM araç doğrulaması 90 sn sürebilir ve kapanışta beklenmemeli (S2-22).
            result = await run_in_daemon_thread(runner)
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

    async def _command_options(self, data: dict[str, Any]) -> dict[str, Any]:
        """Sıradaki seçici/metin adımını döndür; yoksa `ok: False`.

        Model katalog kaynakları (OpenRouter/NIM/Ollama) ağdan okur. Ölçüldü (30 Ekim):
        `command_choices` olay döngüsünde doğrudan çalışıyor, ağ süresince tüm stdio
        döngüsünü donduruyordu ve istisnası `handle` sınırına sızıyordu; artık ayrı
        thread'de koşar, hata genel komut hatasına çevrilir.
        """
        name = str(data.get("ad", ""))
        argument = str(data.get("arguman", ""))
        try:
            payload = await asyncio.to_thread(command_choices, self._state, name, argument)
        except Exception as error:  # katalog/ağ hatası: oturum ve döngü ayakta kalır
            logging.getLogger(__name__).error(
                "Komut seçenekleri üretilemedi (%s): %s", name, type(error).__name__
            )
            return {"ok": False, "metin": messages.APP_COMMAND_FAILED}
        if payload is None:
            return {"ok": False, "metin": messages.APP_COMMAND_UNKNOWN}
        return {"ok": True, "secici": payload}

    def _capture_delivery_owner(self, key: SubmissionKey) -> _DeliveryOwner | None:
        store = self._transcript_store
        owner = _DeliveryOwner(store, key, store.session_id, self._visible_generation)
        alias = (
            self._conversation_id is None
            and key.conversation_id == FALLBACK_CONVERSATION_ID
            and self._state.conversation_id == store.session_id
        )
        return (
            owner if owner.valid() and (store.session_id == key.conversation_id or alias) else None
        )

    def _capture_accepted_turn(self) -> _AcceptedTurn:
        from ..cli.repl.task_list import StoredTodoList, task_list_path
        from ..cli.rule_notices import attach_rule_writer
        from ..engines.agent.auto_switch import AutoSwitch

        visible = self._state
        state = copy.copy(visible)
        state.root = self._transcript_store.root
        state.history = list(visible.history)
        state.pending_blocks = list(visible.pending_blocks)
        state.checkpoints = copy.deepcopy(visible.checkpoints)
        state.cron = copy.deepcopy(visible.cron)
        state.todos = copy.deepcopy(visible.todos)
        if isinstance(state.todos, StoredTodoList):
            state.todos._locate = lambda: task_list_path(
                state.config.memory_dir, state.conversation_id
            )
        memory = copy.copy(visible.approval_memory)
        memory._scopes = set(memory._scopes)
        memory.notices = list(memory.notices)
        memory.auto_review = copy.copy(memory.auto_review)
        memory.auto_review._cache = memory.auto_review._cache.copy()
        memory.auto_review._recent = memory.auto_review._recent.copy()
        memory.auto_review.remembered = memory.is_remembered
        memory.auto_review.plan_bypass = lambda: memory.plan_bypass
        memory.auto_review.on_fallback = state._fall_back_to_manual
        memory.auto_switch = AutoSwitch(
            available=state._auto_switch_available, switch=state._switch_to_auto
        )
        attach_rule_writer(memory, lambda: state.root)
        state.approval_memory = memory
        generation = self._visible_generation
        original_mode = visible.approval
        original_revision = visible.approval_memory.revision

        def mode_changed(mode: ApprovalMode) -> None:
            if (
                self._state is visible
                and self._visible_generation == generation
                and visible.approval is original_mode
                and visible.approval_memory.revision == original_revision
            ):
                visible.approval = mode
                if visible.on_mode_change is not None:
                    visible.on_mode_change(mode)

        state.on_mode_change = mode_changed
        # Live hook lifecycle is rebound only after a new receipt is claimed.
        # Capturing/replaying a receipt must not steal a pending opening task.
        previous_hooks = visible.hook_session
        state.hook_session = None
        return _AcceptedTurn(
            state,
            visible,
            self._transcript_store,
            self._conversation_id or FALLBACK_CONVERSATION_ID,
            self._visible_generation,
            self._workspace_mode,
            self._personal_memory,
            frozenset(self._disabled_mcp),
            tuple(self._pending_capabilities),
            self._all_capabilities,
            self._next_turn_mode,
            self._goal_continuation,
            self._fork_requested,
            visible.approval_memory.revision,
            visible.approval,
            self._workspace_journal,
            previous_hooks,
            frozenset(visible.approval_memory._scopes),
        )

    def _bind_hook_owner(self, state: ReplState, source: HookSession) -> None:
        from ..engines.hooks.factory import open_hook_session

        state.hook_session = open_hook_session(
            state.root,
            lambda: state.config,
            session_id=state.conversation_id,
            permission_mode=lambda: state.approval.value,
            existing=source,
        )
        source.skills_reloader = state._reload_skills
        source.title_sink = state._adopt_hook_title
        source.context_chars = lambda: sum(len(m.content or "") for m in state.history)

    def _lease_accepted_hooks(self, accepted: _AcceptedTurn) -> None:
        if self._hook_lease is None:
            if accepted.hook_source is not None:
                self._bind_hook_owner(accepted.state, accepted.hook_source)
            self._hook_lease = accepted

    def _sync_active_approval(self, *, explicit_mode: ApprovalMode | None = None) -> None:
        accepted = self._active_accepted or self._hook_lease
        if accepted is None:
            return
        memory = accepted.state.approval_memory
        visible = self._state.approval_memory
        # Explicit user permission changes belong to chat identity even after
        # old -> new -> old. Incidental mutable deltas still require the exact
        # generation, so another chat cannot revoke or regrant this turn's scopes.
        if explicit_mode is not None and self._same_accepted_chat(accepted):
            if accepted.state.approval is not explicit_mode or memory.revision != visible.revision:
                memory.revoke()
            memory.revision = visible.revision
            accepted.state.approval = explicit_mode
            return
        if not self._accepted_is_visible(accepted):
            return
        memory._scopes.difference_update(accepted.approval_scopes - visible._scopes)
        if visible.revision != accepted.approval_revision and memory.revision != visible.revision:
            memory.revoke()
            memory.revision = visible.revision
            accepted.state.approval = self._state.approval

    async def _release_accepted_hooks(self, accepted: _AcceptedTurn) -> None:
        if self._hook_lease is not accepted:
            return
        self._hook_lease = None
        source = accepted.state.hook_session or accepted.hook_source
        if source is not None and (
            self._state.hook_session is source
            or (self._accepted_is_visible(accepted) and self._state.hook_session is None)
        ):
            self._bind_hook_owner(self._state, source)
        elif source is not None:
            await source.end("resume")

    def _same_accepted_chat(self, accepted: _AcceptedTurn) -> bool:
        return (
            self._state.root.resolve() == accepted.store.root
            and (self._conversation_id or FALLBACK_CONVERSATION_ID) == accepted.conversation_id
            and self._state.config.memory_dir == accepted.state.config.memory_dir
        )

    def _merge_accepted_result(self, accepted: _AcceptedTurn) -> None:
        self._merge_accepted_approval(accepted)
        if not self._accepted_is_visible(accepted):
            return
        state = accepted.state
        for name in (
            "history",
            "last_changes",
            "last_tool_context",
            "checkpoints",
            "pending_plan",
            "linked_pr",
            "persona_initial_prompt_applied",
            "invoked_skills",
            "todos",
            "cron",
            "worktree",
            "hook_session",
        ):
            setattr(self._state, name, getattr(state, name))
        self._state.root = state.root
        self._state.child_runs = state.child_runs
        self._child_runs = state.child_runs

    def _merge_accepted_approval(self, accepted: _AcceptedTurn) -> None:
        if not self._same_accepted_chat(accepted):
            return
        state = accepted.state
        self._sync_active_approval()
        if self._state.approval_memory.revision == state.approval_memory.revision:
            self._state.approval_memory = state.approval_memory
            self._state.approval = state.approval

    def _accepted_capability_context(
        self, accepted: _AcceptedTurn
    ) -> tuple[str, SkillSelection | None, bool]:
        state = accepted.state
        parts: list[str] = []
        selected_skill = None
        fork = False
        for kind, name in accepted.pending_capabilities:
            if kind == "beceri":
                item = accepted.catalogue.get_skill(name)
                if item is None:
                    continue
                page = read_skill_page(item.path)
                if page.error:
                    continue
                if selected_skill is None:
                    selected_skill = SkillSelection(
                        item.qualified_name, page.revision, page.next_offset
                    )
                if getattr(item, "context", "") == "fork":
                    fork = True
                    if not state.pending_fork_agent:
                        state.pending_fork_agent = getattr(item, "agent", "")
                self._queue_skill_turn_settings(item, state=state)
                parts.append(f"# Kullanıcının açıkça seçtiği beceri: {name}\n{page.text}")
            elif kind == "ajan":
                item = accepted.catalogue.get_agent(name)
                body = load_agent_prompt(item.path)[:6_000] if item else ""
                if body:
                    parts.append(f"# Kullanıcının açıkça seçtiği uzman ajan: {name}\n{body}")
            elif kind == "mcp":
                parts.append(
                    f"Kullanıcı bu turda özellikle '{name}' MCP sunucusunun "
                    "araçlarını kullanmanı istedi."
                )
        return "\n\n".join(parts), selected_skill, fork

    def _accepted_is_visible(self, accepted: _AcceptedTurn) -> bool:
        return (
            self._state is accepted.visible_state
            and self._visible_generation == accepted.generation
            and self._state.root.resolve() == accepted.store.root
            and (self._conversation_id or FALLBACK_CONVERSATION_ID) == accepted.conversation_id
        )

    def _consume_accepted_inputs(self, accepted: _AcceptedTurn) -> None:
        """Only a newly claimed receipt consumes the pending inputs it captured."""
        if not self._accepted_is_visible(accepted):
            return
        empty = copy.copy(accepted.state)
        empty.take_pending_extras()
        empty.take_pending_digest()
        for name in (
            "pending_context",
            "pending_tools",
            "pending_model_choice",
            "pending_denied_tools",
            "pending_fork_agent",
            "pending_grants",
            "pending_fresh_fork",
            "pending_fork_background",
            "pending_fork_skill",
            "pending_stacked_skills",
            "pending_skill_name",
            "pending_digest",
            "pending_blocks",
        ):
            if getattr(self._state, name) == getattr(accepted.state, name):
                # Consume through a throwaway view so the accepted view retains
                # its captured values until it constructs the actual turn extras.
                setattr(self._state, name, getattr(empty, name))
        if tuple(self._pending_capabilities) == accepted.pending_capabilities:
            self._pending_capabilities = []
        if self._next_turn_mode == accepted.next_mode:
            self._next_turn_mode = macros.Mode.NONE
        if self._goal_continuation == accepted.goal_continuation:
            self._goal_continuation = None
        if self._fork_requested == accepted.fork_requested:
            self._fork_requested = False

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
        from ..core.submission import SubmissionKey

        try:
            self._state.prepare_persona_config()
        except ConfigError as error:
            return {"ok": False, "metin": str(error)}
        # Bind profile adoption to the same visible chat as the receipt key,
        # before lookup/claim or durable running-state writes can yield.
        profile_generation = self._visible_generation
        key = SubmissionKey(
            str(self._state.config.memory_dir.resolve()),
            str(self._root.resolve()),
            self._conversation_id or FALLBACK_CONVERSATION_ID,
            str(request.data["gonderim_id"]),
        )
        delivery_owner = self._capture_delivery_owner(key)
        accepted = self._capture_accepted_turn()
        self._lease_accepted_hooks(accepted)
        try:
            return await self._admit_captured_submission(
                request, key, profile_generation, delivery_owner, accepted
            )
        finally:
            if self._active_accepted is not accepted:
                await self._release_accepted_hooks(accepted)

    async def _admit_captured_submission(
        self,
        request: Request,
        key: SubmissionKey,
        profile_generation: int,
        delivery_owner: _DeliveryOwner | None,
        accepted: _AcceptedTurn,
    ) -> dict[str, Any]:
        import sqlite3

        from .submission import receipt_payload

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
                try:
                    attachment_images = await _attachment_images_async(request.data.get("ekler"))
                except ValueError as error:
                    return {"ok": False, "metin": str(error)}
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
                self._consume_accepted_inputs(accepted)
                self._lease_accepted_hooks(accepted)
                self._active_accepted = accepted
                owned = asyncio.create_task(
                    self._execute_submission(
                        claim.receipt,
                        task,
                        attachment_context,
                        attachment_images,
                        voice_context,
                        deadline,
                        accepted.state.config,
                        accepted.state.auto_profile,
                        profile_generation,
                        delivery_owner,
                        accepted,
                    )
                )
                self._submission_task = owned
                try:
                    self._writer(
                        encode_event({"olay": "GonderimMakbuzu", **receipt_payload(claim.receipt)})
                    )
                except (OSError, ValueError):
                    # `ValueError`: kodlama hatası (`UnicodeEncodeError`) dâhil. Kabul edilmiş
                    # görev çalışır durumdayken istemciye hata dönmesin (ölçüldü 30 Ekim).
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
        auto_profile_snapshot: bool | None = None,
        profile_generation_snapshot: int | None = None,
        delivery_owner_snapshot: _DeliveryOwner | None = None,
        accepted_snapshot: _AcceptedTurn | None = None,
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
                auto_profile_snapshot=auto_profile_snapshot,
                profile_generation_snapshot=profile_generation_snapshot,
                delivery_owner_snapshot=delivery_owner_snapshot,
                accepted_snapshot=accepted_snapshot,
            )
            result = self._with_steering_leftover(result)
            # İptal durumu ekran metninin eşitliğinden değil açık işaretten çıkarılır (metin
            # değişirse/yerelleştirilirse yanlış durum yazılırdı; ölçüldü 30 Ekim).
            was_cancelled = result.pop("_cancelled", False) is True
            state = (
                "completed" if result.get("ok") else ("cancelled" if was_cancelled else "failed")
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
            if self._active_accepted is accepted_snapshot:
                self._active_accepted = None
            if accepted_snapshot is not None:
                await self._release_accepted_hooks(accepted_snapshot)

    async def _run_turn(
        self,
        task: str,
        attachment_context: str = "",
        images: tuple[str, ...] = (),
        *,
        voice_context: VoiceTurnContext | None = None,
        browser_only: bool = False,
        chrome_turn_id: str | None = None,
        auto_continues: int = 0,
        deadline: TurnDeadline | None = None,
        receipt: SubmissionReceipt | None = None,
        event_sequence: Iterator[int] | None = None,
        config_snapshot: Config | None = None,
        auto_profile_snapshot: bool | None = None,
        profile_generation_snapshot: int | None = None,
        delivery_owner_snapshot: _DeliveryOwner | None = None,
        accepted_snapshot: _AcceptedTurn | None = None,
    ) -> dict[str, Any]:
        accepted = accepted_snapshot or self._capture_accepted_turn()
        if accepted_snapshot is None:
            self._lease_accepted_hooks(accepted)
        try:
            return await self._run_accepted_turn(
                task,
                attachment_context,
                images,
                voice_context=voice_context,
                browser_only=browser_only,
                chrome_turn_id=chrome_turn_id,
                auto_continues=auto_continues,
                deadline=deadline,
                receipt=receipt,
                event_sequence=event_sequence,
                config_snapshot=config_snapshot,
                auto_profile_snapshot=auto_profile_snapshot,
                profile_generation_snapshot=profile_generation_snapshot,
                delivery_owner_snapshot=delivery_owner_snapshot,
                accepted_snapshot=accepted,
            )
        finally:
            if self._active_accepted is accepted:
                self._active_accepted = None
            await self._release_accepted_hooks(accepted)
            if not browser_only:
                if (
                    self._same_accepted_chat(accepted)
                    and self._transcript_store is not accepted.store
                ):
                    # Old -> new -> old: the durable owner may have completed
                    # after the last reopen loaded history. Reload only that owner.
                    self._state.history = load_transcript_messages(
                        accepted.state.config.memory_dir,
                        accepted.store.root,
                        conversation_id=accepted.store.session_id,
                    )
                if accepted.state.child_runs is not self._state.child_runs:
                    await accepted.state.child_runs.close()

    async def _run_accepted_turn(
        self,
        task: str,
        attachment_context: str = "",
        images: tuple[str, ...] = (),
        *,
        voice_context: VoiceTurnContext | None = None,
        browser_only: bool = False,
        chrome_turn_id: str | None = None,
        auto_continues: int = 0,
        deadline: TurnDeadline | None = None,
        receipt: SubmissionReceipt | None = None,
        event_sequence: Iterator[int] | None = None,
        config_snapshot: Config | None = None,
        auto_profile_snapshot: bool | None = None,
        profile_generation_snapshot: int | None = None,
        delivery_owner_snapshot: _DeliveryOwner | None = None,
        accepted_snapshot: _AcceptedTurn | None = None,
    ) -> dict[str, Any]:
        """Kabul anındaki bağlamla çalış; yalnız açık canlı izin değişikliklerini eşle."""
        assert accepted_snapshot is not None
        accepted = accepted_snapshot
        turn_state = accepted.state
        turn_store = accepted.store
        self._report_voice_background_failures()
        if not browser_only:
            try:
                turn_state.prepare_persona_config()
            except ConfigError as error:
                return {"ok": False, "metin": str(error)}
            task = turn_state.take_persona_initial(task)
        if not task.strip():
            return {"ok": False, "metin": messages.RUN_EMPTY_TASK}
        if not browser_only and receipt is None and delivery_owner_snapshot is None:
            delivery_owner_snapshot = self._capture_delivery_owner(
                SubmissionKey(
                    str(turn_state.config.memory_dir.resolve()),
                    str(turn_state.root.resolve()),
                    accepted.conversation_id,
                    "",
                )
            )
        await self._iptal_edilen_turu_bekle()
        if (
            self._turn is not None
            or self._goal_judging()
            or (
                self._submission_task is not None
                and not self._submission_task.done()
                and asyncio.current_task() is not self._submission_task
            )
        ):
            return {"ok": False, "metin": messages.APP_TURN_ALREADY_RUNNING}
        if not browser_only and receipt is None and auto_continues == 0:
            self._consume_accepted_inputs(accepted)
        self._active_accepted = accepted
        from ..cli.session import open_trace, run_agent_task

        # Yan panelin konuşması uygulamanın sohbetine KARIŞMAZ: kendi geçmişi vardır,
        # diske yazılmaz, adımları ve soruları yalnız panele akar (Claude in Chrome gibi).
        if not browser_only:
            if receipt is None:
                # Otomatik devamın sentetik "devam et" metni kullanıcı sözü değildir
                # (makbuz yolundaki `auto_continues == 0` koşuluyla aynı kural).
                if auto_continues == 0:
                    turn_store.record_user(task)
            elif receipt.attempt_id.endswith(":1") and auto_continues == 0:
                turn_store.record_user(task, message_id=f"{receipt.key.request_id}:user")
        if voice_context is not None and not browser_only and not attachment_context and not images:
            from .voice_intents import local_voice_reply

            reply = local_voice_reply(task)
            if reply is not None:
                turn_state.history = [
                    *turn_state.history,
                    Message("user", task),
                    Message("assistant", reply),
                ]
                turn_store.record_assistant(
                    reply, message_id=f"{receipt.key.request_id}:assistant" if receipt else None
                )
                self._merge_accepted_result(accepted)
                return {"ok": True, "metin": reply, "yerel_yanit": True}
        if not browser_only and not attachment_context and not images:
            # REPL önekleri (P-022) masaüstünde de geçerli; `!`/`#` model çağırmaz.
            local = await self._prefix_reply(task, state=turn_state)
            if local is not None:
                self._merge_accepted_result(accepted)
                if self._accepted_is_visible(accepted):
                    from ..cli.repl.prefixes import push_pending_context

                    for block in turn_state.pending_blocks:
                        push_pending_context(self._state, block)
                return local
            from ..cli.repl.background_commands import at_session_turn

            # `@oturum mesaj` (#228): Claude Code gibi tur çalışır, model SendMessage ile iletir.
            task = at_session_turn(turn_state, task) or task
        image_command = None if browser_only else parse_image_command(task)
        if image_command is not None and not attachment_context and not images:
            ok, markdown = await run_image_command(turn_state.config, image_command)
            turn_state.history = [
                *turn_state.history,
                Message("user", task),
                Message("assistant", markdown),
            ]
            turn_store.record_assistant(
                markdown, message_id=f"{receipt.key.request_id}:assistant" if receipt else None
            )
            self._merge_accepted_result(accepted)
            return {"ok": ok, "metin": markdown, "gorsel_komutu": True}
        history = self._chrome_history if browser_only else turn_state.history

        # Capture the attempt boundary before execution can mutate history. Tool
        # call IDs are model input and can repeat, including with identical args.
        retry_prefix = tuple(
            message_to(message, include_images=True)
            for message in [*history, Message("user", task)]
        )

        # Kullanım sayacı olayları ARADAN dinler: sayaç için ayrı bir yol
        # açmak, bazı çağrı yollarının muhasebeden düşmesine yol açardı.
        writer = self._chrome.tee(_discard_line) if browser_only else self._writer
        visible_generation = accepted.generation
        recorder = (
            None
            if browser_only
            else VisibleToolRecorder(
                turn_store,
                active=lambda: self._turn is owned_turn,
                turn_id=receipt.attempt_id if receipt else None,
            )
        )

        def public_writer(line: str) -> None:
            if recorder is not None:
                recorder.record(line)
            writer(line)

        protocol_sink = ProtocolSink(public_writer, receipt=receipt, sequence=event_sequence)
        effect_sink = _RetryEffectSink(protocol_sink)
        sink = LibrarySink(
            _MeteredSink(
                effect_sink,
                self._usage,
                self._usage_log,
            ),
            turn_state.root,
        )
        prompter = ProtocolPrompter(
            writer,
            self.pending,
            root=turn_state.root,
            element_name=self._chrome.element_name,
            namespace=receipt.attempt_id if receipt else "",
            on_closed=self._question_closed,
            # Önizleme aracın esnek eşleşme ayarıyla AYNI olmalı (gerçek diff).
            edit_fuzzy_match=(config_snapshot or turn_state.config).runtime.edit_fuzzy_match,
            on_app_denied=partial(self._deny_desktop_app, accepted=accepted),
        )
        steering = SteeringQueue()
        child_runs = turn_state.child_runs
        if self._accepted_is_visible(accepted):
            self._child_runs = child_runs
        self._steering = steering
        self._steering_turn = receipt.attempt_id if receipt else chrome_turn_id
        self._steering_requests.clear()
        config = config_snapshot or turn_state.config
        profile_state = accepted.visible_state
        profile_base_config = config
        # Durable "running" bookkeeping can yield before this method starts.
        # Adoption belongs to the chat visible at acceptance, even if the same
        # ReplState/config has since been rebound to another conversation.
        profile_generation = (
            visible_generation
            if profile_generation_snapshot is None
            else profile_generation_snapshot
        )
        select_auto_profile = auto_continues == 0 and (
            turn_state.auto_profile if auto_profile_snapshot is None else auto_profile_snapshot
        )
        if accepted.disabled_mcp:
            config = replace(
                config,
                mcp_servers=tuple(
                    server
                    for server in config.mcp_servers
                    if server.name not in accepted.disabled_mcp
                ),
            )
        capability_context, selected_skill, capability_fork = self._accepted_capability_context(
            accepted
        )
        inherited_context = turn_state.take_pending_digest()
        # `/beceri` slash komutunun hazırladığı gövde ve araç kısıtı (P-019).
        pending_extras = turn_state.take_pending_extras()
        # Becerinin `model`/`effort` alanı yalnız bu turun yapılandırmasıdır (P-020).
        if not select_auto_profile:
            config = pending_extras.turn_config(config)
        turn_mode = accepted.next_mode
        if not browser_only:
            continuation = accepted.goal_continuation
            if turn_mode is macros.Mode.NONE and continuation is not None and task == continuation:
                turn_mode = macros.Mode.GOAL
        fork_requested = accepted.fork_requested or capability_fork

        def current_approval() -> ApprovalMode:
            self._sync_active_approval()
            return turn_state.approval

        # Kullanıcının kalıcı talimatı da bağlama girer. Sistem istemi
        # DEĞİŞTİRİLMEZ: kimlik ve onay sözleşmesi orada durur.
        execution_binding: tuple[str, str, str, int] | None = None

        async def execute_turn() -> AgentOutcome:
            nonlocal execution_binding
            nonlocal config
            if select_auto_profile:
                from ..config.profile import auto_turn_config

                # Establish _turn ownership before yielding. Classification/imports
                # cannot block the UI or let another turn enter this session.
                selected_config, reason = await asyncio.to_thread(
                    auto_turn_config, profile_base_config, task
                )
                # Only the event loop adopts the result. A cancelled worker or a
                # changed conversation must never overwrite another chat's model.
                if (
                    self._state is profile_state
                    and self._visible_generation == profile_generation
                    and profile_state.config is profile_base_config
                ):
                    profile_state.config = selected_config
                # The session retains its connector catalogue; this turn retains
                # the disabled-connector filter captured above.
                if selected_config.mcp_servers != config.mcp_servers:
                    selected_config = replace(selected_config, mcp_servers=config.mcp_servers)
                config = pending_extras.turn_config(selected_config)
                if reason is not None:
                    sink.handle(StatusChanged(reason))
            if journal is not None:
                # Çalışan tur sahipliği kurulduktan sonra I/O yap; paralel
                # istek ilk turu görünmezken ikinci bir tur başlatamasın.
                journal.save([*history, Message("user", task)])
            # Belleği okumak diske gider. Beklemeyi çalışan tur nesnesi
            # oluşturulduktan SONRA yap; aksi halde aynı anda gelen ikinci
            # istek ilk tur henüz görünmediği için üst üste başlayabilir.
            memory_block = await asyncio.to_thread(accepted.personal_memory.prompt_block)
            # Chrome bağlıyken tarayıcı işlerinin sınırı (bkz. `CHROME_NOTE`).
            # Köprü açıksa not verilir: eklenti o an bağlı olmasa da chrome_* Chrome'u açar.
            chrome_note = CHROME_NOTE if self._chrome.running else ""
            persona = persona_turn(turn_state.persona)
            allowed_tools = pending_extras.merged_tools(
                (CHROME_CODE_TURN_TOOLS if accepted.workspace_mode == "kod" else CHROME_TURN_TOOLS)
                if browser_only
                else persona.allowed_tools
            )
            bootstrap_mcp = True
            if browser_only and config.mcp_servers and allowed_tools is not None:
                from ..tools import build_registry as build_builtin_registry

                # Chrome's MCP-shaped aliases are local builtins. Do not await
                # unrelated connectors before a surface which cannot call them.
                # ask_teacher is registered by engine_tools rather than the
                # base registry; it also has no configured MCP dependency.
                builtin_names = set(build_builtin_registry().names()) | {"ask_teacher"}
                if allowed_tools <= builtin_names:
                    bootstrap_mcp = False
            extra_system = "\n\n".join(
                part
                for part in (
                    persona.extra_system,
                    chrome_note,
                    macros.mode_prompt(turn_mode),
                    inherited_context,
                    capability_context,
                    pending_extras.context,
                    attachment_context,
                    voice_context.prompt() if voice_context else "",
                    instruction_block(),
                    memory_block,
                )
                if part
            )
            execution_binding = (
                str(config.memory_dir.resolve()),
                str(turn_state.root.resolve()),
                accepted.conversation_id,
                accepted.generation,
            )
            return await run_agent_task(
                task,
                config,
                bootstrap_mcp=bootstrap_mcp,
                remotion_transport=turn_state.remotion_transport,
                remotion_browser=turn_state.remotion_browser,
                require_remotion_kit=self._require_remotion_kit,
                deadline=deadline,
                sinks=(
                    sink,
                    self._desktop_activity,
                    self._desktop_permissions,
                    self._computer_activity,
                    *trace_sinks,
                ),
                prompter_factory=lambda _drain: prompter,
                mode=turn_state.approval,
                root=turn_state.root,
                extra_roots=turn_state.extra_roots,
                home=turn_state.home,
                history=history,
                cron=None if browser_only else turn_state.cron,
                background_events=None if browser_only else turn_state.background_events,
                todos=None if browser_only else session_todos(turn_state),
                chrome_bridge=self._chrome,
                skill_grants=pending_extras.grants,
                allowed_tools=allowed_tools,
                denied_tools=(
                    frozenset()
                    if browser_only
                    else pending_extras.merged_denied(persona.denied_tools)
                ),
                extra_system=extra_system,
                # Görsel ekler modele GERÇEKTEN gider; yol metni ayrıca kalır.
                images=images,
                session_persona=None if browser_only else turn_state.persona,
                main_config_applied=turn_state.main_config_applied and not browser_only,
                system_prompt=(
                    persona.system_prompt
                    if browser_only or accepted.workspace_mode == "kod"
                    else CHAT_SYSTEM_PROMPT
                ),
                # Sohbet kipi çalışma alanına dokunmaz: ölçüldü, "kampanya planı
                # yap" isteği sohbette diske dosya yazıyordu (bkz. `chat_mode.py`).
                chat_mode=accepted.workspace_mode != "kod" and not browser_only,
                interactive=True,
                capabilities=turn_state.capabilities,
                plain_memory=turn_state.plain_memory,
                conversation_id=accepted.conversation_id,
                attempt_id=receipt.attempt_id if receipt is not None else None,
                event_correlator=protocol_sink.correlate if receipt is not None else None,
                step_limit=macros.mode_step_limit(turn_mode),
                workflow=macros.mode_workflow(turn_mode),
                # `/subtask` ya da `context: fork` beceri: tur fork alt ajanda (P-054).
                turn_runner=(
                    pending_extras.fork_runner(run_forked_turn)
                    if (macros.mode_fork(turn_mode) or fork_requested) and not browser_only
                    else None
                ),
                approval_memory=turn_state.approval_memory,
                steering=steering,
                child_runs=child_runs,
                selected_skill=selected_skill,
                current_approval=current_approval,
                # Oturumun kalıcı belleği (dersler, öğretmen planları, kod indeksi).
                # Verilmezse tur boş bellekle koşar ve hiçbir şey öğrenilmez.
                memory=turn_state.memory,
                # Sekmenin sağlık kaydı: devre durumu turlar arasında yaşar.
                health=turn_state.health,
                journal=journal,
                background=self._voice_background if voice_context else None,
                changes=changes,
                worktree_switch=switch,
                plan_mode_switch=plan_switch,
                hooks=turn_state.hooks(),
                browser=self._browser_panel.turn_browser(),
            )

        # `enter_worktree`/`exit_worktree` isteği: kök tur ortasında değişmez, tur bitince
        # burada uygulanır (REPL `apply_switch` ile aynı). Ölçüldü (31 Ekim): masaüstü
        # anahtarı hiç okumuyordu; araç "tur bitince kök değişir" diyor, kök değişmiyordu.
        switch = WorktreeSwitch()
        plan_switch = PlanModeSwitch()
        # Ajanın her yazmadan önce aldığı anlık görüntüler; tur bitince (iptal dahil)
        # çalışma alanı günlüğüne geçer ve UI geri alma yalnız bunlara dayanır. Kayıt
        # tur checkpoint defterinden gelir: `/rewind` masaüstünde de aynı defteri sarar.
        changes = (
            ChangeSet() if browser_only else turn_state.checkpoints.begin(task, history).changes
        )
        # Tarayıcı paneli turu sekmenin konuşması değildir; günlüğe yazılmaz.
        journal = None if browser_only else self._turn_journal(task, accepted=accepted)
        self._start_local_state_purge(config.memory_dir)
        # Teşhis izi: `/trace` bu turun neden düştüğünü sonradan söyleyebilsin.
        trace = None if browser_only else open_trace(config.memory_dir / "traces")
        trace_sinks: tuple[EventSink, ...] = (trace,) if trace is not None else ()
        owned_turn = asyncio.ensure_future(execute_turn())
        self._turn = owned_turn
        if browser_only:
            self._chrome_turn_id = chrome_turn_id
            self._chrome.publish({"tur": "basladi", "turnId": chrome_turn_id})
        self._ensure_idle_watch()
        self._turn_settled.clear()
        try:
            outcome = await owned_turn
            # Capture before recovery/history replacement can omit durable calls.
            outcome_entry = journal.load() if journal is not None else None
        except asyncio.CancelledError:
            self._iptal_bekliyor = True
            interrupted_entry = journal.load() if journal is not None else None
            # İptal de bir sonuçtur: kaydedilmezse sekme yeniden açıldığında
            # soru cevapsız durur ve kullanıcı turun neden bittiğini göremez.
            if not browser_only:
                turn_store.record_assistant(
                    messages.APP_TURN_CANCELLED,
                    message_id=f"{receipt.key.request_id}:assistant" if receipt else None,
                )
                # Durdurulan istek geçmişte kalır (Claude'daki gibi): yoksa "devam et"
                # dendiğinde model neyin yarıda kaldığını hiç görmüyordu.
                from ..core.turn_resume import interrupted_history

                preserved = (
                    list(interrupted_entry.messages)
                    if interrupted_entry is not None
                    else [*history, Message("user", task)]
                )
                turn_state.history = interrupted_history(
                    preserved, task=task, root=str(turn_state.root.resolve())
                )
                if journal is not None:
                    await await_owned_thread(journal.save, turn_state.history)
            if browser_only:
                self._merge_accepted_approval(accepted)
            else:
                self._merge_accepted_result(accepted)
            retry_safe = effect_sink.permits_retry(interrupted_entry, retry_prefix)
            return {
                "ok": False,
                "metin": messages.APP_TURN_CANCELLED,
                "_cancelled": True,
                "_retry_safe": retry_safe,
            }
        finally:
            record_agent_changes(turn_state.root, accepted.workspace_journal, changes.snapshots)
            self._desktop_activity.clear()
            self._browser_panel.turn_finished()
            self._computer_activity.clear()
            if self._turn is owned_turn:
                self._iptal_bekliyor = False
                self._turn = None
                self._turn_settled.set()
                self._steering_leftover = _leftover_steering(self._steering)
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
            self._merge_accepted_approval(accepted)
            return {"ok": outcome.ok, "metin": outcome.final_text or messages.APP_TURN_NO_ANSWER}
        turn_state.history = outcome.messages
        # Turda açılan/okunan PR sohbetin PR künyesi olur (P-057; `oturum.durum.pr`); künye
        # çıkarımı korumalıdır, tur kaydını düşürmez.
        linked_pr.bind_from_turn(turn_state, getattr(outcome, "tool_uses", ()))
        switched = await turn_state.apply_worktree_switch(switch)
        # `enter_plan_mode` (#324): model kendini plan kipine geçirdiyse sekme kipi PLAN olur.
        turn_state.apply_plan_mode_switch(plan_switch)
        # `exit_plan_mode` planı yazdıysa kart `plan.kart` ile açılır (#325; REPL ile aynı).
        if getattr(outcome, "plan_path", None) is not None:
            turn_state.pending_plan = outcome.plan_path
        owned_visible = self._accepted_is_visible(accepted)
        self._merge_accepted_result(accepted)
        root_payload = self._adopt_state_root() if switched and owned_visible else {}
        # Transcript bir BAŞARI kaydı değil, NE OLDUĞU kaydıdır.
        #
        # Ölçüldü (7 Eylül, kullanıcının Godot koşuları): plan adımı duraklayınca
        # tur `ok=False` döndü; soru diske yazıldı, cevap yazılmadı. Diskteki
        # `198b3a19…` sohbeti 8 soru ve 0 cevap taşıyor. Sekme yeniden açıldığında
        # model kendi ne dediğini göremiyor ve kaldığı yerden süremiyor — oysa
        # duraklama metni tam da devam etmek için gereken bilgidir.
        presentation = present_delivery(task, outcome)
        expected_binding = (
            (
                delivery_owner_snapshot.key.profile_id,
                delivery_owner_snapshot.key.root,
                delivery_owner_snapshot.key.conversation_id,
                delivery_owner_snapshot.generation,
            )
            if delivery_owner_snapshot is not None
            else None
        )
        if presentation.compact and (execution_binding != expected_binding or switched):
            presentation = replace(
                presentation,
                text=outcome.final_text,
                compact=False,
                evidence={k: v for k, v in (presentation.evidence or {}).items() if k != "sunum"},
            )
        delivered_text = outcome.final_text
        delivered_evidence = presentation.evidence
        delivery_store = (
            delivery_owner_snapshot.store
            if delivery_owner_snapshot is not None and delivery_owner_snapshot.valid()
            else None
        )
        if outcome.final_text.strip() and delivery_store is not None:
            identifier = f"{receipt.key.request_id}:assistant" if receipt else None
            if presentation.evidence is not None:
                saved = delivery_store.record_presented_assistant(
                    presentation.text, evidence=presentation.evidence, message_id=identifier
                )
                if saved:
                    delivered_text = presentation.text
                else:
                    delivered_evidence = {
                        k: v for k, v in presentation.evidence.items() if k != "sunum"
                    }
                    delivery_store.record_assistant(outcome.final_text, message_id=identifier)
            else:
                delivery_store.record_assistant(outcome.final_text, message_id=identifier)
        elif presentation.compact and delivered_evidence is not None:
            delivered_evidence = {k: v for k, v in delivered_evidence.items() if k != "sunum"}
        # Boş metinle "başarısız" dönmek kullanıcıya hiçbir şey söylemez.
        metin = delivered_text
        if not metin.strip() and not outcome.ok:
            metin = (
                turn_stopped_summary(outcome.stop_reason, outcome.todos)
                if outcome.budget_stopped
                else messages.APP_TURN_NO_ANSWER
            )
            # Özet de "ne oldu" kaydıdır: sekme yeniden açıldığında "devam et"
            # turunun modeli neyin kaldığını buradan görür.
            if delivery_store is not None:
                delivery_store.record_assistant(
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
            # Geçmiş (`turn_state.history`) taşındığı için model kaldığı yeri bilir.
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
                delivery_owner_snapshot=delivery_owner_snapshot,
                accepted_snapshot=accepted,
            )
            if receipt is not None:
                continued["_retry_safe"] = False
            return {**root_payload, **continued}
        cron_store.save(turn_state.config.memory_dir, accepted.conversation_id, turn_state.cron)
        self._goal_turn_id = receipt.attempt_id if receipt else None
        try:
            goal_payload = (
                await self._evaluate_goal(sink, accepted=accepted)
                if self._accepted_is_visible(accepted)
                else {}
            )
        finally:
            self._goal_turn_id = None
        if switched:
            metin = f"{metin}\n\n{switched}".strip()
        cevap: dict[str, Any] = {
            "ok": outcome.ok,
            "metin": metin,
            **root_payload,
            **goal_payload,
        }
        if not browser_only and code_review_findings.is_findings_turn(task):
            # `/code-review` bulguları kart olarak (Claude Code ReportFindings, #214).
            cevap.update(findings_payload(metin))
        if receipt is not None:
            cevap["_retry_safe"] = (
                getattr(outcome, "tool_calls_made", None) == 0
                and getattr(outcome, "tool_uses", None) == ()
                and effect_sink.permits_retry(outcome_entry, retry_prefix)
            )
        if delivered_evidence is not None:
            cevap["kanit"] = delivered_evidence
        # Onay kartındaki "bir daha sorma" kuralı yazıldı/yazılamadı bildirimi (P-003).
        for notice in turn_state.approval_memory.take_notices():
            self._note_persist_warning(messages.PERMISSION_RULE_SAVED.format(summary=notice))
        return {**cevap, **self._take_persist_warning()}

    async def _evaluate_goal(
        self, sink: EventSink, *, accepted: _AcceptedTurn | None = None
    ) -> dict[str, Any]:
        """`/goal` etkinse turu değerlendir (P-058); sonuç `hedef`/`hedef_devam` alanlarıdır.

        Devam turunu arayüz gönderir (`hedef_devam`): her tur sohbette ayrı cevap olarak
        görünür ve Durdur düğmesi zinciri keser. Devam turu hedef kipinde koşar.
        """
        state = accepted.state if accepted is not None else self._state
        original_goal = state.goal
        if state.goal is None or not state.goal.is_active:
            return {}
        sink.handle(StatusChanged(messages.GOAL_JUDGING))
        task = asyncio.ensure_future(
            goal_flow.evaluate_goal(state, publisher=goal_flow.SinkPublisher((sink,)))
        )
        self._goal_task = task
        try:
            outcome = await task
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            # Kullanıcı Durdur'a bastı: hedef etkin kalır, devam turu üretilmez.
            return {"hedef": {"eylem": "durduruldu", "metin": messages.GOAL_STOPPED}}
        finally:
            self._goal_task = None
        # Ölçüldü (31 Ekim): burada `_next_turn_mode = GOAL` kuruluyordu; devamı göndermeyen
        # istemcide (Telegram) ya da sırada kullanıcı mesajı varken kip ilgisiz tura geçiyordu.
        if accepted is None or (
            self._accepted_is_visible(accepted) and self._state.goal is original_goal
        ):
            self._state.goal = state.goal
            self._goal_continuation = outcome.next_prompt if outcome is not None else None
        return goal_flow.wire_payload(outcome, state)

    def _goal_judging(self) -> bool:
        """Tur bitti ama hedef değerlendirmesi sürüyor: oturum meşgul sayılır."""
        return self._goal_task is not None and not self._goal_task.done()

    def _refresh_capabilities(self) -> None:
        # Kalıcı `capabilities.disabled` + oturumluk kapatmalar birlikte; ek kökler (P-051/052).
        # Tembel keşfedilen alt klasör becerileri yeniden kurulan deftere taşınır (ölçüldü
        # 31 Ekim: yenilemeden sonra kayboluyordu).
        nested = self._state.capabilities.nested_roots if self._state.capabilities else ()
        self._state.capabilities = registry_from_config(
            self._state.config,
            self._state.home,
            self._state.root,
            extra_roots=self._state.extra_roots,
            session_disabled_skills=frozenset(self._disabled_skills),
            session_disabled_agents=frozenset(self._disabled_agents),
        )
        self._state.capabilities.add_nested_roots(nested)
        self._all_capabilities = self._all_capabilities.with_extra_roots(self._state.extra_roots)

    async def _extension_rpc(self, name: str, data: Mapping[str, Any]) -> dict[str, Any]:
        context = ExtensionContext(self._state.root, self._home, self._state.config)
        result = await dispatch_extension(name, data, context)
        if result.config is not None:
            from ..mcp_bridge import pool

            # Kapatılan/kaldırılan eklentinin MCP süreci beklemeden kapanır (P-059).
            for server in result.dropped:
                await pool.drop_mcp_connection(server)
            self._update_connector_config(result.config)
        if result.payload.get("yenile") is True:
            self._reload_capabilities()
        return result.payload

    def _catalog_registry(self) -> CapabilityRegistry:
        """Masaüstü katalog defteri; ajanın turda keşfettiği alt klasör becerileri dahil (P-052)."""
        if self._state.capabilities is not None:
            self._all_capabilities.add_nested_roots(self._state.capabilities.nested_roots)
        return self._all_capabilities

    def _reload_capabilities(self) -> dict[str, Any]:
        """`yetenek.yenile`: kataloğu diskten yeniden tara."""
        self._all_capabilities.invalidate()
        self._refresh_capabilities()
        return {
            "ok": True,
            "beceri": len(self._all_capabilities.skills()),
            "ajan": len(self._all_capabilities.agents()),
        }

    def _diagnose_capabilities(self) -> dict[str, Any]:
        """`yetenek.teshis`: eksik açıklama, kopya ad, uzun gövde gibi bulgular."""
        from ..engines.agent.skill_cost_report import render_cost_report, skill_costs
        from ..tools.capability_doctor import diagnose, render_report

        bulgular = diagnose(self._all_capabilities)
        # `/skill-doctor` (#177): beceri başına bağlam maliyeti ve kullanım sıklığı.
        maliyet = skill_costs(self._all_capabilities, self._state.config.memory_dir)
        return {
            "ok": True,
            "bulgular": [
                {
                    "tur": b.kind,
                    "ad": b.name,
                    "onem": b.severity,
                    "ayrinti": b.detail,
                    "yol": b.path,
                }
                for b in bulgular
            ],
            "maliyet": [
                {
                    "ad": c.name,
                    "kaynak": c.source,
                    "liste_belirtec": c.listing_tokens,
                    "govde_belirtec": c.body_tokens,
                    "cagri": c.uses,
                }
                for c in maliyet
            ],
            "metin": render_cost_report(maliyet)
            + "\n\n"
            + render_report(
                bulgular,
                skills=len(self._all_capabilities.skills()),
                agents=len(self._all_capabilities.agents()),
            ),
        }

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
        # `context: fork` beceri (P-054): arayüz "tur alt ajanda koşacak" diyebilsin.
        skill = self._all_capabilities.get_skill(name) if kind == "beceri" else None
        fork = bool(skill is not None and getattr(skill, "context", "") == "fork")
        return {"ok": True, "tur": kind, "ad": name, "sonraki_tur": True, "fork": fork}

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
            if getattr(item, "context", "") == "fork":
                self._fork_requested = True
                if not self._state.pending_fork_agent:
                    self._state.pending_fork_agent = getattr(item, "agent", "")
            self._queue_skill_turn_settings(item)
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

    def _queue_skill_turn_settings(
        self, item: Capability, *, state: ReplState | None = None
    ) -> None:
        """Katalogdan seçilen becerinin `model`/`effort`/`disallowed-tools` alanları (P-020).

        Slash yolu (`/beceri`) bunları zaten bekleyen eklere koyar; slash seçimi önceliklidir.
        """
        state = state or self._state
        if state.pending_model_choice.is_empty:
            resolution = resolve_turn_model(
                item.model, item.effort, allow_model=model_override_allowed(state, item)
            )
            state.pending_model_choice = resolution.choice
        state.pending_denied_tools = state.pending_denied_tools | map_denied_tools(
            item.disallowed_tools
        )
        # `allowed-tools` ön onayı ve `disallowed-tools` deseni bu turun izin kuralı (#142).
        from ..engines.agent.skill_tool import grant_entries

        state.pending_grants = (
            *state.pending_grants,
            *grant_entries(item, state.root),
        )

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
                    "code": "reference_invalid",
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
        # Oturum defterinden çık (P-060): kapanan masaüstü oturumu mesaj almaz.
        close_link(self._state)
        if self._image_jobs is not None:
            self._image_jobs.stop_accepting()
        images = tuple(self._image_tasks)
        for image in images:
            if not image.done() and not image.cancelling():
                image.cancel()
        selections = tuple(self._model_selection_tasks)
        if selections:
            # Takılı NIM doğrulamasını (90 sn'ye kadar) kapanışta uzun bekleme (S2-22).
            _done, pending = await asyncio.wait(selections, timeout=MODEL_SELECTION_CLOSE_WAIT_S)
            for stuck in pending:
                stuck.cancel()
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
        await self._state.child_runs.close()
        # Arka plana alınmış `!` komutları oturumla kapanır (#218).
        self._state.shell_jobs.kill_all()
        if self._child_runs is not None and self._child_runs is not self._state.child_runs:
            await self._child_runs.close()
        await self._voice_background.close()
        if self._idle_watch is not None:
            from ..cli.repl import hook_events

            await hook_events.stop_idle_watch(self._idle_watch)
            self._idle_watch = None
        if self._state.hook_session is not None:
            # SessionEnd kancası (P-009): yalnız başlamış (en az bir tur koşmuş) oturumda.
            await self._state.hook_session.end("other")
        self._report_voice_background_failures()
        if self._voice_preparations:
            await asyncio.gather(*self._voice_preparations, return_exceptions=True)
            self._voice_preparations.clear()
        voice_stop()
        discard_prepared_voice()
        if images:
            await asyncio.gather(*images, return_exceptions=True)
        # Adımlar bağımsız sahiplik taşır: biri hata verse de kalan kapanış sürer
        # (yoksa tarayıcı süreçleri ve uzak sunucu yetim kalırdı). İlk hata sonda yükselir.
        steps: list[Callable[[], Any]] = [
            *([self._image_jobs.close] if self._image_jobs is not None else []),
            self._submission_store.close,
        ]
        for task in self._panel_tasks.values():
            if not task.done():
                task.cancel()
        self._panel_tasks.clear()
        steps += [
            close_mcp_pool,
            self._mcp_connections.close,
            # Claude in Chrome: çıkışta sekme grubu yalnız boş yeni sekmelerdense kapanır (#436).
            lambda: self._chrome.close_tab_group(only_empty=True),
            self._chrome.close,
            self._processes.close,
            self._browser_panel.close,
            close_all_browser_sessions,
            stop_all_login_processes,
            *([self._remote.aclose] if self._remote is not None else []),
            self.pending.cancel_all,
        ]
        errors: list[Exception] = []
        for step in steps:
            try:
                result = step()
                if inspect.isawaitable(result):
                    await result
            except Exception as error:
                logging.getLogger(__name__).error("Oturum kapanış adımı başarısız: %s", error)
                errors.append(error)
        if errors:
            raise errors[0]


def _notify_auth(session: AppSession, server: str) -> None:
    from ..engines.hooks.notify import notify_auth_success

    notify_auth_success(session._state.hooks(), server)


def _leftover_steering(queue: SteeringQueue | None) -> list[str]:
    """Tur sonunda tüketilmemiş yönlendirme metinleri (#190)."""
    from ..core.steering import steering_text

    if queue is None:
        return []
    return [text for message in queue.drain() if (text := steering_text(message))]

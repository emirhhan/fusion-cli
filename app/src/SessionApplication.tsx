import { createVoicePlayback } from "./voice/voicePlayback";
import { localVoiceReply } from "./voice/localVoice";
import { closeUnfinishedAgents } from "./team/ekipOlaylari";
import { AgentPanel, agentCardsForMessages } from "./team/AgentPanel";
import type { TeamCardsProps } from "./team/TeamCards";
import { operationResult, errorMessage, type CommandResult } from "./protocol/result";
import { submissionAccepted, type SubmissionResult } from "./sessions/submission";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Approval } from "./dialogs/Approval";
import { CloseConfirm } from "./dialogs/CloseConfirm";
import { useKapatmaNabzi } from "./dialogs/closeHeartbeat";
import { osBildirimiGonder } from "./notifications/osNotice";
import { ShareDialog } from "./dialogs/ShareDialog";
import { HistoryPicker } from "./dialogs/HistoryPicker";
import { NewTaskDialog } from "./dialogs/NewTaskDialog";
import {
  CommandSelector,
  type CommandSelectorPayload,
} from "./dialogs/CommandSelector";
import { useHistory } from "./history/useHistory";
import { ProtocolClient } from "./protocol/client";
import { olayEkle } from "./protocol/olayAkisi";
import type { Soru } from "./protocol/types";
import { useProjectRegistry } from "./sessions/useProjectRegistry";
import { createAndOpenProject, openProjectChat, ProjectOpenError } from "./sessions/projectActions";
import { useRemoteProjectSync } from "./remote/useRemoteProjectSync";
import { useSessions, nextSessionId, saveWorkspaceMode, tauriSessionTransport } from "./sessions/useSessions";
import { usePrefsMirror } from "./platform/usePrefsMirror";
import { useSessionModes } from "./sessions/useSessionModes";
import type { SessionTransport } from "./sessions/types";
import { AppHeader, BAGLANTI_KESILDI_DURUMU } from "./screens/AppHeader";
import {
  Composer,
  type ApprovalMode,
  type ComposerAttachment,
  type ComposerCommand,
  type DosyaOnerisi,
  type McpSunucusu,
} from "./screens/Composer";
import { Conversation, type Mesaj } from "./screens/Conversation";
import type { ModelOption } from "./screens/ModelPicker";
import { useModelCatalog } from "./screens/useModelCatalog";
import { useActiveModel } from "./screens/useActiveModel";
import { EmptyState } from "./screens/EmptyState";
import { Inspector, type InspectorTabId } from "./screens/Inspector";
import { Shell } from "./screens/Shell";
import { Sidebar } from "./screens/Sidebar";
import { useLayout } from "./state/useLayout";
import { useInspectorLayout } from "./state/useInspectorLayout";
import { useNavigationHistory } from "./state/useNavigationHistory";
import {
  applyTheme,
  readThemePreference,
  saveThemePreference,
  type ThemePreference,
} from "./theme/theme";
import { FileExplorer } from "./workspace/FileExplorer";
import { ChangesPanel } from "./workspace/ChangesPanel";
import { TestsPanel } from "./workspace/TestsPanel";
import { PreviewPanel } from "./workspace/PreviewPanel";
import { TerminalPanel } from "./processes/TerminalPanel";
import { useProcesses } from "./processes/useProcesses";
import { SkillsCatalog } from "./capabilities/SkillsCatalog";
import { ControlPanel } from "./control/ControlPanel";
import { useUpdateAvailable } from "./control/useUpdateAvailable";
import { ConnectorsScreen } from "./connectors/ConnectorsScreen";
import { HelpScreen } from "./help/HelpScreen";
import { Notification, insanDogrulamasiGerekiyor } from "./notify/Notification";
import { Settings } from "./settings/Settings";
import { useShowSteps } from "./settings/useShowSteps";
import { useInspectorPlacement } from "./settings/useInspectorPlacement";
import { desktopDir } from "@tauri-apps/api/path";
import { DepoUyarisi } from "./workspace/DepoUyarisi";
import { ProjectPicker } from "./screens/ProjectPicker";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import {
  kabukVar,
  onVoiceBargeIn,
  createVoiceMessageDeduper,
  onVoiceMessage,
  onVoiceAnswer,
  onVoicePrefsRequest,
  publishVoiceAsk,
  publishVoicePrefs,
  publishVoiceRuntimeState,
  type VoicePrefsPayload,
} from "./voice/bridge";
import { openVoiceWindow } from "./voice/windowBridge";
import { buildVoiceRequest, type VoiceTurnHandle } from "./voice/voiceTurn";
import { AccountGate } from "./account/AccountGate";
import { AccountScreen } from "./account/AccountScreen";
import { useAccount } from "./account/useAccount";
import { ConnectedOnboarding } from "./onboarding/ConnectedOnboarding";
import { clearProgress } from "./onboarding/persistence";
import type { SampleProject } from "./onboarding";
import { selectDirectory, selectFiles as selectLocalFiles } from "./platform/dialog";
import { PermissionPrompt } from "./permissions/PermissionPrompt";
import { usePermissions } from "./permissions/usePermissions";
import { useDictation } from "./voice/useDictation";
import { desktopPermissionKind, hasSettingsLink, type PermissionBridge } from "./permissions/types";
import { nativePermissionBridge } from "./platform/permissions";
import { listenForFileDrops } from "./platform/drop";
import { FeedbackDialog } from "./feedback/FeedbackDialog";
import { ImageCreate } from "./imagecreate/ImageCreate";
import { MainRail, type MainSection } from "./screens/MainRail";
import { MainSurface, type SurfaceSection } from "./sections/MainSurface";
import { MediaScreen } from "./sections/MediaScreen";
import { KitsScreen } from "./kits/KitsScreen";
import type { ScheduleDeliveryClient } from "./schedule/types";
import { LibraryScreen } from "./library/LibraryScreen";
import { ScheduleScreen } from "./schedule/ScheduleScreen";
import { pickScheduleClient } from "./schedule/pickScheduleClient";
import { useScheduleRunner } from "./schedule/useScheduleRunner";
import { useSchedulerCore } from "./schedule/useSchedulerCore";
import type { ReportInput } from "./feedback/report";
import { useCrashReporter } from "./feedback/useCrashReporter";
import { DEFAULT_SKILL_TASK, isImageCommand, parseCapabilityInput } from "./screens/capabilityInput";
import { attachmentsFromDroppedFiles, isFolderCommand, startsWithFilePath } from "./slashRouting";
import { readStorage, writeStorage } from "./platform/storage";

/** Sohbetin içinden çalışma klasörünü değiştiren komut. */
const FOLDER_COMMAND = {
  ad: "klasor",
  aciklama: "Çalışma klasörünü değiştir",
  destekleniyor: true,
  grup: "Çalışma alanı",
  kullanim: "/klasor",
};

const LAST_ROOT_KEY = "fusion.last-project-root";
/** Webview deposu güvenilmez olabilir (özel pencere, kota): okuma hatası "kayıt yok" sayılır (U3-32). */
function readLastRoot(): string | undefined {
  const sonuc = readStorage(() => localStorage, LAST_ROOT_KEY);
  return sonuc.ok ? sonuc.value ?? undefined : undefined;
}

function attachmentFromPath(path: string): ComposerAttachment {
  return {
    kind: /\.(avif|gif|jpe?g|png|svg|webp)$/i.test(path) ? "image" : "file",
    name: path.split(/[\\/]/).filter(Boolean).slice(-1)[0] ?? path,
    path,
  };
}

function attachmentsFromPaths(paths: string[]): ComposerAttachment[] {
  return paths
    .filter((path) => typeof path === "string" && path.trim().length > 0)
    .map(attachmentFromPath);
}

function commandSelectorFrom(value: unknown): CommandSelectorPayload | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const continuation = row.devam as Record<string, unknown> | undefined;
  if (
    typeof row.adim !== "string" ||
    !["secim", "metin", "gizli_metin"].includes(String(row.tur)) ||
    typeof row.baslik !== "string" ||
    !continuation ||
    typeof continuation.komut !== "string" ||
    typeof continuation.arguman_on_eki !== "string"
  ) return null;
  return value as CommandSelectorPayload;
}

function useConversation(client: ProtocolClient) {
  const [messages, setMessages] = useState<Mesaj[]>([]);
  const [question, setQuestion] = useState<{ id: string; data: Soru } | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    void client.request("oturum.durum", {}).catch(() => undefined);
    client.onEvent((event) => {
      if (event.olay === "SoruKapandi") {
        setQuestion((current) => (current?.id === event.id ? null : current));
        return;
      }
      setMessages((current) => olayEkle(current, event));
    });
    client.onQuestion((id, data) => {
      if (data.tur === "onay") setQuestion({ id, data: data as unknown as Soru });
    });
  }, [client]);

  const send = (task: string) => {
    setRunning(true);
    setMessages((current) => [...closeUnfinishedAgents(current), { rol: "kullanici", metin: task }]);
    void client
      .request("tur.calistir", { gorev: task })
      .then((result) => {
        const text = typeof result.metin === "string" ? result.metin : "";
        if (text) setMessages((current) => [...current, { rol: "asistan", metin: text }]);
      })
      .catch((error) =>
        setMessages((current) => [...current, { rol: "asistan", metin: `Hata: ${String(error)}`, hata: true }]),
      )
      .finally(() => setRunning(false));
  };
  const stop = () => {
    void client.request("tur.kes", {}).catch(() => undefined);
    setRunning(false);
  };
  const answer = (data: Record<string, unknown>) => {
    if (question) client.reply(question.id, data);
    setQuestion(null);
  };
  const clear = () => {
    setMessages([]);
    setQuestion(null);
    setRunning(false);
  };
  return { answer, clear, messages, question, running, send, stop };
}

/** Yalnız `request` gerekir; kanca taşıma tipine bağlı olmamalı. */
export type TemaIstemcisi = Pick<ProtocolClient, "request">;

/** Test edilebilirlik için dışa açık: bkz. `SessionApplication.theme.test.tsx`. */
export function useAppTheme(client?: TemaIstemcisi) {
  const [themePreference, setThemePreference] = useState<ThemePreference>(readThemePreference);
  // Yapılandırma BİR KEZ okunur (bkz. aşağıdaki efekt). `client` her aktif
  // sekme değişiminde YENİ bir referanstır — her sekme kendi çekirdek
  // sürecidir ve süreç KENDİ başlangıcında okuduğu yapılandırmanın bellek
  // içi bir kopyasını taşır. Efekt eskiden `[client]` her değiştiğinde
  // yeniden okuyordu: sekme A'da tema koyu iken sekme B (başka bir zamanda
  // başlamış, hâlâ eski/açık değeri bellekte tutan bir süreç) açılınca genel
  // (`document.documentElement`) tema B'nin BAYAT tercihine dönüyordu — tema
  // sohbet başına davranıyormuş gibi görünüyordu, oysa GLOBAL olmalı.
  const yapilandirmaOkundu = useRef(false);

  const syncWindowColor = (theme: "light" | "dark") => {
    if (!("__TAURI_INTERNALS__" in window)) return;
    void import("@tauri-apps/api/window")
      .then(({ getCurrentWindow }) => getCurrentWindow().setBackgroundColor(
        theme === "dark" ? [17, 17, 17] : [249, 249, 250],
      ))
      .catch((error: unknown) => console.warn("Pencere çerçeve rengi ayarlanamadı", error));
  };

  // Tercih YAPILANDIRMADAN okunur; `localStorage` yalnız ilk boyamayı hızlandıran
  // önbellektir. Ölçüldü (11 Eylül): webview'in LocalStorage deposu kullanıcının
  // kurulumunda hiç yazılmıyordu (0 bayt) ve yazma hatası yutulduğu için tercih
  // her açılışta `system`'e düşüyor, macOS koyu temadayken içerik beyaz kalıyordu.
  useEffect(() => {
    // Yalnız İLK kullanılabilir istemciden, uygulama başına BİR KEZ okunur —
    // sonraki sekme değişimleri (`client` değişse bile) tekrar tetiklemez.
    if (!client || yapilandirmaOkundu.current) return;
    yapilandirmaOkundu.current = true;
    let iptal = false;
    void (async () => {
      try {
        const sonuc = (await client.request("ayar.tema", {})) as { ok?: boolean; tema?: string };
        const tema = sonuc?.tema;
        if (!iptal && sonuc?.ok && (tema === "system" || tema === "light" || tema === "dark")) {
          setThemePreference(tema);
          saveThemePreference(tema);
        }
      } catch {
        // Yapılandırma okunamazsa önbellekteki tercihle devam edilir; bayrak açılır ki
        // sonraki istemci (yeniden bağlanma) bir kez daha denesin (U3-33).
        if (!iptal) yapilandirmaOkundu.current = false;
      }
    })();
    return () => {
      iptal = true;
    };
  }, [client]);

  useEffect(() => {
    syncWindowColor(applyTheme(themePreference));
    if (themePreference !== "system" || !window.matchMedia) return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => syncWindowColor(applyTheme("system", document.documentElement, media.matches));
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, [themePreference]);

  const changeTheme = (preference: ThemePreference) => {
    saveThemePreference(preference);
    setThemePreference(preference);
    // Kalıcılık yapılandırmadadır; hata sessizce yutulmaz, konsola düşer.
    void client?.request("ayar.tema_kaydet", { tema: preference }).catch((error: unknown) => {
      console.error("Tema kaydedilemedi", error);
    });
  };
  return { changeTheme, themePreference };
}

function projectName(root: string): string {
  const parts = root.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] ?? root;
}

/** Sayfa başlığını kendi içinde `PageHeader` ile gösteren tam ekran sayfalar. */
const SAYFA_KENDI_BASLIGINI_TASIR = ["settings", "control", "connectors", "account"];

/** Ana uygulamanın gezinebileceği sayfalar; üst çubuktaki geri/ileri
 * düğmeleri bu sayfalar arasındaki geçmişi gezer (bkz. `useNavigationHistory`). */
type Page =
  | "chat"
  | "skills"
  | "control"
  | "connectors"
  | "help"
  | "settings"
  | "account"
  | "image-create"
  | "video-create";

function ProjectInspector({
  activeTab,
  client,
  collapsed,
  height,
  onActiveTabChange,
  onCollapsedChange,
  onHeightChange,
  onSelectPath,
  onWidthChange,
  placement,
  root,
  selectedPath,
  width,
  requestedPreview = null,
  agents,
}: {
  activeTab: InspectorTabId;
  client: ProtocolClient;
  collapsed: boolean;
  height: number;
  onActiveTabChange: (tab: InspectorTabId) => void;
  onCollapsedChange: (collapsed: boolean) => void;
  onHeightChange: (height: number) => void;
  /** Seçili dosya DIŞARIDAN yönetilir: sohbetteki kod kartı da bir dosya açar. */
  onSelectPath: (path: string | null) => void;
  onWidthChange: (width: number) => void;
  placement: "right" | "bottom";
  root: string;
  selectedPath: string | null;
  width: number;
  requestedPreview?: { url: string; seq: number } | null;
  agents?: TeamCardsProps;
}) {
  const [revision, setRevision] = useState(0);
  const processes = useProcesses(client);
  const changed = () => setRevision((current) => current + 1);
  useEffect(() => client.onEvent((event) => {
    const modifyingTools = new Set(["write_file", "edit_file", "multi_edit", "replace_range"]);
    if (
      event.olay === "FilesChanged" ||
      (event.olay === "ToolExecuted" && event.outcome === "ok" &&
        typeof event.name === "string" && modifyingTools.has(event.name))
    ) changed();
  }), [client]);
  return (
    <Inspector
      activeTab={activeTab}
      collapsed={collapsed}
      height={height}
      onActiveTabChange={onActiveTabChange}
      onCollapsedChange={onCollapsedChange}
      onHeightChange={onHeightChange}
      onWidthChange={onWidthChange}
      placement={placement}
      width={width}
      content={{
        agents: <AgentPanel ajanlar={agents?.ajanlar ?? []} canli={agents?.canli ?? false} onCancel={agents?.onCancel} />,
        files: <FileExplorer client={client} key={root} onChanged={changed} onSelected={onSelectPath} root={root} revision={revision} />,
        // Doğrulama komutları DEĞİŞİKLİKLER sekmesinde: "ne değişti" ile
        // "hâlâ çalışıyor mu" aynı soruya bakar. Ayrı 'Testler' sekmesi git
        // durumunu ikinci kez gösteriyordu.
        changes: (
          <>
            <ChangesPanel client={client} onChanged={changed} revision={revision} />
            <TestsPanel client={client} processes={processes} revision={revision} />
          </>
        ),
        terminal: <TerminalPanel cwd={root} />,
        preview: (
          <PreviewPanel client={client} requestedUrl={requestedPreview} selectedPath={selectedPath} revision={revision} />
        ),
      }}
    />
  );
}

export function Uygulama({ istemci }: { istemci: ProtocolClient }) {
  const conversation = useConversation(istemci);
  const layout = useLayout();
  const inspectorLayout = useInspectorLayout();
  const preferredInspectorPlacement = useInspectorPlacement();
  const inspectorPlacement = inspectorLayout.activeTab === "agents" ? "right" : preferredInspectorPlacement;
  const [draft, setDraft] = useState("");
  const showSteps = useShowSteps();
  // Tema yalnız UYGULANIR; değiştirme Ayarlar ekranındadır.
  useAppTheme(istemci);
  const clear = () => {
    setDraft("");
    conversation.clear();
  };
  const content = conversation.messages.length > 0 ? (
    <Conversation mesajlar={conversation.messages} running={conversation.running} showSteps={showSteps} />
  ) : (
    <EmptyState onSelectPrompt={setDraft} />
  );

  return (
    <Shell
      composer={
        <Composer
          onSend={conversation.send}
          onStop={conversation.stop}
          onValueChange={setDraft}
          running={conversation.running}
          value={draft}
        />
      }
      content={
        <>
          {content}
          {conversation.question && (
            <Approval key={conversation.question.id} onCevap={conversation.answer} soru={conversation.question.data} />
          )}
        </>
      }
      header={
        <AppHeader
          inspectorOpen={layout.inspectorOpen}
          onToggleInspector={layout.toggleInspector}
          onToggleSidebar={layout.toggleSidebar}
          sidebarCollapsed={layout.sidebarCollapsed}
          status={conversation.running ? "Çalışıyor" : "Hazır"}
          title="Yeni görev"
        />
      }
      inspector={
        <Inspector
          content={{ agents: <AgentPanel ajanlar={agentCardsForMessages(conversation.messages)} canli={conversation.running} /> }}
          activeTab={inspectorLayout.activeTab}
          collapsed={inspectorLayout.collapsed}
          height={inspectorLayout.height}
          onActiveTabChange={inspectorLayout.setActiveTab}
          onCollapsedChange={inspectorLayout.setCollapsed}
          onHeightChange={inspectorLayout.setHeight}
          onWidthChange={inspectorLayout.setWidth}
          placement={inspectorPlacement}
          width={inspectorLayout.width}
        />
      }
      inspectorCollapsed={inspectorLayout.collapsed}
      inspectorHeight={inspectorLayout.height}
      inspectorOpen={layout.inspectorOpen}
      inspectorPlacement={inspectorPlacement}
      inspectorWidth={inspectorLayout.width}
      onInspectorClose={layout.closeInspector}
      onSidebarClose={layout.toggleSidebar}
      sidebar={
        <Sidebar
          collapsed={layout.sidebarCollapsed}
          etkin={null}
          onSec={() => undefined}
          onYeni={clear}
          oturumlar={[]}
        />
      }
      sidebarCollapsed={layout.sidebarCollapsed}
    />
  );
}


export function SessionUygulama({
  transport,
  onboarding = false,
  runtimeVersion,
  onOnboardingComplete = () => undefined,
  selectFolder = selectDirectory,
  selectFiles = selectLocalFiles,
  permissionBridge = nativePermissionBridge,
}: {
  transport?: SessionTransport;
  onboarding?: boolean;
  runtimeVersion?: string;
  onOnboardingComplete?: () => void;
  selectFolder?: (defaultPath?: string) => Promise<string | null>;
  selectFiles?: (defaultPath?: string) => Promise<string[]>;
  permissionBridge?: PermissionBridge;
}) {
  const permissions = usePermissions(permissionBridge);
  const controller = useSessions(transport);
  const projects = useProjectRegistry(nextSessionId);
  const [accountHost, setAccountHost] = useState<HTMLDivElement | null>(null);
  const layout = useLayout();
  const inspectorLayout = useInspectorLayout();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [attachments, setAttachments] = useState<Record<string, ComposerAttachment[]>>({});
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [commandSelector, setCommandSelector] = useState<CommandSelectorPayload | null>(null);
  const [controlRevision, setControlRevision] = useState(0);
  /** Beceri/MCP kataloğu değişmiş olabilir; slash menüsü listeleri yeniden okunur. */
  const [capabilityRevision, setCapabilityRevision] = useState(0);
  const [commandBusy, setCommandBusy] = useState(false);
  const [commandError, setCommandError] = useState<string | null>(null);
  const [commands, setCommands] = useState<ComposerCommand[]>([]);

  const [fileSuggestions, setFileSuggestions] = useState<DosyaOnerisi[]>([]);
  // `/beceri` ve `@mcp` girdileri için etkin katalog adları.
  const [skillNames, setSkillNames] = useState<string[]>([]);
  const [mcpServers, setMcpServers] = useState<McpSunucusu[]>([]);
  //: En son gönderilen `@` sorgusunun sırası. Geç gelen cevap yenisini EZMEZ:
  //: kullanıcı yazmaya devam ettiğinde eski sorgunun sonucu listeyi geri almamalı.
  const fileQuerySeq = useRef(0);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  //: Açık rapor penceresi; `null` kapalı. Hata akışından gelirse ayrıntıyı taşır.
  const [feedback, setFeedback] = useState<Partial<ReportInput> | null>(null);
  const [crash, clearCrash] = useCrashReporter();
  const [newTaskOpen, setNewTaskOpen] = useState(false);
  const [newTaskBusy, setNewTaskBusy] = useState(false);
  const folderPickVersion = useRef(0);
  const [newTaskError, setNewTaskError] = useState<string | null>(null);
  // Sayfa geçişleri bir geçmiş yığınında tutulur: üst çubuktaki geri/ileri
  // düğmeleri `setPage` çağıran TÜM mevcut yerlerle (aşağıda) değişmeden
  // çalışır — `push` aynı imzayı taşır, yalnız kaynağı `useState` değil bu
  // yığındır.
  const pageHistory = useNavigationHistory<Page>("chat");
  const page = pageHistory.current;
  const setPage = pageHistory.push;
  // En soldaki ana menü. Home ve Görsel/Video kabuğun içindeki sayfalardır;
  // diğer üç bölüm tüm yüzeyi kaplar ve sayfa geçmişine girmez.
  const [surfaceSection, setSurfaceSection] = useState<SurfaceSection | null>(null);
  const mediaPage = page === "image-create" || page === "video-create";
  const mainSection: MainSection = surfaceSection ?? (mediaPage ? "media" : "home");
  const [settingsSection, setSettingsSection] = useState<"genel" | "kisisellestirme">("genel");
  // "Ayarlar" ve "Kontrol Paneli" aynı ekranı açar; başlık hangi kapıdan
  // girildiğini söyler, yoksa kullanıcı yanlış yere gittiğini sanıyordu.
  const [controlTitle, setControlTitle] = useState("Kontrol Paneli");
  // Seçili dosya BURADA durur: hem çalışma panelindeki ağaç hem sohbetteki
  // kod kartı aynı seçimi değiştirir.
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  // Ajanın çalıştırdığı site (`PreviewReady`): önizleme panelinde açılır.
  const [requestedPreview, setRequestedPreview] = useState<{ url: string; seq: number } | null>(null);
  const showSteps = useShowSteps();
  // İzin modu arayüzde GERÇEK durumu göstermeli: eskiden "Agent · Otomatik"
  // sabit yazıyordu ve security'ye geçince bile değişmiyordu.
  const [busySubmissionMode, setBusySubmissionMode] = useState<"steer" | "queue">("steer");
  const [closeAsked, setCloseAsked] = useState(false);
  // Soru açıkken Rust'a nabız gider; arayüz donarsa kapanış onaysız sürer (R2-14).
  useKapatmaNabzi(closeAsked && kabukVar());
  /** Çekirdek bağlantısı koptuğunda çekirdeğin son hata çıktısı (varsa). */
  const [cekirdekGunlugu, setCekirdekGunlugu] = useState<string | null>(null);
  /** Çökme bildirimi kapatılan konuşma; aynı çökme bir daha gösterilmez. */
  const [cokmeKapatilan, setCokmeKapatilan] = useState<string | null>(null);
  const [showOnboarding, setShowOnboarding] = useState(onboarding);
  const [voicePlaybackRevision, setVoicePlaybackRevision] = useState(0);
  const voiceRequests = useRef<{
    afterIndex: number;
    requestId: string;
    sawRunning: boolean;
    sessionId: string;
  }[]>([]);
  const activeVoiceTurn = useRef<VoiceTurnHandle | null>(null);
  const manualVoiceTurn = useRef<VoiceTurnHandle | null>(null);
  const manualVoiceGeneration = useRef(0);
  const pendingBargeIn = useRef(false);
  const active = controller.activeSession;
  useRemoteProjectSync(active?.client ?? null, projects.registry);
  const activeSessionId = active?.id;
  const activeClient = active?.client;
  useEffect(() => () => {
    manualVoiceGeneration.current += 1;
    void manualVoiceTurn.current?.cancel().catch(() => undefined);
  }, [activeSessionId]);
  usePrefsMirror(activeClient);
  // Bir masaüstü aracı izin yüzünden düşünce çekirdek `MasaustuIzinGerekli` yollar; izin kartı
  // açılır ve sistem istemi (Erişilebilirlik / Ekran Kaydı) Fusion.app adına tetiklenir (P-005).
  const ensurePermission = permissions.ensure;
  useEffect(() => {
    if (!activeClient) return;
    return activeClient.onEvent((event) => {
      if (event.olay !== "MasaustuIzinGerekli") return;
      const kind = desktopPermissionKind(event.tur);
      if (kind) void ensurePermission(kind);
    });
  }, [activeClient, ensurePermission]);
  const requestKitsHost = useCallback((name: string, data: Record<string, unknown>) => {
    if (!activeClient || !activeSessionId) return Promise.reject(new Error("Fusion oturumu yok."));
    return activeClient.request(name, data) as Promise<Record<string, unknown>>;
  }, [activeClient, activeSessionId]);
  const activeMessages = active?.messages;
  const activeRunning = active?.running;
  const commandOwner = useRef(0);
  const commandSequence = useRef(0);
  useEffect(() => {
    const generation = ++commandOwner.current;
    setCommandBusy(false); setCommandError(null);
    return () => { commandOwner.current = generation + 1; };
  }, [activeSessionId]);
  // İzin modu ve çalışma kipi sohbet başınadır; değişiklik çekirdek onaylayınca görünür.
  const { approval, workspaceMode, changeApproval, changeWorkspace } = useSessionModes(
    active ? { id: active.id, client: active.client } : null,
    setCommandError,
  );
  const dictation = useDictation((id, text) =>
    setDrafts((current) => ({ ...current, [id]: text })),
  );
  const dictationRef = useRef(dictation);
  dictationRef.current = dictation;
  useEffect(() => {
    if (dictationRef.current.listening) void dictationRef.current.stop();
  }, [activeSessionId]);
  // Hesap kapısı onboarding'den ÖNCE gelir: kimin kurulum yaptığı belli olmalı.
  const account = useAccount(active?.client ?? null);
  const etkinHesap =
    account.durum?.hesaplar.find((item) => item.kimlik === account.durum?.etkin) ?? null;
  const guncellemeSurumu = useUpdateAvailable();
  const preferredInspectorPlacement = useInspectorPlacement();
  const inspectorPlacement = inspectorLayout.activeTab === "agents" ? "right" : preferredInspectorPlacement;
  const [dogrulamaUyarisi, setDogrulamaUyarisi] = useState<string | null>(null);
  /** Devralınan konuşmada fark edilen hassas değer sayısı; bildirim şeridinde gösterilir. */
  const [gizliDegerSayisi, setGizliDegerSayisi] = useState(0);
  // Sağlayıcı insan doğrulaması isterse Fusion tek başına ilerleyemez. Bu,
  // sohbetin içine gömülü bir hata satırı olarak kayboluyordu; kullanıcı neden
  // durduğunu anlamıyordu. Artık kart olarak görünür ve eylem sunar.
  const sonAsistanMetni = [...(active?.messages ?? [])].reverse()
    .find((mesaj) => mesaj.rol === "asistan")?.metin ?? "";
  // Yedeğe geçen turda sebep yalnız olay satırındadır: seçili web oturumu
  // doğrulama isterken tur yedek modelle sürer ve cevap metni bunu söylemez.
  // Ölçüldü: kullanıcı 120 sn sonra yalnız "zaman aşımı" görüyordu.
  const sonOlayAyrintisi = [...(active?.messages ?? [])].reverse()
    .flatMap((mesaj) => mesaj.rol === "olay" ? [...(mesaj.adimlar ?? [])].reverse() : [])
    .find((adim) => adim.ayrinti && insanDogrulamasiGerekiyor(adim.ayrinti))?.ayrinti ?? "";
  useEffect(() => {
    if (insanDogrulamasiGerekiyor(sonAsistanMetni)) setDogrulamaUyarisi(sonAsistanMetni);
    else if (sonOlayAyrintisi) setDogrulamaUyarisi(sonOlayAyrintisi);
  }, [sonAsistanMetni, sonOlayAyrintisi]);
  const { changeTheme, themePreference } = useAppTheme(active?.client);
  const hasOpenedSession = useRef(false);
  useEffect(() => { if (active) hasOpenedSession.current = true; }, [active]);
  const startDesktopChat = async () => {
    setNewTaskError(null);
    try {
      const record = active ? projects.registry.projects.find((item) => item.id === projects.registry.chats[active.id]) : undefined;
      if (record) await openProjectChat(record, { createChat: controller.create, desktopRoot: desktopDir, assign: projects.assign });
      else await controller.create({ root: active?.root || await desktopDir() });
      setPage("chat");
    } catch (reason) {
      setNewTaskError(`Yeni sohbet açılamadı: ${reason instanceof Error ? reason.message : String(reason)}`);
    }
  };
  const history = useHistory(active?.client ?? null);
  const navigateSidebar = async (destination: string) => {
    setNewTaskError(null);
    if (destination !== "feedback") setSurfaceSection(null);
    if (destination === "feedback") {
      // Rapor penceresi oturum gerektirmez; boş uygulamada da açılır.
      setFeedback({ tur: "geri-bildirim" });
      return;
    }
    try {
      if (!active && destination !== "video-create" && !destination.startsWith("project:") && !destination.startsWith("project-id:")) {
        await controller.create({ root: await desktopDir() });
      }
            if (destination === "image-create" || destination === "video-create") {
              setPage(destination);
            } else if (destination === "skills") {
              setPage("skills");
            } else if (destination === "help") {
              setPage("help");
            } else if (destination === "settings") {
              setSettingsSection("genel");
              setPage("settings");
            } else if (destination === "personalization") {
              setSettingsSection("kisisellestirme");
              setPage("settings");
            } else if (destination === "control-panel") {
              setControlTitle("Kontrol Paneli");
              setPage("control");
            } else if (destination === "connectors") {
              setPage("connectors");
            } else if (destination === "account") {
              setPage("account");
            } else if (destination === "language") {
              // Dil tercihi Ayarlar'da yaşar; şimdilik tek dil var ve bunu
              // kullanıcıya orada açıkça söylüyoruz.
              setSettingsSection("genel");
              setPage("settings");

            } else if (destination === "new-project") {
              requestTaskFolder();

            } else if (destination.startsWith("resume:")) {
              setPage("chat");
              const source = destination.slice("resume:".length) as "claude" | "codex" | "hermes";
              setHistoryOpen(true);
              void history.openSource(source);
            } else if (destination.startsWith("project-id:")) {
              // Kayıtlı proje: sohbet klasörde (yoksa Desktop'ta) açılır ve projeye bağlanır.
              const record = projects.registry.projects.find((item) => item.id === destination.slice("project-id:".length));
              if (!record) throw new Error("Proje bulunamadı.");
              setPage("chat");
              await openProjectChat(record, { createChat: controller.create, desktopRoot: desktopDir, assign: projects.assign });
            } else if (destination.startsWith("project:")) {
              setPage("chat");
              await controller.create({ root: destination.slice("project:".length), mode: "kod" });
            }
    } catch (reason) {
      setNewTaskError(`Sayfa veya proje açılamadı: ${reason instanceof Error ? reason.message : String(reason)}`);
    }
  };
  // Manuel "Şimdi çalıştır" arka planda sohbet açar; kullanıcının o an
  // baktığı sohbet değişmez.
  const activeIdRef = useRef<string | null>(null);
  activeIdRef.current = active?.id ?? null;
  const createScheduledSession = useCallback(
    async (input: { mode: "kod"; root: string; title: string }) => {
      const previous = activeIdRef.current;
      const id = await controller.create(input);
      if (previous) controller.select(previous);
      return id;
    },
    [controller],
  );
  const [deliveryClient, setDeliveryClient] = useState<ScheduleDeliveryClient | null>(null);
  // Zamanlanmış tur onay isteyen araçta askıda bekler; kullanıcı yoksa sessizce ilerlemez, bildirilir (U5-57).
  const [scheduleNotice, setScheduleNotice] = useState<{ sessionId: string | null; kits?: boolean; baslik: string; metin: string } | null>(null);
  // Kits kuyruğuna teslim edilen görev de gözetimsiz çalışır: onay isteyen araçta askıda bekler, haber verilir.
  const notifyKitsApproval = useCallback(({ title, tool }: { title: string; tool: string }) => setScheduleNotice({
    sessionId: null,
    kits: true,
    baslik: "Kits'teki zamanlanmış görev onay bekliyor",
    metin: `"${title}" görevi "${tool}" için onay istiyor. Sen onaylayana kadar bekler; onaylamazsan ilerlemez.`,
  }), []);
  // Vade yoklaması hazır bir sohbetin çekirdeğini kullanır; hiç sohbet yoksa (son sekme kapatıldı,
  // geri yükleme başarısız) görünmez bir zamanlayıcı çekirdeği açılır (U5-52).
  const sessionScheduleClient = pickScheduleClient(active, controller.sessions);
  const detachedScheduleClient = useSchedulerCore({
    transport: transport ?? tauriSessionTransport,
    needed: sessionScheduleClient === null,
  });
  const scheduleClient = sessionScheduleClient ?? detachedScheduleClient;
  const scheduleRunner = useScheduleRunner({
    client: scheduleClient,
    deliveryClient,
    create: createScheduledSession,
    send: controller.send,
    sessions: controller.state.sessions,
    onNeedsApproval: ({ task, sessionId, tool }) => {
      const baslik = "Zamanlanmış görev onay bekliyor";
      setScheduleNotice({
        sessionId,
        baslik,
        metin: `"${task.baslik}" görevi "${tool}" için onay istiyor. Sen onaylayana kadar bekler; onaylamazsan ilerlemez.`,
      });
      // Kullanıcı başka uygulamadaysa şerit görünmez: işletim sistemi bildirimi de gider (U5-57).
      void osBildirimiGonder(baslik, `"${task.baslik}" görevi "${tool}" için onay bekliyor.`);
    },
    onBlocked: (task, reason) => setScheduleNotice({
      sessionId: null,
      baslik: "Zamanlanmış görev başlatılmadı",
      metin: `"${task.baslik}" güvenli biçimde başlatılamadı (${reason}). Görev gönderilmedi; yeniden dene.`,
    }),
  });
  const selectMainSection = (section: MainSection) => {
    if (section === "scheduled" || section === "library" || section === "kits") {
      setSurfaceSection(section);
      return;
    }
    setSurfaceSection(null);
    if (section === "media") {
      if (!mediaPage) void navigateSidebar("image-create");
    } else if (mediaPage) {
      setPage("chat");
    }
  };
  const mainRail = <MainRail active={mainSection} onSelect={selectMainSection} accountHostRef={setAccountHost} />;
  const mainSurface = (
    <MainSurface
      section={surfaceSection}
      scheduled={<ScheduleScreen client={scheduleClient} defaultRoot={active?.root ?? ""} onRunNow={scheduleRunner.runNow} visible={surfaceSection === "scheduled"} />}
      library={<LibraryScreen client={active?.client ?? null} visible={surfaceSection === "library"} />}
      kits={<KitsScreen onDeliveryClient={setDeliveryClient} onScheduleApproval={notifyKitsApproval} requestHost={activeClient ? requestKitsHost : undefined} visible={surfaceSection === "kits"} />}
    />
  );
  /** `@` sorgusunu sunucuya ilet ve gelen öneriyi listeye yaz. */
  const searchProjectFiles = useCallback(
    (sorgu: string) => {
      // Oturum henüz açılmadıysa arama yapılmaz; `@` listesi boş kalır.
      if (!active) return;
      const sira = ++fileQuerySeq.current;
      void active.client
        .request("proje.dosya_ara", { sorgu, limit: 12 })
        .then((cevap) => {
          if (sira !== fileQuerySeq.current) return;
          const veri = cevap as { sonuclar?: unknown };
          const ham = Array.isArray(veri.sonuclar) ? veri.sonuclar : [];
          setFileSuggestions(
            ham
              .map((item) => item as { yol?: unknown; vurgu?: unknown })
              .filter((item): item is { yol: string; vurgu?: number[] } => typeof item.yol === "string")
              .map((item) => ({ yol: item.yol, vurgu: Array.isArray(item.vurgu) ? item.vurgu : [] })),
          );
        })
        .catch(() => {
          // Arama başarısızlığı turu ETKİLEMEZ: liste boş kalır, kullanıcı
          // dosyayı elle yazmaya devam edebilir.
          if (sira === fileQuerySeq.current) setFileSuggestions([]);
        });
    },
    [active],
  );

  const composerCommands = useMemo<ComposerCommand[]>(() => [
    FOLDER_COMMAND,
    ...commands.filter((command) => !command.ad.toLocaleLowerCase("tr").startsWith("resume")),
    ...history.sources.map((source) => ({
      ad: `resume${source.ad}`,
      aciklama: `${source.ad[0].toLocaleUpperCase("tr")}${source.ad.slice(1)} konuşmasına devam et`,
      grup: "Geçmiş",
      kullanim: source.komut,
      destekleniyor: true,
    })),
  ], [commands, history.sources]);

  useEffect(() => {
    if (!activeSessionId) return;
    let alive = true;
    let unlisten: (() => void) | null = null;
    void listenForFileDrops((paths) => {
      if (!alive) return;
      const additions = attachmentsFromPaths(paths);
      if (additions.length === 0) {
        setAttachmentError("Sürüklenen öğelerde geçerli bir dosya yolu bulunamadı.");
        return;
      }
      setAttachmentError(null);
      setAttachments((current) => ({
        ...current,
        [activeSessionId]: [...(current[activeSessionId] ?? []), ...additions]
          .filter((item, index, all) => all.findIndex((other) => other.path === item.path) === index),
      }));
    }).then((stop) => {
      if (alive) unlisten = stop;
      else stop();
    }).catch(() => {
      if (alive) setAttachmentError("Sürükle-bırak dinleyicisi başlatılamadı. Uygulamayı yeniden dene.");
    });
    return () => { alive = false; unlisten?.(); };
  }, [activeSessionId]);

  // Etkin model oturumun yapılandırmasından gelir; istemcide önbelleğe alınmaz.
  // `controlRevision` bağımlılıktır: `/model` komutu modeli değiştirdiğinde
  // composer'daki ad da tazelenmeli, yoksa eski model yazılı kalırdı.
  const { model: activeModel, label: activeModelLabel } = useActiveModel(activeClient, activeSessionId, controlRevision);

  const modelCatalog = useModelCatalog(activeClient, activeSessionId, workspaceMode);
  const modelOptions = modelCatalog.options;
  const modelsBusy = modelCatalog.state.status === "loading";
  const modelsError = modelCatalog.state.status === "error" ? modelCatalog.state.message : "";
  const loadModelOptions = modelCatalog.load;

  useEffect(() => {
    if (!activeClient || !activeSessionId) return;
    let alive = true;
    // `Promise.all` birinin reddinde TÜM slash menüsünü (yerel komutlar dahil) boşaltıyor ve beceri/MCP
    // listesini eski oturumdan bayat bırakıyordu; her yarı bağımsız bozulur (U3-27).
    void Promise.allSettled([
      activeClient.request("komut.listele", {}),
      activeClient.request("yetenek.katalog", {}),
    ]).then(([commandResult, capabilityResult]) => {
      if (!alive) return;
      const commandPayload: Record<string, unknown> = commandResult.status === "fulfilled" ? commandResult.value : {};
      const capabilityPayload: Record<string, unknown> = capabilityResult.status === "fulfilled" ? capabilityResult.value : {};
      const listed = Array.isArray(commandPayload.komutlar) ? commandPayload.komutlar : [];
      const commandRows: ComposerCommand[] = listed.flatMap((raw) => {
        if (!raw || typeof raw !== "object") return [];
        const row = raw as Record<string, unknown>;
        if (typeof row.ad !== "string") return [];
        return [{
          ad: row.ad,
          aciklama: String(row.aciklama ?? ""),
          grup: String(row.grup ?? "Komut"),
          kullanim: String(row.kullanim ?? ""),
          destekleniyor: row.destekleniyor !== false,
        }];
      });
      const mcpRows: ComposerCommand[] = (Array.isArray(capabilityPayload.mcp) ? capabilityPayload.mcp : [])
        .flatMap((raw) => {
          if (!raw || typeof raw !== "object") return [];
          const row = raw as Record<string, unknown>;
          if (typeof row.ad !== "string" || row.etkin !== true) return [];
          return [{
            ad: `mcp ${row.ad}`,
            aciklama: String(row.aciklama ?? `${row.ad} MCP sunucusu`),
            grup: "MCP",
            kullanim: "",
            destekleniyor: true,
          }];
        });
      const commandNames = new Set(commandRows.map((row) => row.ad.toLocaleLowerCase("tr")));
      const skillRows: ComposerCommand[] = (Array.isArray(capabilityPayload.beceriler) ? capabilityPayload.beceriler : [])
        .flatMap((raw) => {
          if (!raw || typeof raw !== "object") return [];
          const row = raw as Record<string, unknown>;
          if (typeof row.ad !== "string" || row.etkin === false) return [];
          if (commandNames.has(row.ad.toLocaleLowerCase("tr"))) return []; // komut kazanır
          return [{
            ad: row.ad,
            aciklama: String(row.aciklama ?? "Beceri"),
            grup: "Beceri",
            kullanim: "",
            destekleniyor: true,
          }];
        });
      const imageRow: ComposerCommand[] = commandNames.has("görsel") ? [] : [{
        ad: "görsel",
        aciklama: "Sohbette görsel üret — /görsel gün batımında bir dağ evi --oran 16:9",
        grup: "Görsel",
        kullanim: "/görsel <ne çizileceği> [--oran 16:9]",
        destekleniyor: true,
      }];
      setSkillNames(skillRows.map((row) => row.ad));
      setMcpServers((Array.isArray(capabilityPayload.mcp) ? capabilityPayload.mcp : []).flatMap((raw) => {
        if (!raw || typeof raw !== "object") return [];
        const row = raw as Record<string, unknown>;
        if (typeof row.ad !== "string" || row.etkin !== true) return [];
        return [{ ad: row.ad, aciklama: String(row.aciklama ?? "MCP sunucusu") }];
      }));
      setCommands([...commandRows, ...imageRow, ...skillRows, ...mcpRows]);
    }).catch(() => { if (alive) setCommands([]); });
    return () => { alive = false; };
  }, [activeClient, activeSessionId, capabilityRevision]);

  // Bağlantılar / Beceriler ekranından dönünce `@mcp` ve `/beceri` listeleri tazelenir (U3-27).
  const oncekiSayfa = useRef(page);
  useEffect(() => {
    const onceki = oncekiSayfa.current;
    oncekiSayfa.current = page;
    if (onceki !== page && (onceki === "skills" || onceki === "connectors" || onceki === "control")) {
      setCapabilityRevision((current) => current + 1);
    }
  }, [page]);

  // Kapatma isteği Rust'ta durdurulur ve karar burada sorulur.
  useEffect(() => {
    if (!kabukVar()) return;
    const cikar = listen("uygulama://kapatma-istegi", () => setCloseAsked(true));
    return () => void cikar.then((f) => f()).catch(() => undefined);
  }, []);

  // Konuşma penceresinden gelen aynı söz, dinleyici sayısı kaç olursa olsun YALNIZ BİR KEZ işlenir.
  const firstTimeVoiceMessage = useRef(createVoiceMessageDeduper());
  const activeRef = useRef(active);
  activeRef.current = active;
  const controllerRef = useRef(controller);
  controllerRef.current = controller;

  // Konuşma penceresinden gelen söz AYNI sohbete düşer: kip kapandığında
  // kullanıcı yazışmış gibi tam dökümü görür.
  useEffect(() => {
    const cikar = onVoiceMessage((mesaj) => {
      if (mesaj.kaynak !== "kullanici") return;
      const current = activeRef.current;
      if (!current) return;
      if (!firstTimeVoiceMessage.current(mesaj.id)) return;
      const gorev = buildVoiceRequest(mesaj.metin, mesaj.kesilen);
      const requestId = nextSessionId();
      const accepted = controllerRef.current.send(current.id, gorev.text, [], true, gorev.voice, requestId);
      if (!accepted) {
        void publishVoiceRuntimeState({
          durum: "error",
          metin: "Bu konuşmada bir görev zaten çalışıyor. Bitmesini bekleyip yeniden konuş.",
        });
        return;
      }
      voiceRequests.current.push({
        afterIndex: current.messages.length,
        requestId,
        sawRunning: false,
        sessionId: current.id,
      });
      void publishVoiceRuntimeState({ durum: localVoiceReply(mesaj.metin) ? "transcribing" : "thinking" });
    });
    return () => void cikar.then((f) => f()).catch(() => undefined);
  }, []);

  useEffect(() => {
    const remove = onVoiceBargeIn(() => {
      pendingBargeIn.current = true;
      const turn = activeVoiceTurn.current;
      if (turn) void turn.cancel().catch(() => undefined);
    });
    return () => {
      void remove.then((unlisten) => unlisten()).catch(() => undefined);
      void activeVoiceTurn.current?.cancel().catch(() => undefined);
    };
  }, []);

  // Yalnız Talk'tan başlayan turun nihai cevabı seslendirilir. Kullanıcının
  // normal yazışmaları sessiz kalır; sohbet değişse bile istek başladığı
  // oturumun kendi çekirdeği kullanılır. Tur kimliği hemen alınır; gerçek
  // bitiş ayrı `ses.bekle` isteğiyle izlenir ve zaman tahmini kullanılmaz.
  useEffect(() => {
    if (activeVoiceTurn.current) return;
    const pending = voiceRequests.current[0];
    if (!pending) return;
    const session = controller.state.sessions[pending.sessionId];
    if (!session) {
      voiceRequests.current.shift();
      setVoicePlaybackRevision(value => value + 1);
      return;
    }
    const response = session.messages.find(message => message.id === `${pending.requestId}:assistant`);
    if (!response && !session.completedRequestIds?.includes(pending.requestId) && session.running) {
      pending.sawRunning = true;
      return;
    }
    if (!response && !session.completedRequestIds?.includes(pending.requestId)) return;
    voiceRequests.current.shift();
    const answer = response?.metin.trim();
    if (!answer) {
      void publishVoiceRuntimeState({ durum: "error", metin: "Fusion yanıt üretmedi." });
      setVoicePlaybackRevision(value => value + 1);
      return;
    }
    pendingBargeIn.current = false;
    // Cevap cümle cümle seslendirilir: ilk cümle hazır olur olmaz ses başlar.
    const turn = createVoicePlayback(session.client, answer, publishVoiceRuntimeState);
    activeVoiceTurn.current = turn;
    if (pendingBargeIn.current) void turn.cancel().catch(() => undefined);
    void turn.finished.finally(() => {
      if (activeVoiceTurn.current === turn) {
        activeVoiceTurn.current = null;
        setVoicePlaybackRevision(value => value + 1);
      }
    }).catch(() => undefined);
  }, [controller.state.sessions, voicePlaybackRevision]);

  // Ses tercihleri konuşma penceresinden gelir ama YAZMA yolu tektir: burada,
  // ana pencerenin çekirdek bağlantısı üzerinden. Pencerenin kendi bağlantısını
  // açmak, iki ayrı yazıcı ve iki ayrı hata yolu demek olurdu.
  useEffect(() => {
    if (!active) return;
    const client = active.client;
    const yayinla = async (istek: VoicePrefsPayload | null) => {
      const sonuc = istek
        ? await client.request("ses.ayar", { ...istek })
        : await client.request("ses.durum", {});
      const kaynak = (istek ? sonuc : (sonuc.ayar as Record<string, unknown> | undefined)) ?? {};
      const satir = kaynak as Record<string, unknown>;
      await publishVoicePrefs({
        hiz: typeof satir.hiz === "number" ? satir.hiz : 1,
      });
      // Arayüzü bekletmeden, ilk kısa yanıtın model yüklemesini öne al.
      void client.request("ses.isit", {}).then(result => {
        if (result.ok === false) console.warn("Fusion ses ön hazırlığı tamamlanamadı.");
      }).catch(() => console.warn("Fusion ses ön hazırlığı bağlantısı tamamlanamadı."));
    };
    const cikar = onVoicePrefsRequest((istek) => void yayinla(istek).catch(() => undefined));
    return () => void cikar.then((f) => f()).catch(() => undefined);
  }, [active]);

  // Ajan siteyi çalıştırınca (`PreviewReady`) önizleme paneli KENDİLİĞİNDEN açılır;
  // kullanıcı "nasıl önizlerim" diye sormak zorunda kalmamalı (ölçüldü, 2 Ekim).
  const openPreview = useCallback((url: string) => {
    setSelectedPath(null);
    setRequestedPreview((current) => ({ url, seq: (current?.seq ?? 0) + 1 }));
    inspectorLayout.setActiveTab("preview");
    layout.openInspector();
  }, [inspectorLayout, layout]);
  const gorulenOnizleme = useRef("");
  useEffect(() => {
    if (!activeMessages || !activeSessionId) return;
    const kartlar = activeMessages.filter((message) => message.rol === "onizleme");
    const son = kartlar[kartlar.length - 1];
    const anahtar = son ? `${activeSessionId}|${kartlar.length}|${son.metin}` : "";
    if (!son || anahtar === gorulenOnizleme.current) return;
    const ilkBakis = gorulenOnizleme.current === "";
    gorulenOnizleme.current = anahtar;
    // Sekme açılırken eski kart yüzünden panel zıplamasın; yalnız canlı turda aç.
    if (!ilkBakis || activeRunning) openPreview(son.metin);
  }, [activeMessages, activeSessionId, activeRunning, openPreview]);

  // Açık onay konuşma penceresine de yayılır ve oradan gelen cevap aynı
  // `answer` yolundan geçer: iki ayrı onay mantığı olsaydı biri düzeltilirken
  // öteki eskirdi.
  // Plan kipi: tur bitince Claude'daki gibi "planı uygula?" kartı. Kart yalnız
  // plan kipinde, turun GERÇEKTEN bittiği anda ve son yanıt hata değilse çıkar.
  const [planHazir, setPlanHazir] = useState<string | null>(null);
  const oncekiCalisiyor = useRef(false);
  useEffect(() => {
    if (!activeMessages || !activeSessionId) return;
    const bitti = oncekiCalisiyor.current && !Boolean(activeRunning);
    oncekiCalisiyor.current = Boolean(activeRunning);
    const son = activeMessages[activeMessages.length - 1];
    if (bitti && approval === "plan" && son?.rol === "asistan" && !son.hata && son.metin.trim()) {
      setPlanHazir(activeSessionId);
    }
  }, [activeRunning, activeSessionId, activeMessages, approval]);
  // Chrome eklentisi Fusion'ı yerel mesajlaşmayla kendisi bulur; köprü ETKİN sohbet
  // sekmesinde açık tutulur. Sekme değişince önceki köprü kapanır, eklenti yeni
  // sekmenin köprüsüne kendiliğinden geçer (bkz. chrome_host.py, offscreen.js).
  const chromeIstemcisi = useRef<{ request: (ad: string, veri: Record<string, unknown>) => Promise<unknown> } | null>(null);
  useEffect(() => {
    const client = active?.client;
    if (!client || active?.status !== "ready") return;
    const onceki = chromeIstemcisi.current;
    if (onceki && onceki !== client) void onceki.request("chrome.durdur", {}).catch(() => undefined);
    chromeIstemcisi.current = client;
    void client.request("chrome.baslat", {}).catch(() => undefined);
  }, [active?.client, active?.status]);
  useEffect(() => {
    if (!active) return;
    const soru = active.question;
    void publishVoiceAsk(
      soru
        ? {
            acik: true,
            sessionId: active.id,
            questionId: soru.id,
            arac: soru.data.arac,
            metin: soru.data.soru ?? `${soru.data.arac ?? "İşlem"} çalıştırılsın mı?`,
            secenekler: (soru.data.secenekler ?? [
              { deger: "evet", etiket: "Onayla" },
              { deger: "hayir", etiket: "Reddet" },
            ]).map((secenek) => ({
              deger: secenek.deger ?? secenek.etiket,
              etiket: secenek.etiket,
            })),
          }
        : null,
    ).catch(() => undefined);
  }, [active?.question, active]);

  useEffect(() => {
    if (!activeSessionId) return;
    const id = activeSessionId;
    // Cevap biçimi ana penceredeki kartla AYNIDIR: izin `{ secim }`, model
    // sorusu (`ask_user`) `{ metin }` bekler; yanlış alan cevabı boşa düşürür.
    const question = active?.question;
    const cikar = onVoiceAnswer((cevap) => {
      if (typeof cevap === "string" || !question || cevap.sessionId !== id || cevap.questionId !== question.id) return;
      void controller.answer(id, question.data.tur === "soru" ? { metin: cevap.answer } : { secim: cevap.answer })
        .catch((reason: unknown) => {
          setNewTaskError(String(reason));
          void publishVoiceRuntimeState({ durum: "error", metin: "Cevap kabul edilmedi. Karttan yeniden deneyebilirsin." });
        });
    });
    return () => void cikar.then((f) => f()).catch(() => undefined);
  }, [activeSessionId, active?.question, controller]);

  // Ölçüldü (28 Eylül, Windows): "Çekirdek bağlantısı kapatıldı" dışında hiçbir
  // iz yoktu; çekirdeğin hata çıktısı atılıyordu. Artık günlüğe yazılıyor ve
  // bağlantı koptuğunda sonu burada gösterilip hata raporuna ekleniyor.
  const aktifCoktu = active?.status === "crashed";
  const baglantiKoptu = Boolean(controller.state.connectionError) || aktifCoktu;
  useEffect(() => {
    if (!baglantiKoptu) return;
    let alive = true;
    invoke<string | null>("cekirdek_gunlugu")
      .then((metin) => { if (alive) setCekirdekGunlugu(metin ?? null); })
      .catch(() => undefined);
    return () => { alive = false; };
  }, [baglantiKoptu]);

  // Kapatma Rust'ta DURDURULUR ve onay burada sorulur; bu yüzden onay HER ekranda
  // çizilmelidir. Ölçüldü (28 Eylül, Windows): hata/hazırlanıyor/hesap/rehber
  // ekranlarında onay hiç çizilmiyordu ve uygulama kapanmıyordu.
  const kapatmaOnayi = closeAsked ? (
    <CloseConfirm
      onCancel={() => {
        setCloseAsked(false);
        // Rust bekleyen isteği ve bekçisini temizlesin; yoksa nabız kesilince uygulama kapanırdı.
        if (kabukVar()) void invoke("kapatma_vazgec").catch(() => undefined);
      }}
      onConfirm={() => void invoke("kapatmayi_onayla").catch((reason: unknown) => setNewTaskError(`Uygulama kapatılamadı: ${errorMessage(reason)}`))}
      running={active?.running}
    />
  ) : null;

  if (controller.state.connectionError) {
    const baglantiHatasi = controller.state.connectionError;
    return (
      <div className="app-status-screen">
        <p>Hata: {baglantiHatasi}</p>
        {cekirdekGunlugu && (
          <details className="app-status-screen__log">
            <summary>Çekirdeğin son hata çıktısı</summary>
            <pre>{cekirdekGunlugu}</pre>
          </details>
        )}
        <button
          className="conversation__report"
          onClick={() => setFeedback({
            tur: "hata",
            mesaj: "Fusion çekirdeğine bağlanılamadı.",
            ayrinti: cekirdekGunlugu ? `${baglantiHatasi}\n\n${cekirdekGunlugu}` : baglantiHatasi,
          })}
          type="button"
        >
          Hatayı bildir
        </button>
        {feedback && <FeedbackDialog initial={feedback} onClose={() => setFeedback(null)} />}
        {kapatmaOnayi}
      </div>
    );
  }
  const chooseProjectFolder = async () => {
    if (!(await permissions.ensure("workspace"))) return null;
    const root = await selectFolder(readLastRoot());
    return root && root !== "/" ? root : null;
  };
  const recordRoots = new Set(projects.registry.projects.flatMap((record) => record.root ? [record.root] : []));
  const projectSidebarProps = {
    profileHost: accountHost,
    onProjectCreate: async (input: { name: string; root?: string }) => {
      setNewTaskError(null);
      try {
        await createAndOpenProject(input, { createRecord: projects.create, createChat: controller.create, desktopRoot: desktopDir, assign: projects.assign });
        setSurfaceSection(null);
        setPage("chat");
      } catch (reason) {
        if (!(reason instanceof ProjectOpenError)) throw reason;
        setSurfaceSection(null);
        setPage("chat");
        setNewTaskError(`${reason.message}. Projenin yanındaki + ile yeniden deneyebilirsin.`);
      }
    },
    onProjectRename: projects.rename,
    onProjectDelete: projects.remove,
    onAssign: projects.assign,
    onPickFolder: chooseProjectFolder,
    onSil: async (id: string) => { await controller.remove(id); projects.forget(id); },
    /** Kalıcı kayıtlar önce gelir; klasörü bir kayda bağlı olan eski türev proje çift görünmez. */
    projeler: [
      ...projects.registry.projects.map((record) => ({
        id: record.id, name: record.name, pinned: false, root: record.root ?? "", updated_at: record.createdAt,
      })),
      ...controller.recentProjects.filter((project) => !recordRoots.has(project.root)).map((project) => ({
        name: project.name, pinned: false, root: project.root, updated_at: project.updatedAt,
      })),
    ],
  };
  const sectionOwnsSidebar = surfaceSection !== null || page === "settings";
  if (!active) {
    if (!hasOpenedSession.current) return <div className="app-status-screen">Hazırlanıyor…{kapatmaOnayi}</div>;
    return <><Shell
      rail={mainRail}
      surface={mainSurface}
      surfaceActive={surfaceSection !== null}
      surfaceFullBleed={surfaceSection !== null}
      sidebarHidden={sectionOwnsSidebar}
      header={<AppHeader canNavigateBack={pageHistory.canGoBack} canNavigateForward={pageHistory.canGoForward} onNavigateBack={pageHistory.back} onNavigateForward={pageHistory.forward} title="Yeni sohbet" status="Hazır" inspectorOpen={false} onToggleInspector={() => undefined} onToggleSidebar={layout.toggleSidebar} sidebarCollapsed={layout.sidebarCollapsed} />}
      content={<>{mediaPage ? <MediaScreen active={page} image={<ImageCreate client={null} />} onSelect={setPage} /> : <EmptyState projectName="Desktop" />}{newTaskError && <p role="alert">{newTaskError}</p>}{!mediaPage && <button type="button" onClick={() => void startDesktopChat()}>Desktop içinde yeni sohbet başlat</button>}</>}
      sidebarCollapsed={layout.sidebarCollapsed}
      onSidebarClose={layout.toggleSidebar}
      sidebar={<Sidebar collapsed={layout.sidebarCollapsed} etkin={null} onNavigate={(destination) => void navigateSidebar(destination)} {...projectSidebarProps} onMove={(id, root) => controller.move(id, root)} onYeni={() => { setSurfaceSection(null); void startDesktopChat(); }} onSec={(id) => { setSurfaceSection(null); void controller.openStored(id).catch(() => setNewTaskError("Sohbet açılamadı. Yeniden dene.")); }} oturumlar={controller.storedConversations.map((conversation) => ({ session_id: conversation.id, source: "fusion", title: conversation.title, project: projectName(conversation.root), projectRoot: conversation.root, projectId: projects.registry.chats[conversation.id], updated_at: conversation.updatedAt * 1000 }))} />}
    />{kapatmaOnayi}</>;
  }

  // Fusion hesapsız açılmaz. Kapı, çekirdek bağlandıktan sonra çizilir:
  // hesap bilgisi oradan okunuyor.
  if (active && !account.yukleniyor && account.durum && (!account.durum.etkin || account.kurtarmaKodu)) {
    return <><AccountGate account={account} />{kapatmaOnayi}</>;
  }

  if (showOnboarding) {
    const projects: SampleProject[] = [
      { id: active.root, name: projectName(active.root), description: "Şu anda açık olan çalışma alanı", path: active.root },
      ...controller.recentProjects.filter((project) => project.root !== active.root).slice(0, 3).map((project) => ({
        id: project.root, name: project.name, description: "Yakın zamanda kullanılan proje", path: project.root,
      })),
    ];
    return (
      <>
      <ConnectedOnboarding
        client={active.client}
        onFinish={(projectId) => {
          setShowOnboarding(false);
          onOnboardingComplete();
          if (projectId && projectId !== active.root) void controller.create({ root: projectId, mode: "kod" });
        }}
        projects={projects}
        runtimeVersion={runtimeVersion}
      />
      {kapatmaOnayi}
      </>
    );
  }

  // Kendi başlığını taşıyan tam ekran sayfalarda üst şerit o başlığı TEKRARLAMAZ.
  // Ölçüldü: Ayarlar açıkken ekranda "Ayarlar" iki kez yazıyordu ve erişilebilirlik
  // ağacında aynı adla iki başlık düğümü oluşuyordu. Şerit bu sayfalarda çalışma
  // alanını gösterir; sayfanın kimliği sayfanın kendi başlığındadır.
  const activeProject = projects.registry.projects.find((record) => record.id === projects.registry.chats[active.id]);
  const activeProjectName = activeProject?.name ?? projectName(active.root);
  const headerTitle = page === "account" ? "Hesabım"
    : page === "settings" ? active.title
    : SAYFA_KENDI_BASLIGINI_TASIR.includes(page)
    ? activeProjectName
    : page === "image-create" ? "Görsel oluştur"
      : page === "video-create" ? "Video oluştur"
        : page === "skills" ? "Beceriler ve Ajanlar"
          : page === "help" ? "Yardım"
            : active.title;

  const draft = drafts[active.id] ?? controller.submissionDraft(active.id);
  const activeAttachments = attachments[active.id] ?? controller.submissionAttachments(active.id);
  const setDraft = (value: string) => setDrafts((current) => ({ ...current, [active.id]: value }));
  /** Komut ve model seçimi AYNI meşgul/hata/sürüm durumunu paylaşır; yalnız taşıma (`run`) değişir. */
  const trackCommand = async (run: () => Promise<Record<string, unknown>>): Promise<CommandResult> => {
    const generation = commandOwner.current, sequence = ++commandSequence.current;
    const isCurrent = () => generation === commandOwner.current && sequence === commandSequence.current;
    setCommandBusy(true);
    setCommandError(null);
    try {
      const result = await run();
      if (!isCurrent()) return { ok: false, message: "Komut sonucu önceki oturuma ait." };
      const next = commandSelectorFrom(result.secici);
      setCommandSelector(next);
      // Çekirdek `/clear` için EKRAN temizleme sinyali döner; afiş basmaz.
      if (result.temizle === true) controller.clear(active.id);
      // Komut yapılandırmayı değiştirmiş olabilir; panel eski değeri göstermesin.
      if (next === null) setControlRevision((current) => current + 1);
      const outcome = operationResult(result, "Komut tamamlanamadı.", true);
      if (!outcome.ok) setCommandError(outcome.message);
      return outcome;
    } catch (reason) {
      const message = `Komut çalıştırılamadı: ${errorMessage(reason)}`;
      if (isCurrent()) setCommandError(message);
      return { ok: false, message };
    } finally {
      if (isCurrent()) setCommandBusy(false);
    }
  };
  const executeCommand = (input: string, recordInput = true, recordOutput = true): Promise<CommandResult> =>
    trackCommand(() => controller.runCommand(active.id, input, recordInput, recordOutput));
  // Yapısal seçim (U1-40); kaynak/kimlik taşımayan seçenek (eski biçim) komut yoluna düşer.
  const selectModelOption = (option: ModelOption): Promise<CommandResult> => {
    const { kaynak, modelId } = option;
    return kaynak && modelId
      ? trackCommand(() => controller.selectModel(active.id, kaynak, modelId))
      : executeCommand(option.deger, false, false);
  };
  const capabilityNames = () => ({
    skills: skillNames,
    mcp: mcpServers.map((server) => server.ad),
    commands: commands.map((command) => command.ad),
  });
  const skillFrom = (task: string) => parseCapabilityInput(task, capabilityNames()).skill;
  const send = (task: string) => {
    const resumeSource = task.match(/^\/resume(claude|codex|hermes)$/i)?.[1]?.toLocaleLowerCase("tr") as "claude" | "codex" | "hermes" | undefined;
    if (resumeSource && history.sources.some((source) => source.ad === resumeSource)) {
      setHistoryOpen(true);
      void history.openSource(resumeSource);
    } else if (isFolderCommand(task, FOLDER_COMMAND.ad)) {
      // Klasör değiştirme UYGULAMA tarafı iştir: çekirdeğin kökü açılışta
      // belirlenir, bu yüzden komutu çekirdeğe göndermek anlamsız olurdu.
      void requestTaskFolder();
    } else if (task.startsWith("/") && !startsWithFilePath(task) && !isImageCommand(task) && !skillFrom(task)) void executeCommand(task);
    else {
      if (active.running && busySubmissionMode === "steer" && !active.stopping && !active.stopError) {
        if (activeAttachments.length) {
          setCommandError("Ekli bağımsız iş için Sıraya al seçeneğini kullan.");
          return false;
        }
        return controller.steer(active.id, task).then((accepted) => {
          if (accepted) setDrafts((current) => ({ ...current, [active.id]: "" }));
          return accepted;
        }).catch((reason: unknown) => { setCommandError(String(reason)); return false; });
      }
      const snapshot = activeAttachments;
      const draftSnapshot = draft;
      const picked = parseCapabilityInput(task, capabilityNames());
      const selections: Array<[string, string]> = [
        ...(picked.skill ? [["beceri", picked.skill.ad] as [string, string]] : []),
        ...picked.mcp.map((ad) => ["mcp", ad] as [string, string]),
      ];
      const taskText = picked.skill ? (picked.skill.rest || DEFAULT_SKILL_TASK(picked.skill.ad)) : task;
      const prepare = selections.length === 0 || !activeClient
        ? Promise.resolve()
        : Promise.all(selections.map(([tur, ad]) => activeClient.request("yetenek.kullan", { tur, ad })))
            .then(() => undefined);
      // Yetenek hazırlığı reddedilirse işlenmemiş söz reddi kalmaz; hata gösterilir, taslak korunur (U3-34).
      const prepared = prepare.then(() => true, (reason: unknown) => {
        setCommandError(`Yetenek hazırlanamadı: ${errorMessage(reason)}`);
        return false;
      });
      return prepared.then<SubmissionResult>((ok) => ok ? controller.submit(active.id, taskText, snapshot) : false).then((receipt) => {
        if (submissionAccepted(receipt)) {
          setAttachments((current) => current[active.id] === snapshot || current[active.id] === undefined
            ? { ...current, [active.id]: [] } : current);
          setDrafts((current) => current[active.id] === draftSnapshot || current[active.id] === undefined
            ? { ...current, [active.id]: "" } : current);
        }
        return receipt;
      });
    }
  };
  const conversationContent = active.messages.length > 0 ? (
    <Conversation
      mesajlar={active.messages}
      running={active.running}
      showSteps={showSteps}
      onReadAloud={async (text) => {
        const generation = ++manualVoiceGeneration.current;
        await manualVoiceTurn.current?.cancel();
        if (generation !== manualVoiceGeneration.current) return;
        const turn = createVoicePlayback(active.client, text, async () => undefined);
        manualVoiceTurn.current = turn;
        try { await turn.finished; }
        finally { if (manualVoiceTurn.current === turn) manualVoiceTurn.current = null; }
      }}
      onEvaluate={async (text, rating) => {
        const result = await active.client.request("yanit.degerlendir", { metin: text, rating });
        if (result.ok !== true) throw new Error(String(result.metin ?? "Değerlendirme kaydedilemedi."));
      }}
      onContinueInNewChat={async (index) => {
        const message = active.messages[index];
        const occurrence = active.messages.slice(0, index).filter((item) => item.rol === "asistan" && !item.ara && !item.akan && item.metin === message.metin).length;
        const result = await active.client.request("sohbet.dallan", { metin: message.metin, eslesme: occurrence });
        if (result.ok !== true || typeof result.sohbet_id !== "string") throw new Error(String(result.metin ?? "Yeni sohbet açılamadı."));
        const projectId = projects.registry.chats[active.id];
        if (projectId) projects.assign(result.sohbet_id, projectId);
        saveWorkspaceMode(result.sohbet_id, workspaceMode);
        await controller.refreshStored();
        await controller.openStored(result.sohbet_id, active.root);
        setSurfaceSection(null);
        setPage("chat");
      }}
      onOneriSec={(gorev) => send(gorev)}
      onRetrySubmission={(requestId) => { controller.retrySubmission(active.id, requestId); }}
      onHataBildir={(metin) => setFeedback({ tur: "hata", mesaj: "Bir görev hatayla bitti.", ayrinti: metin })}
      onOpenPreview={openPreview}
      onOpenFile={(path) => {
        setSelectedPath(path);
        // Dosyanın İÇERİĞİNİ gösteren sekme önizlemedir; ağaç sekmesi yalnız
        // klasörü açardı ve kullanıcı tıkladığı dosyayı göremezdi.
        inspectorLayout.setActiveTab("preview");
        layout.openInspector();
      }}
    />
  ) : (
    <EmptyState durum={active.running ? "thinking" : "idle"} projectName={activeProjectName} workspaceMode={workspaceMode} onSelectPrompt={setDraft} />
  );
  const content = mediaPage
    ? <MediaScreen active={page} image={<ImageCreate client={active.client} jobScope={JSON.stringify([active.root, active.id])} />} onSelect={setPage} />
    : page === "skills"
    ? <SkillsCatalog client={active.client} onClose={() => setPage("chat")} />
    : page === "control"
      ? (
        <ControlPanel
          client={active.client}
          title={controlTitle}
          onClose={() => setPage("chat")}
          revision={controlRevision}
          onProvidersChanged={() => setControlRevision((value) => value + 1)}
        />
      )
      : page === "connectors"
        ? <ConnectorsScreen client={active.client} onClose={() => setPage("chat")} />
      : page === "account"
        ? (
          <AccountScreen
            account={account}
            client={active.client}
            onClose={() => setPage("chat")}
            onPickAvatarFile={async () => {
              // Dosya seçimi KABUKTAN, kopyalama ÇEKİRDEKTEN gelir: arayüz
              // dosya sistemine yazmaz ve avatar hesabın kendi dizininde durur.
              const secilen = await selectFiles(active.root).catch(() => []);
              const yol = secilen[0];
              const kimlik = account.durum?.etkin;
              if (!yol || !kimlik) return null;
              const sonuc = await active.client
                .request("hesap.avatar_yukle", { kimlik, yol })
                .catch(() => null);
              return sonuc?.ok === true && typeof sonuc.avatar === "string" ? sonuc.avatar : null;
            }}
          />
        )
      : page === "settings"
        ? (
          <Settings
            client={active.client}
            initialSection={settingsSection}
            onChangeRoot={() => void requestTaskFolder()}
            onClose={() => setPage("chat")}
            onOpenAccount={() => setPage("account")}
            onReopenSetup={() => { clearProgress(); setPage("chat"); setShowOnboarding(true); }}
            onRunCommand={(command) => executeCommand(command, false)}
            onThemeChange={changeTheme}
            themePreference={themePreference}
            turnRunning={Boolean(active.running)}
          />
        )
      : page === "help"
        ? (
          <HelpScreen
            onClose={() => setPage("chat")}
            onOpenSettings={() => setPage("settings")}
            surum={runtimeVersion}
          />
        )
        : conversationContent;
  const status = active.status === "crashed"
    ? BAGLANTI_KESILDI_DURUMU
    : active.running
      ? "Çalışıyor"
      : "Hazır";
  const chooseTaskFolder = async () => {
    // Sürüm sayacı: Vazgeç (ya da yeni bir seçim) sonrası gelen eski seçici sonucu yok sayılır (U4-20).
    const pick = ++folderPickVersion.current;
    const isCurrentPick = () => folderPickVersion.current === pick;
    setNewTaskBusy(true);
    setNewTaskError(null);
    try {
      const storedRoot = readLastRoot();
      const root = await selectFolder(storedRoot === "/" ? undefined : storedRoot);
      if (!isCurrentPick()) return;
      if (!root) {
        setNewTaskOpen(false);
        return;
      }
      if (root === "/") {
        setNewTaskError("Kök dizin yerine çalışacağın proje klasörünü seç.");
        return;
      }
      await controller.create({ root, mode: "kod" });
      if (!isCurrentPick()) return;
      // Depo yazılamazsa klasör yine açıldı; "Klasör açılamadı" demek yanıltıcı olurdu (U3-32).
      writeStorage(() => localStorage, LAST_ROOT_KEY, root);
      setPage("chat");
      setNewTaskOpen(false);
    } catch (reason) {
      if (isCurrentPick()) setNewTaskError(`Klasör açılamadı: ${errorMessage(reason)}`);
    } finally {
      if (isCurrentPick()) setNewTaskBusy(false);
    }
  };
  function requestTaskFolder() {
    void permissions.ensure("workspace").then((granted) => {
      if (granted) void chooseTaskFolder();
    });
  }

  return (
    <>
    <Shell
      rail={mainRail}
      surface={mainSurface}
      surfaceActive={surfaceSection !== null}
      surfaceFullBleed={surfaceSection !== null}
      sidebarHidden={sectionOwnsSidebar}
      emptyChat={page === "chat" && active.messages.length === 0 && !active.running}
      composer={page === "chat" ? (
        <><ProjectPicker root={active.root} name={activeProjectName} projects={controller.recentProjects} onSelect={async (root) => { await controller.create({ root, mode: "kod" }); setPage("chat"); }} onNew={() => requestTaskFolder()} onSettings={() => { setControlTitle("Proje ayarları"); setPage("control"); }} />
        <DepoUyarisi kok={active.root} projeler={active.depoProjeleri} onAc={(kok) => { void controller.create({ root: kok, mode: "kod" }).then(() => setPage("chat")); }} />
        <Composer
          stopping={active.stopping}
          busySubmissionMode={active.stopping || active.stopError ? "queue" : busySubmissionMode}
          busySubmissionDisabled={Boolean(active.stopError)}
          onBusySubmissionModeChange={setBusySubmissionMode}
          key={active.id}
          workspaceMode={workspaceMode}
          onWorkspaceModeChange={(mode) => void changeWorkspace(mode)}
          activeModel={activeModel}
          activeModelLabel={activeModelLabel}
          modelOptions={modelOptions}
          modelsError={modelsError}
          modelSelectionPending={commandBusy}
          onModelConnect={() => { setControlTitle("Sağlayıcılar"); setPage("control"); }}
          modelsBusy={modelsBusy}
          onModelMenuOpen={() => void loadModelOptions()}
          onModelSelect={(option) => void selectModelOption(option)}
          approval={approval}
          onApprovalChange={(next) => void changeApproval(next)}
          attachments={activeAttachments}
          attachmentError={attachmentError ?? controller.submissionRecoveryError(active.id)}
          commandError={active.stopError ?? commandError}
          commands={composerCommands}
          fileSuggestions={fileSuggestions}
          mcpServers={mcpServers}
          onFileQuery={searchProjectFiles}
          context={active.baglam}
          costUsd={active.maliyetUsd}
          onAttach={() => {
            setAttachmentError(null);
            void selectFiles(active.root).then((paths) => {
              const additions = attachmentsFromPaths(paths);
              if (paths.length > 0 && additions.length === 0) {
                setAttachmentError("Seçimde geçerli bir dosya yolu bulunamadı.");
                return;
              }
              setAttachments((current) => ({
                ...current,
                [active.id]: [...(current[active.id] ?? []), ...additions]
                  .filter((item, index, all) => all.findIndex((other) => other.path === item.path) === index),
              }));
            }).catch(() => setAttachmentError("Dosya seçici açılamadı. Erişimi kontrol edip yeniden dene."));
          }}
          onDropFiles={(files) => {
            setAttachmentError(null);
            const { additions, unresolved } = attachmentsFromDroppedFiles(files, attachments[active.id] ?? []);
            if (files.length > 0 && additions.length === 0 && unresolved > 0) {
              setAttachmentError("Sürüklenen öğelerde geçerli bir dosya yolu bulunamadı. Dosyayı Ekle düğmesiyle seç.");
              return;
            }
            if (unresolved > 0) setAttachmentError(`${unresolved} öğenin yolu çözülemedi; Ekle düğmesiyle seçebilirsin.`);
            setAttachments((current) => ({
              ...current,
              [active.id]: [...(current[active.id] ?? []), ...additions]
                .filter((item, index, all) => all.findIndex((other) => other.path === item.path) === index),
            }));
          }}
          onSend={send}
          onVoice={() => void openVoiceWindow()}
          dictating={dictation.listening}
          dictationError={dictation.error}
          onDictation={() => {
            if (dictation.listening) { void dictation.stop(); return; }
            void (async () => {
              if (!(await permissions.ensure("microphone"))) return;
              if (!(await permissions.ensure("speech"))) return;
              await dictation.start(active.id, draft);
            })();
          }}
          onRemoveAttachment={(path) => setAttachments((current) => ({
            ...current,
            [active.id]: (current[active.id] ?? []).filter((attachment) => attachment.path !== path),
          }))}
          onStop={() => controller.stop(active.id)}
          onValueChange={setDraft}
          running={active.running}
          value={draft}
        /></>
      ) : undefined}
      notices={
        <>
          {gizliDegerSayisi > 0 && (
            <Notification
              baslik="Konuşma devralındı"
              metin={`${gizliDegerSayisi} hassas değer fark edildi. Fusion bunları ekranda göstermedi; uygun olduğunda ilgili anahtarları yenilemeniz iyi olur.`}
              onDismiss={() => setGizliDegerSayisi(0)}
            />
          )}
          {scheduleNotice && (
            <Notification
              baslik={scheduleNotice.baslik}
              metin={scheduleNotice.metin}
              eylem={scheduleNotice.sessionId ? {
                etiket: "Sohbeti aç",
                onSelect: () => {
                  const sessionId = scheduleNotice.sessionId;
                  setScheduleNotice(null);
                  if (sessionId) { controller.select(sessionId); setPage("chat"); }
                },
              } : scheduleNotice.kits ? {
                etiket: "Kits'i aç",
                onSelect: () => { setScheduleNotice(null); setSurfaceSection("kits"); },
              } : undefined}
              onDismiss={() => setScheduleNotice(null)}
            />
          )}
          {dogrulamaUyarisi && (
            <Notification
              baslik="Sağlayıcı doğrulama istiyor"
              metin="Sağlayıcı insan doğrulaması (captcha) istiyor. Bunu ancak sen tamamlayabilirsin; giriş penceresini açıp doğrulamayı bitir."
              eylem={{
                etiket: "Giriş penceresini aç",
                onSelect: () => {
                  setDogrulamaUyarisi(null);
                  setControlTitle("Sağlayıcılar");
                  setPage("control");
                },
              }}
              onDismiss={() => setDogrulamaUyarisi(null)}
            />
          )}
          {aktifCoktu && cokmeKapatilan !== active.id && !crash && !feedback && (
            // Ölçüldü (28 Eylül): çekirdek konuşma sırasında kapanınca yalnız
            // başlıkta "Bağlantı kesildi" yazıyordu; sebep hiçbir yerde yoktu.
            <Notification
              baslik="Fusion çekirdeği kapandı"
              metin={active.error ?? "Bu konuşmanın çekirdeği beklenmedik şekilde kapandı."}
              eylem={{
                etiket: "Hatayı bildir",
                onSelect: () => setFeedback({
                  tur: "hata",
                  mesaj: "Fusion çekirdeği konuşma sırasında kapandı.",
                  ayrinti: [active.error, cekirdekGunlugu].filter(Boolean).join("\n\n"),
                }),
              }}
              onDismiss={() => setCokmeKapatilan(active.id)}
            />
          )}
          {crash && !feedback && (
            <Notification
              baslik="Fusion bir hatayla karşılaştı"
              metin="Arayüzde beklenmeyen bir hata oldu. Bize bildirirsen düzeltebiliriz; ne gönderileceğini göndermeden önce görürsün."
              eylem={{
                etiket: "Hatayı bildir",
                onSelect: () => {
                  setFeedback({ tur: "hata", mesaj: crash.mesaj, ayrinti: crash.ayrinti });
                  clearCrash();
                },
              }}
              onDismiss={clearCrash}
            />
          )}
        </>
      }
      content={
        <>
          {content}
          {newTaskError && !newTaskOpen && <p role="alert">{newTaskError}</p>}
          {kapatmaOnayi}
          {feedback && <FeedbackDialog initial={feedback} onClose={() => setFeedback(null)} />}
          {shareOpen && (
            <ShareDialog
              messages={active.messages}
              onClose={() => setShareOpen(false)}
              title={active.title}
            />
          )}
          {planHazir === active.id && !active.question && !active.running && (
            <Approval
              eyebrow="Plan hazır"
              serbestCevap={false}
              soru={{
                tur: "soru",
                soru: "Bu plan uygulansın mı?",
                secenekler: [
                  { etiket: "Evet, otomatik kipte uygula", aciklama: "Proje içindeki işleri sormadan yapar; riskli işlemlerde yine sorar." },
                  { etiket: "Evet, düzenlemeleri kabul ederek uygula", aciklama: "Dosya düzenlemeleri sorulmaz; komutlar için izin ister." },
                  { etiket: "Evet, her adımda sor", aciklama: "Manuel kipte uygular; her yazma ve komut için izin ister." },
                  { etiket: "Hayır, planlamaya devam et", aciklama: "Plan kipinde kalır; planı birlikte düzeltebilirsiniz." },
                ],
                onerilen: "Evet, otomatik kipte uygula",
              }}
              onCevap={(cevap) => {
                setPlanHazir(null);
                const metin = String(cevap.metin ?? "");
                const yeniKip: ApprovalMode | null = metin.startsWith("Evet, otomatik") ? "auto"
                  : metin.startsWith("Evet, düzenlemeleri") ? "edits"
                  : metin.startsWith("Evet, her") ? "security" : null;
                if (!yeniKip) return;
                // Mod çekirdekte değişmediyse plan "uygulanmış" sayılmaz: hata görünür, mesaj gitmez.
                void changeApproval(yeniKip).then((degisti) => {
                  if (degisti) send("Planı onaylıyorum. Şimdi bu planı adım adım uygula ve her adımdan sonra doğrula.");
                });
              }}
            />
          )}
          {active.question && (
            <Approval
              key={`${active.id}:${active.question.id}`}
              onCevap={(answer) => controller.answer(active.id, answer)}
              soru={active.question.data}
            />
          )}
          {historyOpen && (
            <HistoryPicker
              history={history}
              onClose={() => setHistoryOpen(false)}
              onResumed={(result) => {
                setPage("chat");
                setGizliDegerSayisi(result.secretCount);
              }}
              onResume={(session) => controller.resume({
                source: session.kaynak,
                sessionId: session.oturum_id,
                title: session.baslik,
                root: active.root,
              })}
              open
            />
          )}
          <NewTaskDialog
            busy={newTaskBusy}
            error={newTaskError}
            onCancel={() => {
              // Seçici asılı kalsa bile çıkış var; sonradan dönen sonuç sürüm sayacıyla yok sayılır (U4-20).
              folderPickVersion.current += 1;
              setNewTaskBusy(false);
              setNewTaskError(null);
              setNewTaskOpen(false);
            }}
            onChat={() => {
              setNewTaskOpen(false);
              setNewTaskError(null);
              setPage("chat");
              void controller.create();
            }}
            onFolder={requestTaskFolder}
            open={newTaskOpen}
          />
          {permissions.activeKind && (
            <PermissionPrompt
              canOpenSettings={hasSettingsLink(permissions.activeKind)}
              error={permissions.error}
              isRequesting={permissions.isRequesting}
              kind={permissions.activeKind}
              phase={permissions.phase}
              onContinue={() => void permissions.continue()}
              onContinueToNext={permissions.hasQueuedPermission ? permissions.continueToNext : undefined}
              onDismiss={permissions.dismiss}
              onOpenSettings={() => void permissions.openSettings(permissions.activeKind!)}
              onRetry={() => void permissions.retry()}
            />
          )}
          {commandSelector && (
            <CommandSelector
              busy={commandBusy}
              error={commandError}
              onCancel={() => {
                setCommandError(null);
                setCommandSelector(null);
              }}
              onSelect={(input) => void executeCommand(input, false)}
              onSecret={(saglayici, deger) => void trackCommand(() => controller.saveProviderSecret(active.id, saglayici, deger))}
              open
              selector={commandSelector}
            />
          )}
        </>
      }
      header={
        <AppHeader
          canNavigateBack={pageHistory.canGoBack}
          canNavigateForward={pageHistory.canGoForward}
          sidebarAvailable={!sectionOwnsSidebar}
          inspectorAvailable={page === "chat" && surfaceSection === null}
          inspectorOpen={layout.inspectorOpen}
          onNavigateBack={pageHistory.back}
          onNavigateForward={pageHistory.forward}
          onShare={page === "chat" && active.messages.some((message) => message.rol === "kullanici" || message.rol === "asistan") ? () => setShareOpen(true) : undefined}
          onToggleInspector={layout.toggleInspector}
          onToggleSidebar={layout.toggleSidebar}
          sidebarCollapsed={layout.sidebarCollapsed}
          status={status}
          title={headerTitle}
        />
      }
      inspector={page === "chat" ? (
        <ProjectInspector
          agents={{ ajanlar: agentCardsForMessages(active.messages), canli: active.running, onCancel: active.turnId ? async (agentId) => {
            const result = await active.client.request("ajan.durdur", { agentId, turnId: active.turnId });
            if (result.ok !== true) throw new Error(String(result.metin ?? "Alt ajan durdurulamadı."));
          } : undefined }}
          activeTab={inspectorLayout.activeTab}
          client={active.client}
          collapsed={inspectorLayout.collapsed}
          height={inspectorLayout.height}
          key={active.id}
          onActiveTabChange={inspectorLayout.setActiveTab}
          onCollapsedChange={inspectorLayout.setCollapsed}
          onHeightChange={inspectorLayout.setHeight}
          onSelectPath={setSelectedPath}
          onWidthChange={inspectorLayout.setWidth}
          placement={inspectorPlacement}
          requestedPreview={requestedPreview}
          root={active.root}
          selectedPath={selectedPath}
          width={inspectorLayout.width}
        />
      ) : undefined}
      inspectorCollapsed={inspectorLayout.collapsed}
      inspectorHeight={inspectorLayout.height}
      inspectorPlacement={inspectorPlacement}
      inspectorOpen={page === "chat" && surfaceSection === null && layout.inspectorOpen}
      inspectorWidth={inspectorLayout.width}
      onInspectorClose={layout.closeInspector}
      sidebar={
        <Sidebar
          collapsed={layout.sidebarCollapsed}
          availableSources={history.sources.map((source) => source.ad)}
          etkin={active.id}
          {...projectSidebarProps}
          onMove={(id, root) => controller.move(id, root)}
          onNavigate={(destination) => void navigateSidebar(destination)}
          onSec={(id) => {
            setSurfaceSection(null);
            setPage("chat");
            // Açık sekme seçilir; diskte duran sohbet ise ÖNCE açılır. İkisi de
            // aynı listede durur: kullanıcı için ikisi de "dünkü konuşmam"dır.
            if (controller.state.sessions[id]) controller.select(id);
            else void controller.openStored(id, controller.storedConversations.find((item) => item.id === id)?.root ?? active?.root);
          }}
          onYeni={() => { setSurfaceSection(null); void startDesktopChat(); }}
          oturumlar={[
            ...controller.sessions.map((session) => ({
              session_id: session.id,
              source: session.source,
              title: session.title,
              project: projectName(session.root),
              projectRoot: session.root,
              projectId: projects.registry.chats[session.id],
              updated_at: session.updatedAt,
            })),
            // Diskte duran ama açılmamış sohbetler. Ölçüldü (kullanıcının diski,
            // 8 Eylül): 110 sohbet kayıtlıydı ve arayüzde hiçbiri görünmüyordu.
            ...controller.storedConversations
              .filter((conversation) => !controller.state.sessions[conversation.id])
              .map((conversation) => ({
                session_id: conversation.id,
                source: "fusion",
                title: conversation.title,
                project: projectName(conversation.root),
                projectRoot: conversation.root,
                projectId: projects.registry.chats[conversation.id],
                updated_at: conversation.updatedAt * 1000,
              })),
          ]}
          guncellemeSurumu={guncellemeSurumu}
          onGuncellemeAc={() => setPage("settings")}
          hesap={etkinHesap}
          onCikis={() => {
            // Çıkış sonrası pencere yeniden yüklenir: hesabın yapılandırması
            // ancak yeni bir çekirdek sürecinde bırakılabilir.
            void account.cikis().then((tamam) => { if (tamam) window.location.reload(); });
          }}
        />
      }
      sidebarCollapsed={layout.sidebarCollapsed}
      onSidebarClose={layout.toggleSidebar}
    />
    </>
  );
}

export function CoreConnectedApp({ transport }: { transport?: SessionTransport } = {}) {
  return <SessionUygulama transport={transport} />;
}

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Approval } from "./dialogs/Approval";
import { CloseConfirm } from "./dialogs/CloseConfirm";
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
import { useSessions } from "./sessions/useSessions";
import type { SessionTransport } from "./sessions/types";
import { AppHeader } from "./screens/AppHeader";
import {
  Composer,
  type ApprovalMode,
  type ComposerAttachment,
  type ComposerCommand,
  type DosyaOnerisi,
} from "./screens/Composer";
import { Conversation, type Mesaj } from "./screens/Conversation";
import type { ModelOption } from "./screens/ModelPicker";
import { EmptyState } from "./screens/EmptyState";
import { Inspector, type InspectorTabId } from "./screens/Inspector";
import { Shell } from "./screens/Shell";
import { Sidebar } from "./screens/Sidebar";
import { useLayout } from "./state/useLayout";
import { useInspectorLayout } from "./state/useInspectorLayout";
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
import { ProjectPicker } from "./screens/ProjectPicker";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import {
  kabukVar,
  onVoiceBargeIn,
  onVoiceMessage,
  onVoiceAnswer,
  onVoicePrefsRequest,
  publishVoiceAsk,
  publishVoicePrefs,
  publishVoiceRuntimeState,
  type VoicePrefsPayload,
} from "./voice/bridge";
import { openVoiceWindow } from "./voice/windowBridge";
import { findVoiceAnswer, speakVoiceAnswer, type VoiceTurnHandle } from "./voice/voiceTurn";
import { AccountGate } from "./account/AccountGate";
import { AccountScreen } from "./account/AccountScreen";
import { useAccount } from "./account/useAccount";
import { Onboarding, type OnboardingValue } from "./onboarding";
import type { ApprenticeStatus, DiscoveredSource, ProviderSummary, SampleProject } from "./onboarding";
import { selectDirectory, selectFiles as selectLocalFiles } from "./platform/dialog";
import { PermissionPrompt } from "./permissions/PermissionPrompt";
import { usePermissions } from "./permissions/usePermissions";
import { useDictation } from "./voice/useDictation";
import type { PermissionBridge } from "./permissions/types";
import { nativePermissionBridge } from "./platform/permissions";
import { listenForFileDrops } from "./platform/drop";

/** Sohbetin içinden çalışma klasörünü değiştiren komut. */
const FOLDER_COMMAND = {
  ad: "klasor",
  aciklama: "Çalışma klasörünü değiştir",
  destekleniyor: true,
  grup: "Çalışma alanı",
  kullanim: "/klasor",
};

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
      setMessages((current) => olayEkle(current, event));
    });
    client.onQuestion((id, data) => {
      if (data.tur === "onay") setQuestion({ id, data: data as unknown as Soru });
    });
  }, [client]);

  const send = (task: string) => {
    setRunning(true);
    setMessages((current) => [...current, { rol: "kullanici", metin: task }]);
    void client
      .request("tur.calistir", { gorev: task })
      .then((result) => {
        const text = typeof result.metin === "string" ? result.metin : "";
        if (text) setMessages((current) => [...current, { rol: "asistan", metin: text }]);
      })
      .catch((error) =>
        setMessages((current) => [...current, { rol: "asistan", metin: `Hata: ${String(error)}` }]),
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
type TemaIstemcisi = Pick<ProtocolClient, "request">;

function useAppTheme(client?: TemaIstemcisi) {
  const [themePreference, setThemePreference] = useState<ThemePreference>(readThemePreference);

  // Tercih YAPILANDIRMADAN okunur; `localStorage` yalnız ilk boyamayı hızlandıran
  // önbellektir. Ölçüldü (11 Eylül): webview'in LocalStorage deposu kullanıcının
  // kurulumunda hiç yazılmıyordu (0 bayt) ve yazma hatası yutulduğu için tercih
  // her açılışta `system`'e düşüyor, macOS koyu temadayken içerik beyaz kalıyordu.
  useEffect(() => {
    if (!client) return;
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
        // Yapılandırma okunamazsa önbellekteki tercihle devam edilir.
      }
    })();
    return () => {
      iptal = true;
    };
  }, [client]);

  useEffect(() => {
    applyTheme(themePreference);
    if (themePreference !== "system" || !window.matchMedia) return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => applyTheme("system", document.documentElement, media.matches);
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

function ProjectInspector({
  activeTab,
  client,
  collapsed,
  onActiveTabChange,
  onCollapsedChange,
  onSelectPath,
  onWidthChange,
  root,
  selectedPath,
  width,
}: {
  activeTab: InspectorTabId;
  client: ProtocolClient;
  collapsed: boolean;
  onActiveTabChange: (tab: InspectorTabId) => void;
  onCollapsedChange: (collapsed: boolean) => void;
  /** Seçili dosya DIŞARIDAN yönetilir: sohbetteki kod kartı da bir dosya açar. */
  onSelectPath: (path: string | null) => void;
  onWidthChange: (width: number) => void;
  root: string;
  selectedPath: string | null;
  width: number;
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
      onActiveTabChange={onActiveTabChange}
      onCollapsedChange={onCollapsedChange}
      onWidthChange={onWidthChange}
      width={width}
      content={{
        files: <FileExplorer client={client} key={revision} onChanged={changed} onSelected={onSelectPath} root={root} />,
        // Doğrulama komutları DEĞİŞİKLİKLER sekmesinde: "ne değişti" ile
        // "hâlâ çalışıyor mu" aynı soruya bakar. Ayrı 'Testler' sekmesi git
        // durumunu ikinci kez gösteriyordu.
        changes: (
          <>
            <ChangesPanel client={client} onChanged={changed} revision={revision} />
            <TestsPanel client={client} processes={processes} />
          </>
        ),
        terminal: <TerminalPanel cwd={root} />,
        preview: <PreviewPanel client={client} selectedPath={selectedPath} />,
      }}
    />
  );
}

export function Uygulama({ istemci }: { istemci: ProtocolClient }) {
  const conversation = useConversation(istemci);
  const layout = useLayout();
  const inspectorLayout = useInspectorLayout();
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
            <Approval onCevap={conversation.answer} soru={conversation.question.data} />
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
          activeTab={inspectorLayout.activeTab}
          collapsed={inspectorLayout.collapsed}
          onActiveTabChange={inspectorLayout.setActiveTab}
          onCollapsedChange={inspectorLayout.setCollapsed}
          onWidthChange={inspectorLayout.setWidth}
          width={inspectorLayout.width}
        />
      }
      inspectorCollapsed={inspectorLayout.collapsed}
      inspectorOpen={layout.inspectorOpen}
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

function ConnectedOnboarding({
  client,
  projects,
  runtimeVersion,
  onFinish,
}: {
  client: ProtocolClient;
  projects: SampleProject[];
  runtimeVersion?: string;
  onFinish: (projectId: string | null) => void;
}) {
  const [value, setValue] = useState<OnboardingValue>({ step: "welcome", selectedProjectId: null });
  const [sources, setSources] = useState<DiscoveredSource[]>([
    { kind: "claude", status: "not-found" },
    { kind: "codex", status: "not-found" },
    { kind: "hermes", status: "not-found" },
  ]);
  const [providers, setProviders] = useState<ProviderSummary[]>([]);
  // Faz 3, Görev 2 (C5/C9): agent şu an ücretsiz API çırağıyla mı çalışıyor?
  // Kaynak `kontrol.durum`'un `model.cirak_aktif`/`model.onerilen_cirak` alanları
  // — bu bileşen kendi başına HESAPLAMAZ (tek kaynak `providers/capabilities.py`).
  const [apprentice, setApprentice] = useState<ApprenticeStatus>({
    active: true,
    recommendedModel: null,
  });

  const refreshControlStatus = useCallback(() => {
    return client.request("kontrol.durum", {}).then((control) => {
      const rows = Array.isArray(control.saglayicilar) ? control.saglayicilar : [];
      setProviders(rows.slice(0, 8).map((raw) => {
        const row = raw as Record<string, unknown>;
        const configured = row.kurulu === true;
        return {
          id: String(row.id ?? ""),
          name: String(row.ad ?? row.id ?? "Sağlayıcı"),
          secretConfigured: configured,
          status: configured ? "ready" : "needs-setup",
        };
      }));
      const model = (control.model ?? {}) as Record<string, unknown>;
      setApprentice({
        active: model.cirak_aktif !== false,
        recommendedModel:
          typeof model.onerilen_cirak === "string" ? model.onerilen_cirak : null,
      });
      return control;
    });
  }, [client]);

  useEffect(() => {
    let alive = true;
    void Promise.all([
      client.request("gecmis.kaynaklar", {}),
      refreshControlStatus(),
    ]).then(([history]) => {
      if (!alive) return;
      const found = new Set(
        Array.isArray(history.kaynaklar)
          ? history.kaynaklar.map((item) => String((item as Record<string, unknown>).ad ?? ""))
          : [],
      );
      setSources((["claude", "codex", "hermes"] as const).map((kind) => ({
        kind,
        status: found.has(kind) ? "found" : "not-found",
        itemCount: found.has(kind) ? 1 : 0,
      })));
    }).catch(() => undefined);
    return () => { alive = false; };
  }, [client, refreshControlStatus]);

  const handleResetToApprentice = useCallback(() => {
    // Kalıcılaştırma ve gerçek geçiş SUNUCUDA olur (`kontrol.cirak_varsayilanina_don`
    // → `config/model_select.py::reset_to_apprentice_default`); burada yalnızca
    // isteği yollayıp güncel durumu yeniden okuruz.
    void client.request("kontrol.cirak_varsayilanina_don", {}).then(() => refreshControlStatus());
  }, [client, refreshControlStatus]);

  return (
    <Onboarding
      apprentice={apprentice}
      onChange={setValue}
      onComplete={({ selectedProjectId }) => onFinish(selectedProjectId)}
      onResetToApprentice={handleResetToApprentice}
      onSkip={() => onFinish(null)}
      projects={projects}
      providers={providers}
      runtime={{ status: "ready", version: runtimeVersion }}
      sources={sources}
      value={value}
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
  const layout = useLayout();
  const inspectorLayout = useInspectorLayout();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [attachments, setAttachments] = useState<Record<string, ComposerAttachment[]>>({});
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [commandSelector, setCommandSelector] = useState<CommandSelectorPayload | null>(null);
  const [controlRevision, setControlRevision] = useState(0);
  const [commandBusy, setCommandBusy] = useState(false);
  const [commandError, setCommandError] = useState<string | null>(null);
  const [commands, setCommands] = useState<ComposerCommand[]>([]);
  const [activeModel, setActiveModel] = useState("");
  const [activeModelLabel, setActiveModelLabel] = useState("");
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([]);
  const [modelsBusy, setModelsBusy] = useState(false);
  const [fileSuggestions, setFileSuggestions] = useState<DosyaOnerisi[]>([]);
  //: En son gönderilen `@` sorgusunun sırası. Geç gelen cevap yenisini EZMEZ:
  //: kullanıcı yazmaya devam ettiğinde eski sorgunun sonucu listeyi geri almamalı.
  const fileQuerySeq = useRef(0);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [newTaskOpen, setNewTaskOpen] = useState(false);
  const [newTaskBusy, setNewTaskBusy] = useState(false);
  const [newTaskError, setNewTaskError] = useState<string | null>(null);
  const [page, setPage] = useState<"chat" | "skills" | "control" | "connectors" | "help" | "settings" | "account" | "image-create" | "video-create">("chat");
  // "Ayarlar" ve "Kontrol Paneli" aynı ekranı açar; başlık hangi kapıdan
  // girildiğini söyler, yoksa kullanıcı yanlış yere gittiğini sanıyordu.
  const [controlTitle, setControlTitle] = useState("Kontrol Paneli");
  // Seçili dosya BURADA durur: hem çalışma panelindeki ağaç hem sohbetteki
  // kod kartı aynı seçimi değiştirir.
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const showSteps = useShowSteps();
  // İzin modu arayüzde GERÇEK durumu göstermeli: eskiden "Agent · Otomatik"
  // sabit yazıyordu ve security'ye geçince bile değişmiyordu.
  const [approval, setApproval] = useState<ApprovalMode>("auto");
  const [closeAsked, setCloseAsked] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(onboarding);
  const voiceRequest = useRef<{
    afterIndex: number;
    sawRunning: boolean;
    sessionId: string;
  } | null>(null);
  const activeVoiceTurn = useRef<VoiceTurnHandle | null>(null);
  const pendingBargeIn = useRef(false);
  const active = controller.activeSession;
  const dictation = useDictation((id, text) =>
    setDrafts((current) => ({ ...current, [id]: text })),
  );
  useEffect(() => {
    if (dictation.listening) void dictation.stop();
  }, [active?.id]);
  // Hesap kapısı onboarding'den ÖNCE gelir: kimin kurulum yaptığı belli olmalı.
  const account = useAccount(active?.client ?? null);
  const etkinHesap =
    account.durum?.hesaplar.find((item) => item.kimlik === account.durum?.etkin) ?? null;
  const guncellemeSurumu = useUpdateAvailable();
  const inspectorPlacement = useInspectorPlacement();
  const [dogrulamaUyarisi, setDogrulamaUyarisi] = useState<string | null>(null);
  // Sağlayıcı insan doğrulaması isterse Fusion tek başına ilerleyemez. Bu,
  // sohbetin içine gömülü bir hata satırı olarak kayboluyordu; kullanıcı neden
  // durduğunu anlamıyordu. Artık kart olarak görünür ve eylem sunar.
  const sonAsistanMetni = [...(active?.messages ?? [])].reverse()
    .find((mesaj) => mesaj.rol === "asistan")?.metin ?? "";
  useEffect(() => {
    if (insanDogrulamasiGerekiyor(sonAsistanMetni)) setDogrulamaUyarisi(sonAsistanMetni);
  }, [sonAsistanMetni]);
  const { changeTheme, themePreference } = useAppTheme(active?.client);
  const hasOpenedSession = useRef(false);
  useEffect(() => { if (active) hasOpenedSession.current = true; }, [active]);
  const startDesktopChat = async () => {
    setNewTaskError(null);
    try {
      const root = await desktopDir();
      await controller.create({ root });
      setPage("chat");
    } catch {
      setNewTaskError("Desktop klasörü açılamadı. Yeniden dene veya bir klasör seç.");
    }
  };
  const history = useHistory(active?.client ?? null);
  const navigateSidebar = async (destination: string) => {
    setNewTaskError(null);
    try {
      if (!active && !["image-create", "video-create"].includes(destination) && !destination.startsWith("project:")) {
        await controller.create({ root: await desktopDir() });
      }
            if (destination === "image-create" || destination === "video-create") {
              setPage(destination);
            } else if (destination === "skills") {
              setPage("skills");
            } else if (destination === "help") {
              setPage("help");
            } else if (destination === "settings") {
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
              setPage("settings");

            } else if (destination === "new-project") {
              requestTaskFolder();

            } else if (destination.startsWith("resume:")) {
              setPage("chat");
              const source = destination.slice("resume:".length) as "claude" | "codex" | "hermes";
              setHistoryOpen(true);
              void history.openSource(source);
            } else if (destination.startsWith("project:")) {
              setPage("chat");
              await controller.create({ root: destination.slice("project:".length) });
            }
    } catch {
      setNewTaskError("Sayfa veya proje açılamadı. Yeniden dene.");
    }
  };
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
    if (!active) return;
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
        [active.id]: [...(current[active.id] ?? []), ...additions]
          .filter((item, index, all) => all.findIndex((other) => other.path === item.path) === index),
      }));
    }).then((stop) => {
      if (alive) unlisten = stop;
      else stop();
    }).catch(() => {
      if (alive) setAttachmentError("Sürükle-bırak dinleyicisi başlatılamadı. Uygulamayı yeniden dene.");
    });
    return () => { alive = false; unlisten?.(); };
  }, [active?.id]);

  // Etkin model oturumun yapılandırmasından gelir; istemcide önbelleğe alınmaz.
  // `controlRevision` bağımlılıktır: `/model` komutu modeli değiştirdiğinde
  // composer'daki ad da tazelenmeli, yoksa eski model yazılı kalırdı.
  useEffect(() => {
    if (!active) return;
    let alive = true;
    void active.client
      .request("kontrol.durum", {})
      .then((payload) => {
        if (!alive || payload.ok !== true) return;
        const modelState = payload.model as { agent?: unknown; agent_label?: unknown } | undefined;
        const model = modelState?.agent;
        if (typeof model === "string") setActiveModel(model);
        setActiveModelLabel(typeof modelState?.agent_label === "string" ? modelState.agent_label : "");
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [active, controlRevision]);

  /** Etkin sağlayıcıların canlı katalogda bulunan modellerini oku. */
  const loadModelOptions = useCallback(async () => {
    if (!active) return;
    setModelsBusy(true);
    setModelOptions([]);
    try {
      const sonuc = await active.client.request("model.katalog", {});
      const modeller = Array.isArray(sonuc.modeller) ? sonuc.modeller : [];
      setModelOptions(
        modeller.flatMap((raw) => {
          if (!raw || typeof raw !== "object") return [];
          const row = raw as Record<string, unknown>;
          if (typeof row.model !== "string" || !row.model || typeof row.kaynak !== "string") return [];
          return [{
            deger: `/development uygula ${row.kaynak} ${row.model}`,
            modelId: row.model,
            etiket: typeof row.etiket === "string" ? row.etiket : row.model,
            aciklama: typeof row.aciklama === "string" ? row.aciklama : "",
            grup: typeof row.grup === "string" ? row.grup : "diger",
          }];
        }),
      );
    } catch {
      setModelOptions([]);
    } finally {
      setModelsBusy(false);
    }
  }, [active]);

  useEffect(() => {
    if (!active) return;
    let alive = true;
    void Promise.all([
      active.client.request("komut.listele", {}),
      active.client.request("yetenek.katalog", {}),
    ]).then(([commandPayload, capabilityPayload]) => {
      if (!alive) return;
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
      setCommands([...commandRows, ...mcpRows]);
    }).catch(() => { if (alive) setCommands([]); });
    return () => { alive = false; };
  }, [active?.client, active?.id]);

  // Kapatma isteği Rust'ta durdurulur ve karar burada sorulur.
  useEffect(() => {
    if (!kabukVar()) return;
    const cikar = listen("uygulama://kapatma-istegi", () => setCloseAsked(true));
    return () => void cikar.then((f) => f()).catch(() => undefined);
  }, []);

  // Konuşma penceresinden gelen söz AYNI sohbete düşer: kip kapandığında
  // kullanıcı yazışmış gibi tam dökümü görür.
  useEffect(() => {
    if (!active) return;
    const cikar = onVoiceMessage((mesaj) => {
      if (mesaj.kaynak !== "kullanici") return;
      // Sözü kesildiyse modele NE söylerken kesildiği de gider. Bu bağlam
      // olmadan model yarım bıraktığı cevabı bilmez ve kullanıcının
      // düzeltmesini yeni bir soru sanar.
      const gorev = mesaj.kesilen
        ? `${mesaj.metin}\n\n[Sesli konuşma: sen "${mesaj.kesilen}" derken sözün kesildi.`
          + ` Yarım kalan cevabınla kullanıcının bu son sözünü birlikte değerlendir;`
          + ` baştan tekrar etme.]`
        : mesaj.metin;
      const accepted = controller.send(active.id, gorev, []);
      if (!accepted) {
        void publishVoiceRuntimeState({
          durum: "error",
          metin: "Bu konuşmada bir görev zaten çalışıyor. Bitmesini bekleyip yeniden konuş.",
        });
        return;
      }
      voiceRequest.current = {
        afterIndex: active.messages.length,
        sawRunning: false,
        sessionId: active.id,
      };
      void publishVoiceRuntimeState({ durum: "thinking" });
    });
    return () => void cikar.then((f) => f()).catch(() => undefined);
  }, [active, controller]);

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
    const pending = voiceRequest.current;
    if (!pending) return;
    const session = controller.state.sessions[pending.sessionId];
    if (!session) {
      voiceRequest.current = null;
      return;
    }
    if (session.running) {
      pending.sawRunning = true;
      return;
    }
    if (!pending.sawRunning) return;
    voiceRequest.current = null;
    const answer = findVoiceAnswer(session.messages, pending.afterIndex);
    if (!answer) {
      void publishVoiceRuntimeState({ durum: "error", metin: "Fusion yanıt üretmedi." });
      return;
    }
    pendingBargeIn.current = false;
    void speakVoiceAnswer(session.client, answer, publishVoiceRuntimeState)
      .then((turn) => {
        activeVoiceTurn.current = turn;
        if (pendingBargeIn.current) void turn.cancel().catch(() => undefined);
        void turn.finished.finally(() => {
          if (activeVoiceTurn.current === turn) activeVoiceTurn.current = null;
        }).catch(() => undefined);
      })
      .catch(() => undefined);
  }, [controller.state.sessions]);

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
        model: typeof satir.model === "string" ? satir.model : null,
        robotik: typeof satir.robotik === "number" ? satir.robotik : 0.5,
      });
    };
    const cikar = onVoicePrefsRequest((istek) => void yayinla(istek).catch(() => undefined));
    return () => void cikar.then((f) => f()).catch(() => undefined);
  }, [active]);

  // Açık onay konuşma penceresine de yayılır ve oradan gelen cevap aynı
  // `answer` yolundan geçer: iki ayrı onay mantığı olsaydı biri düzeltilirken
  // öteki eskirdi.
  useEffect(() => {
    if (!active) return;
    const soru = active.question;
    void publishVoiceAsk(
      soru
        ? {
            acik: true,
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
    if (!active) return;
    const id = active.id;
    // Cevap biçimi ana penceredeki onay kutusuyla AYNIDIR: `{ secim }`.
    const cikar = onVoiceAnswer((cevap) => controller.answer(id, { secim: cevap }));
    return () => void cikar.then((f) => f()).catch(() => undefined);
  }, [active?.id, controller]);

  if (controller.state.connectionError) {
    return <div className="app-status-screen">Hata: {controller.state.connectionError}</div>;
  }
  if (!active) {
    if (!hasOpenedSession.current) return <div className="app-status-screen">Hazırlanıyor…</div>;
    return <Shell
      header={<AppHeader title="Yeni sohbet" status="Hazır" inspectorOpen={false} onToggleInspector={() => undefined} onToggleSidebar={layout.toggleSidebar} sidebarCollapsed={layout.sidebarCollapsed} />}
      content={<>{page === "image-create" || page === "video-create" ? <section className="empty-state"><div className="empty-state__content"><h2>{page === "image-create" ? "Görsel oluştur" : "Video oluştur"}</h2><p>Daha sonra</p><button type="button" onClick={() => setPage("chat")}>Sohbete dön</button></div></section> : <EmptyState projectName="Desktop" />}{newTaskError && <p role="alert">{newTaskError}</p>}<button type="button" onClick={() => void startDesktopChat()}>Desktop içinde yeni sohbet başlat</button></>}
      sidebarCollapsed={layout.sidebarCollapsed}
      onSidebarClose={layout.toggleSidebar}
      sidebar={<Sidebar collapsed={layout.sidebarCollapsed} etkin={null} onNavigate={(destination) => void navigateSidebar(destination)} onSil={(id) => controller.remove(id)} onMove={(id, root) => controller.move(id, root)} onYeni={() => void startDesktopChat()} onSec={(id) => { void controller.openStored(id).catch(() => setNewTaskError("Sohbet açılamadı. Yeniden dene.")); }} oturumlar={controller.storedConversations.map((conversation) => ({ session_id: conversation.id, source: "fusion", title: conversation.title, project: projectName(conversation.root), projectRoot: conversation.root, updated_at: conversation.updatedAt * 1000 }))} />}
    />;
  }

  // Fusion hesapsız açılmaz. Kapı, çekirdek bağlandıktan sonra çizilir:
  // hesap bilgisi oradan okunuyor.
  if (active && !account.yukleniyor && account.durum && !account.durum.etkin) {
    return <AccountGate account={account} />;
  }

  if (showOnboarding) {
    const projects: SampleProject[] = [
      { id: active.root, name: projectName(active.root), description: "Şu anda açık olan çalışma alanı", path: active.root },
      ...controller.recentProjects.filter((project) => project.root !== active.root).slice(0, 3).map((project) => ({
        id: project.root, name: project.name, description: "Yakın zamanda kullanılan proje", path: project.root,
      })),
    ];
    return (
      <ConnectedOnboarding
        client={active.client}
        onFinish={(projectId) => {
          setShowOnboarding(false);
          onOnboardingComplete();
          if (projectId && projectId !== active.root) void controller.create({ root: projectId });
        }}
        projects={projects}
        runtimeVersion={runtimeVersion}
      />
    );
  }

  // Kendi başlığını taşıyan tam ekran sayfalarda üst şerit o başlığı TEKRARLAMAZ.
  // Ölçüldü: Ayarlar açıkken ekranda "Ayarlar" iki kez yazıyordu ve erişilebilirlik
  // ağacında aynı adla iki başlık düğümü oluşuyordu. Şerit bu sayfalarda çalışma
  // alanını gösterir; sayfanın kimliği sayfanın kendi başlığındadır.
  const headerTitle = page === "settings" ? active.title
    : SAYFA_KENDI_BASLIGINI_TASIR.includes(page)
    ? projectName(active.root)
    : page === "image-create" ? "Görsel oluştur"
      : page === "video-create" ? "Video oluştur"
        : page === "skills" ? "Beceriler ve Ajanlar"
          : page === "help" ? "Yardım"
            : active.title;

  const draft = drafts[active.id] ?? "";
  const activeAttachments = attachments[active.id] ?? [];
  const setDraft = (value: string) => setDrafts((current) => ({ ...current, [active.id]: value }));
  const executeCommand = async (input: string, recordInput = true) => {
    setCommandBusy(true);
    setCommandError(null);
    try {
      const result = await controller.runCommand(active.id, input, recordInput);
      const next = commandSelectorFrom(result.secici);
      setCommandSelector(next);
      // Çekirdek `/clear` için EKRAN temizleme sinyali döner; afiş basmaz.
      if (result.temizle === true) controller.clear(active.id);
      // Komut yapılandırmayı değiştirmiş olabilir; panel eski değeri göstermesin.
      if (next === null) setControlRevision((current) => current + 1);
      if (result.ok === false) setCommandError(String(result.metin ?? "Komut tamamlanamadı."));
    } catch {
      setCommandError("Komut çalıştırılamadı. Bağlantıyı kontrol edip yeniden dene.");
    } finally {
      setCommandBusy(false);
    }
  };
  const send = (task: string) => {
    const resumeSource = task.match(/^\/resume(claude|codex|hermes)$/i)?.[1]?.toLocaleLowerCase("tr") as "claude" | "codex" | "hermes" | undefined;
    if (resumeSource && history.sources.some((source) => source.ad === resumeSource)) {
      setHistoryOpen(true);
      void history.openSource(resumeSource);
    } else if (task.trim().toLocaleLowerCase("tr") === `/${FOLDER_COMMAND.ad}`) {
      // Klasör değiştirme UYGULAMA tarafı iştir: çekirdeğin kökü açılışta
      // belirlenir, bu yüzden komutu çekirdeğe göndermek anlamsız olurdu.
      void requestTaskFolder();
    } else if (task.startsWith("/")) void executeCommand(task);
    else {
      controller.send(active.id, task, activeAttachments);
      setAttachments((current) => ({ ...current, [active.id]: [] }));
    }
    setDraft("");
  };
  const conversationContent = active.messages.length > 0 ? (
    <Conversation
      mesajlar={active.messages}
      running={active.running}
      showSteps={showSteps}
      onOneriSec={(gorev) => send(gorev)}
      onOpenFile={(path) => {
        setSelectedPath(path);
        // Dosyanın İÇERİĞİNİ gösteren sekme önizlemedir; ağaç sekmesi yalnız
        // klasörü açardı ve kullanıcı tıkladığı dosyayı göremezdi.
        inspectorLayout.setActiveTab("preview");
        layout.openInspector();
      }}
    />
  ) : (
    <EmptyState durum={active.running ? "thinking" : "idle"} projectName={projectName(active.root)} onSelectPrompt={setDraft} />
  );
  const content = page === "image-create" || page === "video-create"
    ? <section className="empty-state"><div className="empty-state__content"><h2>{page === "image-create" ? "Görsel oluştur" : "Video oluştur"}</h2><p>Daha sonra</p><button type="button" onClick={() => setPage("chat")}>Sohbete dön</button></div></section>
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
          <>{conversationContent}<Settings
            client={active.client}
            onChangeRoot={() => void requestTaskFolder()}
            onClose={() => setPage("chat")}
            onOpenAccount={() => setPage("account")}
            onRunCommand={(command) => executeCommand(command, false)}
            onThemeChange={changeTheme}
            themePreference={themePreference}
          /></>
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
    ? "Bağlantı kesildi"
    : active.running
      ? "Çalışıyor"
      : "Hazır";
  const chooseTaskFolder = async () => {
    setNewTaskBusy(true);
    setNewTaskError(null);
    try {
      const storedRoot = localStorage.getItem("fusion.last-project-root") ?? undefined;
      const root = (await selectFolder(storedRoot === "/" ? undefined : storedRoot))?.trim();
      if (!root) {
        setNewTaskOpen(false);
        return;
      }
      if (root === "/") {
        setNewTaskError("Kök dizin yerine çalışacağın proje klasörünü seç.");
        return;
      }
      await controller.create({ root });
      localStorage.setItem("fusion.last-project-root", root);
      setPage("chat");
      setNewTaskOpen(false);
    } catch {
      setNewTaskError("Klasör açılamadı. Erişimi kontrol edip yeniden dene.");
    } finally {
      setNewTaskBusy(false);
    }
  };
  function requestTaskFolder() {
    void permissions.ensure("workspace").then((granted) => {
      if (granted) void chooseTaskFolder();
    });
  }

  return (
    <Shell
      emptyChat={(page === "chat" || page === "settings") && active.messages.length === 0 && !active.running}
      composer={page === "chat" || page === "settings" ? (
        <><ProjectPicker root={active.root} projects={controller.recentProjects} onSelect={async (root) => { await controller.create({ root }); setPage("chat"); }} onNew={() => requestTaskFolder()} onSettings={() => { setControlTitle("Proje ayarları"); setPage("control"); }} />
        <Composer
          activeModel={activeModel}
          activeModelLabel={activeModelLabel}
          modelOptions={modelOptions}
          modelsBusy={modelsBusy}
          onModelMenuOpen={() => void loadModelOptions()}
          onModelSelect={(komut) => void executeCommand(komut, false)}
          approval={approval}
          onApprovalChange={(next) => {
            setApproval(next);
            void active.client.request("oturum.baslat", { mod: next });
          }}
          attachments={activeAttachments}
          attachmentError={attachmentError ?? commandError}
          commands={composerCommands}
          fileSuggestions={fileSuggestions}
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
            const additions = files.flatMap((file): ComposerAttachment[] => {
              const localPath = (file as File & { path?: string }).path || file.webkitRelativePath || file.name;
              if (!localPath.trim()) return [];
              return [{ kind: file.type.startsWith("image/") ? "image" : "file", name: file.name, path: localPath }];
            });
            if (files.length > 0 && additions.length === 0) {
              setAttachmentError("Sürüklenen öğelerde geçerli bir dosya yolu bulunamadı.");
              return;
            }
            setAttachments((current) => ({ ...current, [active.id]: [...(current[active.id] ?? []), ...additions] }));
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
      content={
        <>
          {content}
          {newTaskError && !newTaskOpen && <p role="alert">{newTaskError}</p>}
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
          {closeAsked && (
            <CloseConfirm
              onCancel={() => setCloseAsked(false)}
              onConfirm={() => void invoke("kapatmayi_onayla")}
              running={active.running}
            />
          )}
          {shareOpen && (
            <ShareDialog
              messages={active.messages}
              onClose={() => setShareOpen(false)}
              title={active.title}
            />
          )}
          {active.question && (
            <Approval
              onCevap={(answer) => controller.answer(active.id, answer)}
              soru={active.question.data}
            />
          )}
          {historyOpen && (
            <HistoryPicker
              history={history}
              onClose={() => setHistoryOpen(false)}
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
            onCancel={() => { setNewTaskError(null); setNewTaskOpen(false); }}
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
              canOpenSettings={permissions.activeKind === "microphone" || permissions.activeKind === "speech"}
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
              open
              selector={commandSelector}
            />
          )}
        </>
      }
      header={
        <AppHeader
          inspectorOpen={layout.inspectorOpen}
          onShare={page === "chat" && active.messages.some((message) => message.rol === "kullanici" || message.rol === "asistan") ? () => setShareOpen(true) : undefined}
          onToggleInspector={layout.toggleInspector}
          onToggleSidebar={layout.toggleSidebar}
          sidebarCollapsed={layout.sidebarCollapsed}
          status={status}
          title={headerTitle}
        />
      }
      inspector={page === "chat" || page === "settings" ? (
        <ProjectInspector
          activeTab={inspectorLayout.activeTab}
          client={active.client}
          collapsed={inspectorLayout.collapsed}
          key={active.id}
          onActiveTabChange={inspectorLayout.setActiveTab}
          onCollapsedChange={inspectorLayout.setCollapsed}
          onSelectPath={setSelectedPath}
          onWidthChange={inspectorLayout.setWidth}
          root={active.root}
          selectedPath={selectedPath}
          width={inspectorLayout.width}
        />
      ) : undefined}
      inspectorCollapsed={inspectorLayout.collapsed}
      inspectorPlacement={inspectorPlacement}
      inspectorOpen={(page === "chat" || page === "settings") && layout.inspectorOpen}
      inspectorWidth={inspectorLayout.width}
      onInspectorClose={layout.closeInspector}
      sidebar={
        <Sidebar
          collapsed={layout.sidebarCollapsed}
          availableSources={history.sources.map((source) => source.ad)}
          etkin={active.id}
          onSil={(id) => controller.remove(id)}
          onMove={(id, root) => controller.move(id, root)}
          onNavigate={(destination) => void navigateSidebar(destination)}
          onSec={(id) => {
            setPage("chat");
            // Açık sekme seçilir; diskte duran sohbet ise ÖNCE açılır. İkisi de
            // aynı listede durur: kullanıcı için ikisi de "dünkü konuşmam"dır.
            if (controller.state.sessions[id]) controller.select(id);
            else void controller.openStored(id, controller.storedConversations.find((item) => item.id === id)?.root ?? active?.root);
          }}
          onYeni={() => void startDesktopChat()}
          oturumlar={[
            ...controller.sessions.map((session) => ({
              session_id: session.id,
              source: session.source,
              title: session.title,
              project: projectName(session.root),
              projectRoot: session.root,
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
                updated_at: conversation.updatedAt * 1000,
              })),
          ]}
          projeler={controller.recentProjects.map((project) => ({
            name: project.name,
            pinned: false,
            root: project.root,
            updated_at: project.updatedAt,
          }))}
          guncellemeSurumu={guncellemeSurumu}
          onGuncellemeAc={() => setPage("settings")}
          hesap={etkinHesap}
          onCikis={() => {
            // Çıkış sonrası pencere yeniden yüklenir: hesabın yapılandırması
            // ancak yeni bir çekirdek sürecinde bırakılabilir.
            void account.cikis().then(() => window.location.reload());
          }}
        />
      }
      sidebarCollapsed={layout.sidebarCollapsed}
      onSidebarClose={layout.toggleSidebar}
    />
  );
}

export function CoreConnectedApp({ transport }: { transport?: SessionTransport } = {}) {
  return <SessionUygulama transport={transport} />;
}

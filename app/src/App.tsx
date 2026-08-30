import { useEffect, useState } from "react";
import { Approval } from "./dialogs/Approval";
import { HistoryPicker } from "./dialogs/HistoryPicker";
import { NewTaskDialog } from "./dialogs/NewTaskDialog";
import { useHistory } from "./history/useHistory";
import { ProtocolClient } from "./protocol/client";
import { olayMetni } from "./protocol/olayMetni";
import type { Soru } from "./protocol/types";
import { useRuntime } from "./runtime/useRuntime";
import type { RuntimeTransport } from "./runtime/types";
import { useSessions } from "./sessions/useSessions";
import type { SessionTransport } from "./sessions/types";
import { AppHeader } from "./screens/AppHeader";
import { Composer, type WorkspaceMode } from "./screens/Composer";
import { Conversation, type Mesaj } from "./screens/Conversation";
import { EmptyState } from "./screens/EmptyState";
import { Inspector, type InspectorTabId } from "./screens/Inspector";
import { RuntimeSetup } from "./screens/RuntimeSetup";
import { Shell } from "./screens/Shell";
import { Sidebar } from "./screens/Sidebar";
import { useLayout } from "./state/useLayout";
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
import { ProcessesPanel } from "./processes/ProcessesPanel";
import { TerminalPanel } from "./processes/TerminalPanel";
import { useProcesses } from "./processes/useProcesses";
import { SkillsCatalog } from "./capabilities/SkillsCatalog";
import { ControlPanel } from "./control/ControlPanel";
import { Lessons } from "./lessons/Lessons";
import { Onboarding, type OnboardingValue } from "./onboarding";
import type { DiscoveredSource, ProviderSummary, SampleProject } from "./onboarding";
import { selectDirectory } from "./platform/dialog";

function useConversation(client: ProtocolClient) {
  const [messages, setMessages] = useState<Mesaj[]>([]);
  const [question, setQuestion] = useState<{ id: string; data: Soru } | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    void client.request("oturum.durum", {}).catch(() => undefined);
    client.onEvent((event) => {
      const text = olayMetni(event);
      if (text) setMessages((current) => [...current, { rol: "olay", metin: text }]);
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

function useAppTheme() {
  const [themePreference, setThemePreference] = useState<ThemePreference>(readThemePreference);

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
  };
  return { changeTheme, themePreference };
}

function projectName(root: string): string {
  const parts = root.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] ?? root;
}

function ProjectInspector({ client, requestedTab, root }: { client: ProtocolClient; requestedTab: InspectorTabId | null; root: string }) {
  const [revision, setRevision] = useState(0);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
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
      requestedTab={requestedTab}
      content={{
        files: <FileExplorer client={client} key={revision} onChanged={changed} onSelected={setSelectedPath} root={root} />,
        changes: <ChangesPanel client={client} onChanged={changed} revision={revision} />,
        terminal: <TerminalPanel controller={processes} />,
        processes: <ProcessesPanel controller={processes} />,
        tests: <TestsPanel client={client} processes={processes} />,
        preview: <PreviewPanel client={client} selectedPath={selectedPath} />,
      }}
    />
  );
}

export function Uygulama({ istemci }: { istemci: ProtocolClient }) {
  const conversation = useConversation(istemci);
  const layout = useLayout();
  const [draft, setDraft] = useState("");
  const { changeTheme, themePreference } = useAppTheme();
  const clear = () => {
    setDraft("");
    conversation.clear();
  };
  const content = conversation.messages.length > 0 ? (
    <Conversation mesajlar={conversation.messages} />
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
          onThemeChange={changeTheme}
          onToggleInspector={layout.toggleInspector}
          onToggleSidebar={layout.toggleSidebar}
          sidebarCollapsed={layout.sidebarCollapsed}
          status={conversation.running ? "Çalışıyor" : "Hazır"}
          themePreference={themePreference}
          title="Yeni görev"
        />
      }
      inspector={<Inspector />}
      inspectorOpen={layout.inspectorOpen}
      onInspectorClose={layout.closeInspector}
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

  useEffect(() => {
    let alive = true;
    void Promise.all([
      client.request("gecmis.kaynaklar", {}),
      client.request("kontrol.durum", {}),
    ]).then(([history, control]) => {
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
    }).catch(() => undefined);
    return () => { alive = false; };
  }, [client]);

  return (
    <Onboarding
      onChange={setValue}
      onComplete={({ selectedProjectId }) => onFinish(selectedProjectId)}
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
}: {
  transport?: SessionTransport;
  onboarding?: boolean;
  runtimeVersion?: string;
  onOnboardingComplete?: () => void;
  selectFolder?: (defaultPath?: string) => Promise<string | null>;
}) {
  const controller = useSessions(transport);
  const layout = useLayout();
  const { changeTheme, themePreference } = useAppTheme();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [historyOpen, setHistoryOpen] = useState(false);
  const [newTaskOpen, setNewTaskOpen] = useState(false);
  const [newTaskBusy, setNewTaskBusy] = useState(false);
  const [newTaskError, setNewTaskError] = useState<string | null>(null);
  const [page, setPage] = useState<"chat" | "skills" | "control" | "lessons">("chat");
  // "Ayarlar" ve "Kontrol Paneli" aynı ekranı açar; başlık hangi kapıdan
  // girildiğini söyler, yoksa kullanıcı yanlış yere gittiğini sanıyordu.
  const [controlTitle, setControlTitle] = useState("Kontrol Paneli");
  const [requestedTab, setRequestedTab] = useState<InspectorTabId | null>(null);
  // Varsayılan SOHBET: boş bir pencerede "merhaba" yazmak proje taraması
  // başlatmamalı. Kod kipine geçiş kullanıcının açık kararıdır.
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("sohbet");
  const [showOnboarding, setShowOnboarding] = useState(onboarding);
  const active = controller.activeSession;
  const history = useHistory(active?.client ?? null);

  if (controller.state.connectionError) {
    return <div className="app-status-screen">Hata: {controller.state.connectionError}</div>;
  }
  if (!active) return <div className="app-status-screen">Bağlanıyor…</div>;

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

  const draft = drafts[active.id] ?? "";
  const setDraft = (value: string) => setDrafts((current) => ({ ...current, [active.id]: value }));
  const send = (task: string) => {
    controller.send(active.id, task);
    setDraft("");
  };
  const conversationContent = active.messages.length > 0 ? (
    <Conversation mesajlar={active.messages} />
  ) : (
    <EmptyState onSelectPrompt={setDraft} />
  );
  /** Ders adımının işaret ettiği yüzeyi aç. Hiçbir şey çalıştırılmaz. */
  const openLessonTarget = (hedef: string) => {
    if (hedef === "yetenek") return setPage("skills");
    if (hedef === "kontrol") return setPage("control");
    if (hedef === "gecmis") {
      setPage("chat");
      return setHistoryOpen(true);
    }
    setPage("chat");
    layout.openInspector();
    setRequestedTab(hedef === "surec" ? "processes" : "files");
  };
  const content = page === "skills"
    ? <SkillsCatalog client={active.client} onClose={() => setPage("chat")} />
    : page === "control"
      ? <ControlPanel client={active.client} onClose={() => setPage("chat")} />
      : page === "lessons"
        ? (
          <Lessons
            client={active.client}
            onClose={() => setPage("chat")}
            onOpenTab={openLessonTarget}
            onUseComposer={(gorev) => {
              setPage("chat");
              setDraft(gorev);
            }}
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
      setWorkspaceMode("kod");
      setNewTaskOpen(false);
    } catch {
      setNewTaskError("Klasör açılamadı. Erişimi kontrol edip yeniden dene.");
    } finally {
      setNewTaskBusy(false);
    }
  };

  return (
    <Shell
      composer={page === "chat" ? (
        <Composer
          mode={workspaceMode}
          onModeChange={(next) => {
            setWorkspaceMode(next);
            void active.client.request("oturum.baslat", { kip: next });
          }}
          onSend={send}
          onStop={() => controller.stop(active.id)}
          onValueChange={setDraft}
          running={active.running}
          value={draft}
        />
      ) : undefined}
      content={
        <>
          {content}
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
              setWorkspaceMode("sohbet");
              void controller.create();
            }}
            onFolder={() => void chooseTaskFolder()}
            open={newTaskOpen}
          />
        </>
      }
      header={
        <AppHeader
          inspectorOpen={layout.inspectorOpen}
          onThemeChange={changeTheme}
          onToggleInspector={layout.toggleInspector}
          onToggleSidebar={layout.toggleSidebar}
          sidebarCollapsed={layout.sidebarCollapsed}
          status={status}
          themePreference={themePreference}
          title={page === "skills" ? "Beceriler ve Ajanlar" : page === "control" ? controlTitle : page === "lessons" ? "Dersler" : active.title}
        />
      }
      inspector={page === "chat" ? <ProjectInspector client={active.client} key={active.id} requestedTab={requestedTab} root={active.root} /> : undefined}
      inspectorOpen={page === "chat" && layout.inspectorOpen}
      onInspectorClose={layout.closeInspector}
      sidebar={
        <Sidebar
          collapsed={layout.sidebarCollapsed}
          availableSources={history.sources.map((source) => source.ad)}
          etkin={active.id}
          onSil={(id) => void controller.remove(id)}
          onNavigate={(destination) => {
            if (destination === "skills") {
              setPage("skills");
            } else if (destination === "lessons") {
              setPage("lessons");
            } else if (destination === "control-panel" || destination === "settings") {
              setControlTitle(destination === "settings" ? "Ayarlar" : "Kontrol Paneli");
              setPage("control");
            } else if (destination.startsWith("resume:")) {
              setPage("chat");
              const source = destination.slice("resume:".length) as "claude" | "codex" | "hermes";
              setHistoryOpen(true);
              void history.openSource(source);
            } else if (destination.startsWith("project:")) {
              setPage("chat");
              void controller.create({ root: destination.slice("project:".length) });
            }
          }}
          onSec={(id) => { setPage("chat"); controller.select(id); }}
          onYeni={() => { setNewTaskError(null); setNewTaskOpen(true); }}
          oturumlar={controller.sessions.map((session) => ({
            session_id: session.id,
            source: session.source,
            title: session.title,
            project: projectName(session.root),
          }))}
          projeler={controller.recentProjects.map((project) => ({
            name: project.name,
            pinned: false,
            root: project.root,
            updated_at: project.updatedAt,
          }))}
        />
      }
      sidebarCollapsed={layout.sidebarCollapsed}
    />
  );
}

export function CoreConnectedApp({ transport }: { transport?: SessionTransport } = {}) {
  return <SessionUygulama transport={transport} />;
}

interface AppProps {
  runtimeTransport?: RuntimeTransport;
  sessionTransport?: SessionTransport;
}

export default function App({ runtimeTransport, sessionTransport }: AppProps = {}) {
  const runtime = useRuntime(runtimeTransport);
  const [onboardingComplete, setOnboardingComplete] = useState(
    () => localStorage.getItem("fusion.onboarding.completed.v1") === "true",
  );
  if (runtime.state !== "hazir") {
    return <RuntimeSetup {...runtime} onRepair={runtime.repair} />;
  }
  return (
    <SessionUygulama
      onboarding={!onboardingComplete}
      onOnboardingComplete={() => {
        localStorage.setItem("fusion.onboarding.completed.v1", "true");
        setOnboardingComplete(true);
      }}
      runtimeVersion={runtime.version}
      transport={sessionTransport}
    />
  );
}

import { useEffect, useState } from "react";
import { Approval } from "./dialogs/Approval";
import { HistoryPicker } from "./dialogs/HistoryPicker";
import { useHistory } from "./history/useHistory";
import { ProtocolClient } from "./protocol/client";
import { olayMetni } from "./protocol/olayMetni";
import type { Soru } from "./protocol/types";
import { useRuntime } from "./runtime/useRuntime";
import type { RuntimeTransport } from "./runtime/types";
import { useSessions } from "./sessions/useSessions";
import type { SessionTransport } from "./sessions/types";
import { AppHeader } from "./screens/AppHeader";
import { Composer } from "./screens/Composer";
import { Conversation, type Mesaj } from "./screens/Conversation";
import { EmptyState } from "./screens/EmptyState";
import { Inspector } from "./screens/Inspector";
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

export function SessionUygulama({ transport }: { transport?: SessionTransport }) {
  const controller = useSessions(transport);
  const layout = useLayout();
  const { changeTheme, themePreference } = useAppTheme();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [historyOpen, setHistoryOpen] = useState(false);
  const active = controller.activeSession;
  const history = useHistory(active?.client ?? null);

  if (controller.state.connectionError) {
    return <div className="app-status-screen">Hata: {controller.state.connectionError}</div>;
  }
  if (!active) return <div className="app-status-screen">Bağlanıyor…</div>;

  const draft = drafts[active.id] ?? "";
  const setDraft = (value: string) => setDrafts((current) => ({ ...current, [active.id]: value }));
  const send = (task: string) => {
    controller.send(active.id, task);
    setDraft("");
  };
  const content = active.messages.length > 0 ? (
    <Conversation mesajlar={active.messages} />
  ) : (
    <EmptyState onSelectPrompt={setDraft} />
  );
  const status = active.status === "crashed"
    ? "Bağlantı kesildi"
    : active.running
      ? "Çalışıyor"
      : "Hazır";

  return (
    <Shell
      composer={
        <Composer
          onSend={send}
          onStop={() => controller.stop(active.id)}
          onValueChange={setDraft}
          running={active.running}
          value={draft}
        />
      }
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
          title={active.title}
        />
      }
      inspector={<Inspector />}
      inspectorOpen={layout.inspectorOpen}
      onInspectorClose={layout.closeInspector}
      sidebar={
        <Sidebar
          collapsed={layout.sidebarCollapsed}
          availableSources={history.sources.map((source) => source.ad)}
          etkin={active.id}
          onNavigate={(destination) => {
            if (destination.startsWith("resume:")) {
              const source = destination.slice("resume:".length) as "claude" | "codex" | "hermes";
              setHistoryOpen(true);
              void history.openSource(source);
            } else if (destination.startsWith("project:")) {
              void controller.create({ root: destination.slice("project:".length) });
            }
          }}
          onSec={controller.select}
          onYeni={() => void controller.create()}
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
  if (runtime.state !== "hazir") {
    return <RuntimeSetup {...runtime} onRepair={runtime.repair} />;
  }
  return <CoreConnectedApp transport={sessionTransport} />;
}

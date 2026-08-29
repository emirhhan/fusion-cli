import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { Approval } from "./dialogs/Approval";
import { ProtocolClient } from "./protocol/client";
import { olayMetni } from "./protocol/olayMetni";
import type { Soru } from "./protocol/types";
import { useRuntime } from "./runtime/useRuntime";
import type { RuntimeTransport } from "./runtime/types";
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

const CORE_CLOSED = "Çekirdek beklenmedik şekilde kapandı. Uygulamayı yeniden başlatmayı deneyin.";

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

export function Uygulama({ istemci }: { istemci: ProtocolClient }) {
  const conversation = useConversation(istemci);
  const layout = useLayout();
  const [draft, setDraft] = useState("");
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

export function CoreConnectedApp() {
  const [client, setClient] = useState<ProtocolClient | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let lineUnlisten: UnlistenFn | null = null;
    let closeUnlisten: UnlistenFn | null = null;
    let active = true;
    let current: ProtocolClient | null = null;
    void invoke("cekirdek_baslat")
      .then(async () => {
        current = new ProtocolClient(
          (line) => void invoke("cekirdege_yaz", { satir: line }),
          (handler) => {
            void listen<string>("cekirdek-satir", (event) => handler(event.payload)).then(
              (unlisten) => {
                lineUnlisten = unlisten;
              },
            );
          },
        );
        closeUnlisten = await listen("cekirdek-kapandi", () => {
          current?.close(CORE_CLOSED);
          setError(CORE_CLOSED);
        });
        if (active) setClient(current);
      })
      .catch((reason) => setError(String(reason)));
    return () => {
      active = false;
      lineUnlisten?.();
      closeUnlisten?.();
      current?.close();
    };
  }, []);
  if (error) return <div className="app-status-screen">Hata: {error}</div>;
  if (!client) return <div className="app-status-screen">Bağlanıyor…</div>;
  return <Uygulama istemci={client} />;
}

export default function App({ runtimeTransport }: { runtimeTransport?: RuntimeTransport } = {}) {
  const runtime = useRuntime(runtimeTransport);
  if (runtime.state !== "hazir") {
    return <RuntimeSetup {...runtime} onRepair={runtime.repair} />;
  }
  return <CoreConnectedApp />;
}

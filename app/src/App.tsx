import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { Approval } from "./dialogs/Approval";
import { ProtocolClient } from "./protocol/client";
import { olayMetni } from "./protocol/olayMetni";
import type { Soru } from "./protocol/types";
import { useRuntime } from "./runtime/useRuntime";
import type { RuntimeTransport } from "./runtime/types";
import { Conversation, type Mesaj } from "./screens/Conversation";
import { EmptyState } from "./screens/EmptyState";
import { RuntimeSetup } from "./screens/RuntimeSetup";
import { Shell } from "./screens/Shell";
import { Sidebar } from "./screens/Sidebar";

const CORE_CLOSED = "Çekirdek beklenmedik şekilde kapandı. Uygulamayı yeniden başlatmayı deneyin.";

function Composer({ onSend }: { onSend: (task: string) => void }) {
  const [draft, setDraft] = useState("");
  const send = () => {
    const task = draft.trim();
    if (!task) return;
    setDraft("");
    onSend(task);
  };
  return (
    <div style={{ margin: "0 auto", maxWidth: "var(--icerik-en-fazla)", padding: "12px 16px 20px", width: "100%" }}>
      <div style={{ border: "1px solid var(--kenarlik)", borderRadius: "var(--yaricap)", display: "flex", gap: 8, padding: 8 }}>
        <input aria-label="Mesaj" onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => event.key === "Enter" && send()} placeholder="Fusion'a bir görev ver" style={{ border: "none", flex: 1, font: "inherit", outline: "none", padding: "8px" }} value={draft} />
        <button onClick={send} style={{ background: "var(--birincil-buton)", border: "none", borderRadius: 8, color: "var(--ters-metin)", cursor: "pointer", padding: "8px 14px" }} type="button">Gönder</button>
      </div>
    </div>
  );
}

function useConversation(client: ProtocolClient) {
  const [messages, setMessages] = useState<Mesaj[]>([]);
  const [question, setQuestion] = useState<{ id: string; data: Soru } | null>(null);
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
    setMessages((current) => [...current, { rol: "kullanici", metin: task }]);
    void client.request("tur.calistir", { gorev: task }).then((result) => {
      const text = typeof result.metin === "string" ? result.metin : "";
      if (text) setMessages((current) => [...current, { rol: "asistan", metin: text }]);
    }).catch((error) => setMessages((current) => [...current, { rol: "asistan", metin: `Hata: ${String(error)}` }]));
  };
  const answer = (data: Record<string, unknown>) => {
    if (question) client.reply(question.id, data);
    setQuestion(null);
  };
  return { answer, messages, question, send, clear: () => setMessages([]) };
}

export function Uygulama({ istemci }: { istemci: ProtocolClient }) {
  const conversation = useConversation(istemci);
  const content = conversation.messages.length > 0
    ? <Conversation mesajlar={conversation.messages} />
    : <EmptyState />;
  return (
    <Shell
      kenar={<Sidebar etkin={null} onSec={() => undefined} onYeni={conversation.clear} oturumlar={[]} />}
      icerik={
        <>
          {content}
          {conversation.question && <Approval onCevap={conversation.answer} soru={conversation.question.data} />}
          <Composer onSend={conversation.send} />
        </>
      }
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
    void invoke("cekirdek_baslat").then(async () => {
      current = new ProtocolClient((line) => void invoke("cekirdege_yaz", { satir: line }), (handler) => {
        void listen<string>("cekirdek-satir", (event) => handler(event.payload)).then((unlisten) => { lineUnlisten = unlisten; });
      });
      closeUnlisten = await listen("cekirdek-kapandi", () => { current?.close(CORE_CLOSED); setError(CORE_CLOSED); });
      if (active) setClient(current);
    }).catch((reason) => setError(String(reason)));
    return () => { active = false; lineUnlisten?.(); closeUnlisten?.(); current?.close(); };
  }, []);
  if (error) return <div style={{ padding: 24 }}>Hata: {error}</div>;
  if (!client) return <div style={{ padding: 24 }}>Bağlanıyor…</div>;
  return <Uygulama istemci={client} />;
}

export default function App({ runtimeTransport }: { runtimeTransport?: RuntimeTransport } = {}) {
  const runtime = useRuntime(runtimeTransport);
  if (runtime.state !== "hazir") {
    return <RuntimeSetup {...runtime} onRepair={runtime.repair} />;
  }
  return <CoreConnectedApp />;
}

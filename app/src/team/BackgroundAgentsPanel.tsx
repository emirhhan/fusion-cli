import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { osBildirimiGonder } from "../notifications/osNotice";
import { BackgroundPendingInput, parsePendingRequest, type PendingRequest } from "./BackgroundPendingInput";
import "./BackgroundAgentsPanel.css";

/** Panelin konuştuğu uç (`ProtocolClient` ile uyumlu, testte sahte verilir). */
export interface BackgroundClient {
  request(name: string, data: Record<string, unknown>): Promise<Record<string, unknown>>;
}

/** `arkaplan.durum` görev satırı (çekirdekte `BackgroundTask.to_dict` + etiket). */
export interface BackgroundTaskRow {
  id: string;
  name: string;
  status: string;
  label: string;
  active: boolean;
  detail: string;
  question: string;
  /** Yalnız girdi bekleyen görevde: onay mı serbest metinli soru mu, ayrıntısıyla. */
  pending: PendingRequest | null;
}

export interface PeerRow { id: string; ad: string; tur: string; kok: string }
export interface HeldMessage { no: number; kimden: string; metin: string }

export const BACKGROUND_POLL_MS = 3000;

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function parseTask(value: unknown): BackgroundTaskRow | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  if (typeof raw.id !== "string" || typeof raw.name !== "string") return null;
  return {
    id: raw.id,
    name: raw.name,
    status: text(raw.status),
    label: text(raw.durum_etiketi) || text(raw.status),
    active: raw.etkin === true,
    detail: text(raw.question) || text(raw.summary) || text(raw.note) || text(raw.prompt),
    question: text(raw.question),
    pending: raw.status === "girdi_bekliyor" ? parsePendingRequest(raw.soru, text(raw.question)) : null,
  };
}

function parsePeer(value: unknown): PeerRow | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  return typeof raw.id === "string" && typeof raw.ad === "string"
    ? { id: raw.id, ad: raw.ad, tur: text(raw.tur), kok: text(raw.kok) }
    : null;
}

function parseHeld(value: unknown): HeldMessage | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  return typeof raw.no === "number" ? { no: raw.no, kimden: text(raw.kimden), metin: text(raw.metin) } : null;
}

function list<T>(value: unknown, parse: (item: unknown) => T | null): T[] {
  return Array.isArray(value) ? value.map(parse).filter((item): item is T => item !== null) : [];
}

interface PanelProps {
  client: BackgroundClient | null;
  /** Bekletilen gelen mesajı tura almak `/list-agents al <no>` komutuyla olur (etiketli girdi). */
  onCommand?: (line: string) => void;
  pollMs?: number;
  notify?: (title: string, body: string) => void;
}

/**
 * Arka plan ajan görevleri (P-048) ve açık Fusion oturumları (P-060).
 *
 * Terminaldeki `/tasks`, `/list-agents` ve `fusion agents` karşılığı: görev başlat, izle, girdi
 * bekleyeni onayla, devam mesajı gönder, durdur; başka oturumdan gelen mesajı tura al ya da sil.
 * Bitiş/girdi bildirimleri işletim sistemi bildirimine de düşer.
 */
export function BackgroundAgentsPanel({ client, onCommand, pollMs = BACKGROUND_POLL_MS, notify }: PanelProps) {
  const [tasks, setTasks] = useState<BackgroundTaskRow[]>([]);
  const [peers, setPeers] = useState<PeerRow[]>([]);
  const [held, setHeld] = useState<HeldMessage[]>([]);
  const [enabled, setEnabled] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [replies, setReplies] = useState<Record<string, string>>({});
  const [detail, setDetail] = useState<{ id: string; body: string } | null>(null);
  const [peerTarget, setPeerTarget] = useState("");
  const [peerText, setPeerText] = useState("");
  const notifyRef = useRef(notify ?? ((title: string, body: string) => void osBildirimiGonder(title, body)));

  const refresh = useCallback(async () => {
    if (!client) return;
    try {
      const result = await client.request("arkaplan.durum", {});
      if (result.ok !== true) throw new Error(text(result.metin) || "Arka plan görevleri okunamadı.");
      setEnabled(result.acik !== false);
      setTasks(list(result.gorevler, parseTask));
      setPeers(list(result.oturumlar, parsePeer));
      setHeld(list(result.bekleyen, parseHeld));
      for (const notice of list(result.bildirimler, (item) => (typeof item === "string" ? item : null))) {
        notifyRef.current("Fusion arka plan", notice);
      }
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Arka plan görevleri okunamadı.");
    }
  }, [client]);

  useEffect(() => {
    if (!client) return;
    void refresh();
    const timer = window.setInterval(() => void refresh(), pollMs);
    return () => window.clearInterval(timer);
  }, [client, pollMs, refresh]);

  const call = async (name: string, data: Record<string, unknown>): Promise<Record<string, unknown> | null> => {
    if (!client) return null;
    let failure: string | null = null;
    let result: Record<string, unknown> | null = null;
    try {
      result = await client.request(name, data);
      if (result.ok !== true) failure = text(result.metin) || "İşlem yapılamadı.";
    } catch {
      failure = "İşlem yapılamadı.";
    }
    await refresh();
    if (failure) setError(failure);
    return failure ? null : result;
  };

  const start = async (event: FormEvent) => {
    event.preventDefault();
    const task = draft.trim();
    if (!task) return;
    if (await call("arkaplan.baslat", { gorev: task })) setDraft("");
  };

  const reply = async (id: string) => {
    const message = (replies[id] ?? "").trim();
    if (!message) return;
    if (await call("arkaplan.mesaj", { id, metin: message })) setReplies((current) => ({ ...current, [id]: "" }));
  };

  const show = async (id: string) => {
    if (detail?.id === id) {
      setDetail(null);
      return;
    }
    const result = await call("arkaplan.goster", { id });
    if (result) setDetail({ id, body: [text(result.sonuc), text(result.olaylar)].filter(Boolean).join("\n\n") || "Henüz sonuç yok." });
  };

  const sendToPeer = async (event: FormEvent) => {
    event.preventDefault();
    if (!peerTarget || !peerText.trim()) return;
    if (await call("esler.gonder", { hedef: peerTarget, metin: peerText.trim() })) setPeerText("");
  };

  if (!client) return null;
  return (
    <section aria-labelledby="bg-agents-heading" className="bg-agents">
      <h3 id="bg-agents-heading">Arka plan görevleri</h3>
      {error && <p className="bg-agents__error" role="alert">{error}</p>}
      {!enabled ? (
        <p className="bg-agents__hint">Arka plan görevleri kapalı (runtime.background_agents).</p>
      ) : (
        <form className="bg-agents__start" onSubmit={(event) => void start(event)}>
          <label htmlFor="bg-agents-draft">Arka planda çalışacak görev</label>
          <textarea id="bg-agents-draft" onChange={(event) => setDraft(event.target.value)} placeholder="ör. Tüm testleri koştur ve kırılanları düzelt" rows={2} value={draft} />
          <button disabled={!draft.trim()} type="submit">Arka planda başlat</button>
        </form>
      )}
      {tasks.length === 0 ? (
        <p className="bg-agents__hint">Görev yok. Sohbette <code>/bg &lt;görev&gt;</code> yaz ya da yukarıdan başlat.</p>
      ) : (
        <ul aria-label="Arka plan görevleri" className="bg-agents__list">
          {tasks.map((task) => (
            <li className="bg-agents__item" data-status={task.status} key={task.id}>
              <div className="bg-agents__row">
                <strong>{task.name}</strong>
                <span className="bg-agents__chip">{task.label}</span>
              </div>
              <p className="bg-agents__detail" title={task.detail}>{task.detail}</p>
              {task.pending && (
                <BackgroundPendingInput
                  onAnswer={async (cevap) => (await call("arkaplan.cevapla", { id: task.id, cevap })) !== null}
                  request={task.pending}
                  taskName={task.name}
                />
              )}
              <div className="bg-agents__actions">
                <button aria-expanded={detail?.id === task.id} onClick={() => void show(task.id)} type="button">Ayrıntı</button>
                {task.active ? (
                  <button aria-label={`${task.name} görevini durdur`} onClick={() => void call("arkaplan.durdur", { id: task.id })} type="button">Durdur</button>
                ) : (
                  <button aria-label={`${task.name} kaydını sil`} onClick={() => void call("arkaplan.sil", { id: task.id })} type="button">Sil</button>
                )}
              </div>
              <form className="bg-agents__reply" onSubmit={(event) => { event.preventDefault(); void reply(task.id); }}>
                <input
                  aria-label={`${task.name} görevine mesaj`}
                  onChange={(event) => setReplies((current) => ({ ...current, [task.id]: event.target.value }))}
                  placeholder={task.active ? "Devam mesajı (sıradaki turda)" : "Devam mesajı (görevi sürdürür)"}
                  value={replies[task.id] ?? ""}
                />
                <button disabled={!(replies[task.id] ?? "").trim()} type="submit">Gönder</button>
              </form>
              {detail?.id === task.id && <pre className="bg-agents__output">{detail.body}</pre>}
            </li>
          ))}
        </ul>
      )}
      <h3>Açık oturumlar</h3>
      {held.length > 0 && (
        <ul aria-label="Bekletilen gelen mesajlar" className="bg-agents__list">
          {held.map((message) => (
            <li className="bg-agents__item" data-status="gelen" key={message.no}>
              <div className="bg-agents__row"><strong>{message.kimden}</strong><span className="bg-agents__chip">gelen mesaj</span></div>
              <p className="bg-agents__detail">{message.metin}</p>
              <div className="bg-agents__actions">
                <button disabled={!onCommand} onClick={() => onCommand?.(`/list-agents al ${message.no}`)} title="Etiketli (güvenilmez) girdi olarak tura alınır" type="button">Tura al</button>
                <button onClick={() => void call("esler.reddet", { no: message.no })} type="button">Sil</button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {peers.length === 0 ? (
        <p className="bg-agents__hint">Başka açık Fusion oturumu yok.</p>
      ) : (
        <form className="bg-agents__reply" onSubmit={(event) => void sendToPeer(event)}>
          <select aria-label="Hedef oturum" onChange={(event) => setPeerTarget(event.target.value)} value={peerTarget}>
            <option value="">Oturum seç</option>
            {peers.map((peer) => <option key={peer.id} value={peer.id}>{peer.ad} · {peer.tur}</option>)}
          </select>
          <input aria-label="Oturuma mesaj" onChange={(event) => setPeerText(event.target.value)} placeholder="Mesaj" value={peerText} />
          <button disabled={!peerTarget || !peerText.trim()} type="submit">Gönder</button>
        </form>
      )}
    </section>
  );
}

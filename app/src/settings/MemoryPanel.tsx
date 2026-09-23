import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";

interface SavedMemory { id: string; metin: string }

export function MemoryPanel({ client }: { client: ProtocolClient }) {
  const [items, setItems] = useState<SavedMemory[]>([]);
  const [enabled, setEnabled] = useState(true);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const result = await client.request("bellek.listele", {});
      if (result.ok !== true) throw new Error(String(result.metin ?? "Hafıza okunamadı."));
      setItems(Array.isArray(result.anilar) ? result.anilar as SavedMemory[] : []);
      setEnabled(result.etkin !== false);
      setError(null);
    } catch {
      setError("Hafıza okunamadı. Yeniden dene.");
    }
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  const add = async () => {
    if (!draft.trim()) return;
    setBusy(true);
    try {
      const result = await client.request("bellek.ekle", { metin: draft.trim() });
      if (result.ok !== true) throw new Error(String(result.metin ?? "Anı kaydedilemedi."));
      setDraft("");
      await load();
    } catch (reason) {
      setError(String(reason));
    } finally { setBusy(false); }
  };
  const remove = async (id: string) => {
    setBusy(true);
    try {
      const result = await client.request("bellek.sil", { id });
      if (result.ok !== true) throw new Error(String(result.metin ?? "Anı kaldırılamadı."));
      await load();
    } catch (reason) {
      setError(String(reason));
    } finally { setBusy(false); }
  };
  const toggle = async (next: boolean) => {
    setBusy(true);
    try {
      const result = await client.request("bellek.etkinlestir", { etkin: next });
      if (result.ok !== true) throw new Error(String(result.metin ?? "Tercih kaydedilemedi."));
      setEnabled(next);
      setError(null);
    } catch (reason) {
      setError(String(reason));
    } finally { setBusy(false); }
  };

  return <article className="settings__card">
    <h3>Kaydedilmiş anılar</h3>
    <p className="settings__hint">Anılar bu bilgisayarda saklanır. Açıkken yeni görevlerin bağlamına eklenir ve seçilen model sağlayıcısına gönderilir.</p>
    <label className="settings__row settings__row--check">
      <input aria-label="Hafızayı kullan" checked={enabled} disabled={busy} onChange={(event) => void toggle(event.target.checked)} type="checkbox" />
      <span>Hafızayı kullan</span>
    </label>
    {error && <p className="settings__inline-error" role="alert">{error}</p>}
    <div className="settings__memory-add">
      <input aria-label="Yeni anı" maxLength={500} onChange={(event) => setDraft(event.target.value)} placeholder="Örneğin: Yanıtları Türkçe ve kısa yaz" value={draft} />
      <button disabled={busy || !draft.trim()} onClick={() => void add()} type="button">Ekle</button>
    </div>
    {items.length === 0 ? <p className="settings__hint">Henüz kayıtlı anı yok.</p> :
      <ul className="settings__memory-list">
        {items.map((item) => <li key={item.id}><span>{item.metin}</span><button aria-label={`Anıyı kaldır: ${item.metin}`} disabled={busy} onClick={() => void remove(item.id)} type="button">Kaldır</button></li>)}
      </ul>}
  </article>;
}

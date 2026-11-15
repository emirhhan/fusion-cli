import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";

interface Shortcut {
  ad: string;
  metin: string;
}

interface MonitorReply {
  ok: boolean;
  acik?: boolean;
  metin?: string;
}

interface ShortcutsReply {
  ok: boolean;
  kisayollar?: Shortcut[];
  metin?: string;
}

/** Kısayol adı: boşluksuz, en çok 40 karakter (eklentideki kuralla aynı). */
const SHORTCUT_NAME = /^[\p{L}\p{N}_-]{1,40}$/u;

function failureText(reply: { ok: boolean; metin?: string }, fallback: string): string {
  return reply.metin || fallback;
}

/**
 * Eklentinin paneldeki iki ayarı masaüstünden: konsol/ağ izleme anahtarı ve kısayollar.
 * Eklenti bağlıyken gösterilir; değerler köprü üzerinden eklentinin kendi deposundan okunur,
 * panel ve masaüstü aynı listeyi görür.
 */
export function ChromeExtensionSettings({ client }: { client: ProtocolClient }) {
  const [monitor, setMonitor] = useState(true);
  const [shortcuts, setShortcuts] = useState<Shortcut[]>([]);
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [izleme, liste] = await Promise.all([
      client.request("chrome.izleme", {}) as unknown as Promise<MonitorReply>,
      client.request("chrome.kisayollar", {}) as unknown as Promise<ShortcutsReply>,
    ]);
    if (!izleme.ok) throw new Error(failureText(izleme, "İzleme ayarı okunamadı."));
    if (!liste.ok) throw new Error(failureText(liste, "Kısayollar okunamadı."));
    setMonitor(izleme.acik !== false);
    setShortcuts(liste.kisayollar ?? []);
  }, [client]);

  useEffect(() => {
    let mounted = true;
    load().catch((cause) => {
      if (mounted) setError(cause instanceof Error ? cause.message : "Eklenti ayarları okunamadı.");
    });
    return () => { mounted = false; };
  }, [load]);

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Eklenti ayarı değiştirilemedi.");
    } finally {
      setBusy(false);
    }
  };

  const toggleMonitor = (acik: boolean) => run(async () => {
    const reply = await client.request("chrome.izleme", { acik }) as unknown as MonitorReply;
    if (!reply.ok) throw new Error(failureText(reply, "İzleme ayarı değiştirilemedi."));
    setMonitor(reply.acik !== false);
  });

  const applyList = (reply: ShortcutsReply, fallback: string) => {
    if (!reply.ok) throw new Error(failureText(reply, fallback));
    setShortcuts(reply.kisayollar ?? []);
  };

  const save = () => {
    const ad = name.trim().replace(/^\//, "");
    const metin = text.trim();
    if (!SHORTCUT_NAME.test(ad)) {
      setError("Kısayol adı boşluksuz, en çok 40 karakter olmalı (ör. ozet).");
      return;
    }
    if (!metin) {
      setError("Kısayolun görev metnini yaz.");
      return;
    }
    void run(async () => {
      const reply = await client.request("chrome.kisayol_kaydet", { ad, metin }) as unknown as ShortcutsReply;
      applyList(reply, "Kısayol kaydedilemedi.");
      setName("");
      setText("");
    });
  };

  const remove = (ad: string) => run(async () => {
    const reply = await client.request("chrome.kisayol_sil", { ad }) as unknown as ShortcutsReply;
    applyList(reply, "Kısayol silinemedi.");
  });

  return (
    <section className="settings__subcard" aria-labelledby="chrome-ext-settings">
      <h4 id="chrome-ext-settings">Eklenti ayarları</h4>
      <label className="settings__row settings__row--check">
        <input
          aria-label="Konsol ve ağ isteklerini izle"
          checked={monitor}
          disabled={busy}
          onChange={(event) => void toggleMonitor(event.target.checked)}
          type="checkbox"
        />
        <span>Konsol ve ağ isteklerini izle</span>
      </label>
      <p className="settings__hint">Yalnız tek tek izin verdiğiniz sitelerde, sayfanın içinde tutulur ve Fusion sorduğunda okunur. Başlıklar (çerez, yetki) kaydedilmez.</p>

      <h4>Kısayollar</h4>
      <p className="settings__hint">Sık verdiğiniz görevi adla kaydedin; eklenti panelinde <code>/ad</code> ile çağrılır, ajan <code>chrome_action shortcut</code> ile alır.</p>
      {shortcuts.length === 0 ? (
        <p className="settings__hint">Henüz kısayol yok.</p>
      ) : (
        <ul className="settings__list" aria-label="Kayıtlı kısayollar">
          {shortcuts.map((shortcut) => (
            <li key={shortcut.ad}>
              <strong>/{shortcut.ad}</strong>
              <code title={shortcut.metin}>{shortcut.metin}</code>
              <button aria-label={`/${shortcut.ad} kısayolunu kaldır`} disabled={busy} onClick={() => void remove(shortcut.ad)} type="button">Kaldır</button>
            </li>
          ))}
        </ul>
      )}
      <div className="settings__form">
        <label htmlFor="chrome-shortcut-name">Kısayol adı</label>
        <input id="chrome-shortcut-name" maxLength={41} onChange={(event) => setName(event.target.value)} placeholder="ör. ozet" value={name} />
        <label htmlFor="chrome-shortcut-text">Görev</label>
        <textarea id="chrome-shortcut-text" maxLength={2000} onChange={(event) => setText(event.target.value)} placeholder="Bu sayfayı kısaca özetle." rows={2} value={text} />
      </div>
      <div className="settings__actions">
        <button disabled={busy} onClick={save} type="button">Kısayolu kaydet</button>
      </div>
      {error && <p className="settings__inline-error" role="alert">{error}</p>}
    </section>
  );
}

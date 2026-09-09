import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";

type Transport = "stdio" | "streamable_http";

interface ConnectorRow {
  ad: string;
  argumanlar: string[];
  arac_sayisi?: number;
  client_id?: string;
  durum?: string;
  kapsamlar?: string[];
  komut: string;
  mesaj?: string | null;
  tasima?: Transport;
  url?: string;
}

interface ConnectorResult {
  arac_sayisi?: number;
  durum?: string;
  mesaj?: string | null;
  metin?: string;
  ok?: boolean;
}

const EMPTY = {
  ad: "",
  client_id: "",
  kapsamlar: "",
  komut: "",
  tasima: "stdio" as Transport,
  url: "",
};

const LABELS: Record<string, string> = {
  bagli: "Bağlı",
  giris_bekleniyor: "Giriş bekleniyor",
  hata: "Bağlantı hatası",
  kapali: "Bağlı değil",
  zaman_asimi: "Zaman aşımı",
  yapilandirildi: "Test edilmedi",
};

export function Connectors({ client }: { client: ProtocolClient }) {
  const [rows, setRows] = useState<ConnectorRow[]>([]);
  const [draft, setDraft] = useState(EMPTY);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = (await client.request("baglanti.listele", {})) as {
      ok?: boolean;
      sunucular?: ConnectorRow[];
    };
    if (result?.ok) setRows(result.sunucular ?? []);
  }, [client]);

  useEffect(() => {
    void load().catch(() => setNotice("Bağlantılar okunamadı."));
  }, [load]);

  useEffect(() => {
    if (!rows.some((row) => row.durum === "giris_bekleniyor")) return;
    const timer = window.setInterval(() => void load(), 1200);
    return () => window.clearInterval(timer);
  }, [load, rows]);

  const run = async (name: string, data: Record<string, unknown>, key = name) => {
    setBusy(key);
    try {
      const result = (await client.request(name, data)) as ConnectorResult;
      setNotice(result?.metin ?? result?.mesaj ?? null);
      if (result?.ok || result?.durum) {
        if (name === "baglanti.ekle") setDraft(EMPTY);
        await load();
      }
    } catch {
      setNotice("Bağlantı işlemi tamamlanamadı.");
    } finally {
      setBusy(null);
    }
  };

  const canAdd = Boolean(
    draft.ad.trim() && (draft.tasima === "stdio" ? draft.komut.trim() : draft.url.trim()),
  );
  const addPayload =
    draft.tasima === "stdio"
      ? { ad: draft.ad, komut: draft.komut }
      : {
          ad: draft.ad,
          tasima: draft.tasima,
          url: draft.url,
          kapsamlar: draft.kapsamlar,
          client_id: draft.client_id,
        };

  return (
    <article className="settings__card settings__card--wide settings__connectors">
      <div className="settings__card-head">
        <div>
          <h3>MCP bağlantıları</h3>
          <p className="settings__hint">Yerel araçları veya OAuth destekli uzak MCP servislerini bağlayın.</p>
        </div>
        <span className="settings__badge">{rows.filter((row) => row.durum === "bagli").length} etkin</span>
      </div>

      {rows.length > 0 ? (
        <ul className="settings__list settings__connector-list">
          {rows.map((row) => {
            const remote = row.tasima === "streamable_http";
            const pending = row.durum === "giris_bekleniyor";
            return (
              <li className="settings__connector" data-state={row.durum} key={row.ad}>
                <div className="settings__connector-main">
                  <strong>{row.ad}</strong>
                  <span className="settings__connector-state">{LABELS[row.durum ?? "yapilandirildi"]}</span>
                  {row.durum === "bagli" && <span>{row.arac_sayisi ?? 0} araç</span>}
                </div>
                <code>{remote ? row.url : [row.komut, ...row.argumanlar].join(" ")}</code>
                {row.mesaj && <p className="settings__connector-error" role="status">{row.mesaj}</p>}
                <div className="settings__connector-actions">
                  {remote && row.durum !== "bagli" && (
                    <button
                      aria-label={`${row.ad} bağlantısında giriş yap`}
                      disabled={busy !== null || pending}
                      onClick={() => void run("baglanti.giris", { ad: row.ad }, `login:${row.ad}`)}
                      type="button"
                    >
                      {pending ? "Giriş bekleniyor…" : "Giriş yap"}
                    </button>
                  )}
                  <button
                    aria-label={`${row.ad} bağlantısını test et`}
                    disabled={busy !== null || pending}
                    onClick={() => void run("baglanti.dogrula", { ad: row.ad }, `test:${row.ad}`)}
                    type="button"
                  >
                    Test et
                  </button>
                  {remote && row.durum === "bagli" && (
                    <button
                      aria-label={`${row.ad} bağlantısından çıkış yap`}
                      disabled={busy !== null}
                      onClick={() => void run("baglanti.cikis", { ad: row.ad }, `logout:${row.ad}`)}
                      type="button"
                    >
                      Çıkış yap
                    </button>
                  )}
                  <button
                    aria-label={`${row.ad} bağlantısını kaldır`}
                    disabled={busy !== null}
                    onClick={() => void run("baglanti.sil", { ad: row.ad }, `remove:${row.ad}`)}
                    type="button"
                  >
                    Kaldır
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="settings__hint">Henüz bağlantı yok.</p>
      )}

      <div className="settings__form settings__connector-form">
        <label htmlFor="baglanti-tur">Bağlantı türü</label>
        <select
          id="baglanti-tur"
          onChange={(event) => setDraft((current) => ({ ...current, tasima: event.target.value as Transport }))}
          value={draft.tasima}
        >
          <option value="stdio">Yerel komut</option>
          <option value="streamable_http">Uzak MCP · OAuth</option>
        </select>
        <label htmlFor="baglanti-ad">Ad</label>
        <input
          id="baglanti-ad"
          onChange={(event) => setDraft((current) => ({ ...current, ad: event.target.value }))}
          placeholder={draft.tasima === "stdio" ? "godot" : "meta"}
          value={draft.ad}
        />
        {draft.tasima === "stdio" ? (
          <>
            <label htmlFor="baglanti-komut">Komut</label>
            <input
              id="baglanti-komut"
              onChange={(event) => setDraft((current) => ({ ...current, komut: event.target.value }))}
              placeholder="npx -y godot-mcp"
              value={draft.komut}
            />
          </>
        ) : (
          <>
            <label htmlFor="baglanti-url">MCP adresi</label>
            <input
              id="baglanti-url"
              onChange={(event) => setDraft((current) => ({ ...current, url: event.target.value }))}
              placeholder="https://mcp.example.com/mcp"
              type="url"
              value={draft.url}
            />
            <label htmlFor="baglanti-kapsam">OAuth kapsamları</label>
            <input
              id="baglanti-kapsam"
              onChange={(event) => setDraft((current) => ({ ...current, kapsamlar: event.target.value }))}
              placeholder="ads_read business_management"
              value={draft.kapsamlar}
            />
            <label htmlFor="baglanti-client">Client ID</label>
            <input
              id="baglanti-client"
              onChange={(event) => setDraft((current) => ({ ...current, client_id: event.target.value }))}
              placeholder="Dinamik kayıt varsa boş bırakın"
              value={draft.client_id}
            />
          </>
        )}
        <button
          disabled={busy !== null || !canAdd}
          onClick={() => void run("baglanti.ekle", addPayload)}
          type="button"
        >
          Bağlantı ekle
        </button>
      </div>
      {notice && <p className="settings__hint" role="status">{notice}</p>}
    </article>
  );
}

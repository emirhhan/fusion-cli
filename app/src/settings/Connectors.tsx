import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";

/**
 * MCP bağlantıları.
 *
 * Sunucu eklemek için `config.yaml`'ı elle açmak gerekiyordu. Komut tek satır
 * yazılır ("npx -y mcp-github"); ayrıştırmayı çekirdek yapar, arayüz komutu
 * kendi başına parçalamaz.
 */
interface ConnectorRow {
  ad: string;
  argumanlar: string[];
  komut: string;
}

export function Connectors({ client }: { client: ProtocolClient }) {
  const [rows, setRows] = useState<ConnectorRow[]>([]);
  const [draft, setDraft] = useState({ ad: "", komut: "" });
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const veri = (await client.request("baglanti.listele", {})) as {
      ok?: boolean;
      sunucular?: ConnectorRow[];
    };
    if (veri?.ok) setRows(veri.sunucular ?? []);
  }, [client]);

  useEffect(() => {
    void load().catch(() => setNotice("Bağlantılar okunamadı."));
  }, [load]);

  const run = async (name: string, data: Record<string, unknown>) => {
    setBusy(true);
    const sonuc = (await client.request(name, data)) as { ok?: boolean; metin?: string };
    setBusy(false);
    setNotice(sonuc?.metin ?? null);
    if (sonuc?.ok) {
      setDraft({ ad: "", komut: "" });
      await load();
    }
  };

  const eklenebilir = Boolean(draft.ad.trim() && draft.komut.trim());

  return (
    <article className="settings__card settings__card--wide">
      <h3>MCP bağlantıları</h3>
      {rows.length > 0 ? (
        <ul className="settings__list">
          {rows.map((row) => (
            <li key={row.ad}>
              <strong>{row.ad}</strong>
              <code>{[row.komut, ...row.argumanlar].join(" ")}</code>
              <button
                aria-label={`${row.ad} bağlantısını kaldır`}
                disabled={busy}
                onClick={() => void run("baglanti.sil", { ad: row.ad })}
                type="button"
              >
                Kaldır
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="settings__hint">Henüz bağlantı yok.</p>
      )}

      <div className="settings__form">
        <label htmlFor="baglanti-ad">Ad</label>
        <input
          id="baglanti-ad"
          onChange={(event) => setDraft((current) => ({ ...current, ad: event.target.value }))}
          placeholder="github"
          value={draft.ad}
        />
        <label htmlFor="baglanti-komut">Komut</label>
        <input
          id="baglanti-komut"
          onChange={(event) => setDraft((current) => ({ ...current, komut: event.target.value }))}
          placeholder="npx -y mcp-github"
          value={draft.komut}
        />
        <button
          disabled={busy || !eklenebilir}
          onClick={() => void run("baglanti.ekle", draft)}
          type="button"
        >
          Bağlantı ekle
        </button>
      </div>
      {notice && <p className="settings__hint" role="status">{notice}</p>}
    </article>
  );
}

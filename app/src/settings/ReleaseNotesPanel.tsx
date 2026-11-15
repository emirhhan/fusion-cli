import { useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { errorMessage } from "../protocol/result";
import "./ImportPanel.css";

/** Sürüm notları (P-071): CHANGELOG bölümleri; terminalde `/release-notes`. Düz metin çizilir. */

interface Section { baslik: string; surum: string; tarih: string }

export function ReleaseNotesPanel({ client }: { client: ProtocolClient }) {
  const [installed, setInstalled] = useState("");
  const [sections, setSections] = useState<Section[]>([]);
  const [selected, setSelected] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void client.request("surum.notlari", { surum: selected }).then((payload) => {
      if (!active) return;
      if (payload.ok !== true) throw new Error(String(payload.metin ?? "Sürüm notları alınamadı."));
      setInstalled(String(payload.kurulu ?? ""));
      setText(String(payload.metin ?? ""));
      if (Array.isArray(payload.bolumler)) {
        setSections(payload.bolumler.filter((row): row is Record<string, unknown> => !!row && typeof row === "object").map((row) => ({ baslik: String(row.baslik ?? ""), surum: String(row.surum ?? ""), tarih: String(row.tarih ?? "") })));
      }
    }).catch((reason) => active && setError(errorMessage(reason)));
    return () => { active = false; };
  }, [client, selected]);

  return <article id="settings-release-notes" className="settings__card">
    <h3>Sürüm notları</h3>
    <p className="settings__hint">Kurulu sürüm: {installed || "…"}. Terminalde <code>/release-notes</code>.</p>
    {sections.length > 0 && (
      <label className="settings__row">
        <span>Bölüm</span>
        <select aria-label="Sürüm notu bölümü" onChange={(event) => setSelected(event.target.value)} value={selected}>
          <option value="">En yeni</option>
          {sections.filter((section) => section.surum).map((section) => <option key={section.baslik} value={section.surum}>{section.baslik}</option>)}
        </select>
      </label>
    )}
    {error && <p className="settings__inline-error" role="alert"><span>{error}</span></p>}
    {text && <pre aria-label="Sürüm notu metni" className="settings__pre">{text}</pre>}
  </article>;
}

import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { errorMessage, operationResult } from "../protocol/result";
import { Button } from "../ui/Button";
import { StatusRow } from "../ui/StatusRow";

export interface DevTool { id: string; ad: string; neden: string; kurulu: boolean; surum: string | null; indirme: string }

export function parseDevTools(payload: Record<string, unknown>): DevTool[] {
  const rows = Array.isArray(payload.araclar) ? payload.araclar : [];
  return rows.flatMap((raw) => {
    const row = raw as Record<string, unknown>;
    if (typeof row.id !== "string" || typeof row.ad !== "string") return [];
    return [{
      id: row.id, ad: row.ad, neden: String(row.neden ?? ""), kurulu: row.kurulu === true,
      surum: typeof row.surum === "string" ? row.surum : null, indirme: String(row.indirme ?? ""),
    }];
  });
}

/**
 * Proje yazacaklar için Node, Python, Git denetimi. Fusion bunları KURMAZ:
 * eksik olanın resmî indirme sayfasını gösterir, kurulumu kullanıcı yapar.
 */
export function DevToolsCheck({ client }: { client: ProtocolClient }) {
  const [tools, setTools] = useState<DevTool[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setError(null);
    try {
      const payload = await client.request("araclar.algila", {});
      const result = operationResult(payload, "Araçlar denetlenemedi.", true);
      if (!result.ok) { setError(result.message); return; }
      setTools(parseDevTools(payload));
    } catch (reason) { setError(errorMessage(reason)); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  const missing = tools?.filter((tool) => !tool.kurulu) ?? [];
  return (
    <section aria-labelledby="devtools-title" className="guide-devtools">
      <h3 id="devtools-title">Proje yazacaksan: gerekli araçlar</h3>
      <p className="guide-devtools__lead">
        Fusion proje yazarken bu araçlara ihtiyaç duyabilir. Eksik olanı kendi başına kurmaz; indirme sayfasını gösterir, kurulumu sen yaparsın.
      </p>
      {error && <p role="alert">{error} <Button onClick={() => void load()} variant="ghost">Yeniden dene</Button></p>}
      {!tools && !error && <p role="status">Araçlar denetleniyor…</p>}
      {tools && (
        <div className="guide-devtools__list">
          {tools.map((tool) => (
            <StatusRow
              action={!tool.kurulu && tool.indirme ? (
                <a className="guide-devtools__link" href={tool.indirme} rel="noreferrer noopener" target="_blank">İndirme sayfasını aç</a>
              ) : undefined}
              description={tool.kurulu ? (tool.surum ?? tool.neden) : tool.neden}
              key={tool.id}
              label={tool.ad}
              status={tool.kurulu ? "Kurulu" : "Eksik"}
              tone={tool.kurulu ? "success" : "warning"}
            />
          ))}
        </div>
      )}
      {tools && missing.length > 0 && <p className="guide-devtools__note">Kurulumdan sonra Fusion'ı kapatıp açman gerekebilir.</p>}
    </section>
  );
}

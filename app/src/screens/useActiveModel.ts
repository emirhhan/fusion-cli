import { useEffect, useState } from "react";
import type { CatalogClient } from "./useModelCatalog";

/** Composer model bilgisinin tek kontrol-durumu adaptörü. */
export function useActiveModel(client: CatalogClient | undefined, sessionId: string | undefined, revision: number) {
  const [snapshot, setSnapshot] = useState<{ client: CatalogClient; sessionId: string; model: string; label: string } | null>(null);
  useEffect(() => {
    if (!client || !sessionId) return;
    let alive = true;
    void client.request("kontrol.durum", {}).then((payload) => {
      if (!alive || payload.ok !== true) return;
      const state = payload.model as { agent?: unknown; agent_label?: unknown } | undefined;
      setSnapshot({ client, sessionId, model: typeof state?.agent === "string" ? state.agent : "",
        label: typeof state?.agent_label === "string" ? state.agent_label : "" });
    }).catch(() => undefined);
    return () => { alive = false; };
  }, [client, sessionId, revision]);
  const current = snapshot?.client === client && snapshot?.sessionId === sessionId ? snapshot : null;
  return { model: current?.model ?? "", label: current?.label ?? "" };
}

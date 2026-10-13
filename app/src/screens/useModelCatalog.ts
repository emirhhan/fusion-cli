import { useCallback, useEffect, useRef, useState } from "react";
import type { AsyncState } from "../protocol/asyncState";
import type { ModelOption } from "./ModelPicker";

export interface CatalogClient {
  request(name: string, data: Record<string, unknown>): Promise<Record<string, unknown>>;
}

/** Generation+request ownership keeps stale results away from new sessions. */
export function useModelCatalog(client: CatalogClient | undefined, sessionId: string | undefined, mode: string) {
  const [options, setOptions] = useState<ModelOption[]>([]);
  const [state, setState] = useState<AsyncState<ModelOption[]>>({ status: "ready", value: [] });
  const owner = useRef(0);
  const sequence = useRef(0);
  useEffect(() => {
    const generation = ++owner.current;
    setOptions([]);
    setState({ status: "ready", value: [] });
    return () => { owner.current = generation + 1; };
  }, [client, sessionId, mode]);
  const load = useCallback(async () => {
    if (!client) return;
    const generation = owner.current, intent = ++sequence.current;
    const current = () => owner.current === generation && sequence.current === intent;
    setState({ status: "loading" });
    try {
      const payload = await client.request("model.katalog", { kip: mode });
      if (!current()) return;
      if (payload.ok !== true) {
        setState({ status: "error", message: "Model listesi okunamadı. Yeniden dene." });
        return;
      }
      const rows = Array.isArray(payload.modeller) ? payload.modeller : [];
      const entries = rows.flatMap((raw): ModelOption[] => {
        if (!raw || typeof raw !== "object") return [];
        const row = raw as Record<string, unknown>;
        if (typeof row.model !== "string" || !row.model || typeof row.kaynak !== "string") return [];
        const capability = row.yetenek && typeof row.yetenek === "object" ? row.yetenek as Record<string, unknown> : {};
        return [{ deger: `/development uygula ${row.kaynak} ${row.model}`,
          modelId: row.model,
          etiket: typeof row.etiket === "string" ? row.etiket : row.model,
          aciklama: typeof row.aciklama === "string" ? row.aciklama : "",
          grup: typeof row.grup === "string" ? row.grup : "diger",
          toolSupport: typeof capability.tool_support === "string" ? capability.tool_support : "unknown",
          health: typeof row.saglikli === "string" ? row.saglikli : "bilinmiyor" }];
      });
      setOptions(entries);
      setState({ status: "ready", value: entries });
    } catch {
      if (current()) setState({ status: "error", message: "Model listesi okunamadı. Yeniden dene." });
    }
  }, [client, mode]);
  return { options, state, load };
}

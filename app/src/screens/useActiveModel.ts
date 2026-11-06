import { useCallback, useEffect, useRef, useState } from "react";
import type { CatalogClient } from "./useModelCatalog";

type ModelSnapshot = { client: CatalogClient; sessionId: string; model: string; label: string };
type ModelRead = ModelSnapshot & { revision: number; attempt: number; pending: boolean; error: string };
const READ_ERROR = "Etkin model okunamadı. Yeniden dene.";
const REFRESH_ERROR = "Etkin model yenilenemedi; son okunan model gösteriliyor. Yeniden dene.";

/** Read only the owned session's configured agent, after its identity bootstrap. */
export function useActiveModel(
  client: CatalogClient | undefined,
  sessionId: string | undefined,
  revision: number,
  bootstrap?: Promise<boolean>,
) {
  const [read, setRead] = useState<ModelRead | null>(null);
  const lastValid = useRef<ModelSnapshot | null>(null);
  const [retryRequest, setRetryRequest] = useState<{ client: CatalogClient | undefined; sessionId: string | undefined; count: number } | null>(null);
  const attempt = retryRequest?.client === client && retryRequest?.sessionId === sessionId ? retryRequest?.count ?? 0 : 0;
  const retry = useCallback(() => setRetryRequest((previous) => ({ client, sessionId,
    count: previous?.client === client && previous?.sessionId === sessionId ? (previous?.count ?? 0) + 1 : 1,
  })), [client, sessionId]);
  useEffect(() => {
    if (!client || !sessionId) return;
    let alive = true;
    const previous = lastValid.current;
    const owned = previous?.client === client && previous.sessionId === sessionId ? previous : null;
    const base = { client, sessionId, revision, attempt, model: owned?.model ?? "", label: owned?.label ?? "" };
    setRead({ ...base, pending: true, error: "" });
    const load = async () => {
      try {
        // `ready` is published before oturum.baslat completes. Await that exact promise.
        if (bootstrap && !await bootstrap) throw new Error("bootstrap");
        if (!alive) return;
        // One immediate local read-only recovery for an initial transient failure.
        const reads = !owned && attempt === 0 ? 2 : 1;
        for (let index = 0; index < reads; index += 1) {
          try {
            const payload = await client.request("kontrol.durum", {});
            if (!alive) return;
            const model = payload.model as { agent?: unknown; agent_label?: unknown } | undefined;
            if (payload.ok !== true || typeof model?.agent !== "string" || !model.agent.trim()) throw new Error("invalid model");
            const snapshot = { client, sessionId, model: model.agent, label: typeof model.agent_label === "string" ? model.agent_label : "" };
            lastValid.current = snapshot;
            setRead({ ...snapshot, revision, attempt, pending: false, error: "" });
            return;
          } catch {
            if (!alive) return;
            if (index + 1 === reads) throw new Error("model read");
          }
        }
      } catch {
        if (alive) setRead({ ...base, pending: false, error: owned ? REFRESH_ERROR : READ_ERROR });
      }
    };
    void load();
    return () => { alive = false; };
  }, [client, sessionId, revision, bootstrap, attempt]);
  const current = read && read.client === client && read.sessionId === sessionId ? read : null;
  const pending = Boolean(client && sessionId && (!current || current.revision !== revision || current.attempt !== attempt || current.pending));
  return { model: current?.model ?? "", label: current?.label ?? "", pending, error: pending ? "" : current?.error ?? "", retry };
}

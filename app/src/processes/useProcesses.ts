import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import type { ProjectProcess } from "./types";

const OUTPUT_STREAM_LIMIT = 256 * 1024;

export interface ProcessOutputStream {
  text: string;
  total: number;
}

function decode(payload: Record<string, unknown>): ProjectProcess[] {
  if (payload.ok !== true || !Array.isArray(payload.surecler)) {
    throw new Error(typeof payload.metin === "string" ? payload.metin : "Süreçler alınamadı.");
  }
  return payload.surecler.map((raw) => {
    if (!raw || typeof raw !== "object") throw new Error("Geçersiz süreç kaydı.");
    const item = raw as Record<string, unknown>;
    if (
      typeof item.surec_id !== "string" || typeof item.komut !== "string" ||
      typeof item.cwd !== "string" || typeof item.pid !== "number" ||
      !["calisiyor", "bitti", "hata", "durduruldu"].includes(String(item.durum)) ||
      !(typeof item.cikis_kodu === "number" || item.cikis_kodu === null) ||
      typeof item.cikti !== "string" || typeof item.baslangic !== "number"
    ) throw new Error("Geçersiz süreç kaydı.");
    return item as unknown as ProjectProcess;
  });
}

export function useProcesses(client: ProtocolClient) {
  const [processes, setProcesses] = useState<ProjectProcess[]>([]);
  const [outputStreams, setOutputStreams] = useState<Record<string, ProcessOutputStream>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setProcesses(decode(await client.request("surec.listele", {})));
      setError(null);
    } catch (reason) {
      setError(String(reason));
    }
  }, [client]);

  useEffect(() => {
    void refresh();
    const unlisten = client.onEvent((event) => {
      if (event.olay === "ProcessOutput") {
        const processId = event.surec_id;
        const text = event.metin;
        if (typeof processId === "string" && typeof text === "string" && text) {
          setOutputStreams((current) => {
            const stream = current[processId] ?? { text: "", total: 0 };
            return {
              ...current,
              [processId]: {
                text: (stream.text + text).slice(-OUTPUT_STREAM_LIMIT),
                total: stream.total + text.length,
              },
            };
          });
        }
        void refresh();
      } else if (event.olay === "ProcessStatus") {
        void refresh();
      }
    });
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => {
      unlisten();
      window.clearInterval(timer);
    };
  }, [client, refresh]);

  const start = useCallback(async (command: string, cwd = "") => {
    setBusy(true);
    try {
      const result = await client.request("surec.baslat", { komut: command, cwd });
      if (result.ok !== true) throw new Error(String(result.metin ?? "Süreç başlatılamadı."));
      await refresh();
      return true;
    } catch (reason) {
      setError(String(reason));
      return false;
    } finally {
      setBusy(false);
    }
  }, [client, refresh]);

  const stop = useCallback(async (processId: string) => {
    try {
      const result = await client.request("surec.kes", { surec_id: processId });
      if (result.ok !== true) throw new Error(String(result.metin ?? "Süreç durdurulamadı."));
      await refresh();
    } catch (reason) {
      setError(String(reason));
    }
  }, [client, refresh]);

  return { busy, error, outputStreams, processes, refresh, start, stop };
}

export type ProcessController = ReturnType<typeof useProcesses>;

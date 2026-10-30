import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import type { ProjectProcess } from "./types";

const OUTPUT_STREAM_LIMIT = 256 * 1024;

export interface ProcessOutputStream {
  text: string;
  total: number;
}

/** Çekirdeğin bildiği durumlar; yenisi eklenirse süreç gizlenmez, "hata" olarak gösterilir. */
const BILINEN_DURUMLAR = ["calisiyor", "bitti", "hata", "durduruldu"];

/**
 * Tek bozuk kayıt tüm listeyi düşürmez: biçimsiz kayıt atlanır, `pid` boş olabilir (süreç
 * doğamadı) ve bilinmeyen `durum` "hata" sayılır. Ölçüldü (30 Ekim): tek kayıttaki `pid: null` ya da
 * yeni bir durum, arayüzü "Geçersiz süreç kaydı." hatasında eski listeyle bırakıyordu (U4-28).
 */
function decode(payload: Record<string, unknown>): ProjectProcess[] {
  if (payload.ok !== true || !Array.isArray(payload.surecler)) {
    throw new Error(typeof payload.metin === "string" ? payload.metin : "Süreçler alınamadı.");
  }
  return payload.surecler.flatMap((raw): ProjectProcess[] => {
    if (!raw || typeof raw !== "object") return [];
    const item = raw as Record<string, unknown>;
    if (
      typeof item.surec_id !== "string" || typeof item.komut !== "string" ||
      typeof item.cwd !== "string" ||
      !(typeof item.pid === "number" || item.pid === null || item.pid === undefined) ||
      !(typeof item.cikis_kodu === "number" || item.cikis_kodu === null) ||
      typeof item.cikti !== "string" || typeof item.baslangic !== "number"
    ) return [];
    const durum = BILINEN_DURUMLAR.includes(String(item.durum)) ? (item.durum as ProjectProcess["durum"]) : "hata";
    return [{ ...(item as unknown as ProjectProcess), pid: typeof item.pid === "number" ? item.pid : null, durum }];
  });
}

/** Hata metnindeki "Error: " öneki kullanıcıya gösterilmez. */
function hataMetni(reason: unknown): string {
  return (reason instanceof Error ? reason.message : String(reason)).replace(/^Error:\s*/, "");
}

export function useProcesses(client: ProtocolClient) {
  const [processes, setProcesses] = useState<ProjectProcess[]>([]);
  const [outputStreams, setOutputStreams] = useState<Record<string, ProcessOutputStream>>({});
  //: Liste okuma hatası; her başarılı yenilemede silinir.
  const [listError, setListError] = useState<string | null>(null);
  //: Başlat/durdur hatası ayrıdır: 1 sn'lik yoklama bunu silmez, kullanıcı okuyabilir (U4-27).
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inflight = useRef(false);
  const dirty = useRef(false);

  // Aynı anda en fazla BİR liste isteği uçar; uçarken gelen istekler tek bir ek yenilemeye birleşir.
  // Ölçüldü (30 Ekim): her çıktı olayı + 1 sn yoklama istek fırtınası üretiyor, yanıt sırası
  // garanti olmadığından eski liste yenisini ezebiliyordu (U4-26).
  const refresh = useCallback(async () => {
    if (inflight.current) { dirty.current = true; return; }
    inflight.current = true;
    try {
      do {
        dirty.current = false;
        try {
          setProcesses(decode(await client.request("surec.listele", {})));
          setListError(null);
        } catch (reason) {
          setListError(hataMetni(reason));
        }
      } while (dirty.current);
    } finally {
      inflight.current = false;
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
    setActionError(null);
    try {
      const result = await client.request("surec.baslat", { komut: command, cwd });
      if (result.ok !== true) throw new Error(String(result.metin ?? "Süreç başlatılamadı."));
      await refresh();
      return true;
    } catch (reason) {
      setActionError(hataMetni(reason));
      return false;
    } finally {
      setBusy(false);
    }
  }, [client, refresh]);

  const stop = useCallback(async (processId: string) => {
    setActionError(null);
    try {
      const result = await client.request("surec.kes", { surec_id: processId });
      if (result.ok !== true) throw new Error(String(result.metin ?? "Süreç durdurulamadı."));
      await refresh();
    } catch (reason) {
      setActionError(hataMetni(reason));
    }
  }, [client, refresh]);

  return { busy, error: actionError ?? listError, outputStreams, processes, refresh, start, stop };
}

export type ProcessController = ReturnType<typeof useProcesses>;

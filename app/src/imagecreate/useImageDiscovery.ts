import { useCallback, useEffect, useRef, useState } from "react";
import type { AsyncState } from "../protocol/asyncState";
import { errorMessage, operationResult } from "../protocol/result";
export interface ImageClient { request(name: string, data: Record<string, unknown>): Promise<Record<string, unknown>> }
const ENDPOINTS = { providers: "gorsel.saglayicilar", gallery: "gorsel.galeri", flows: "gorsel.akislar" } as const;
export type DiscoverySection = keyof typeof ENDPOINTS;
/** Her bölüm kendi sırasını ve hatasını taşır; yeniden deneme diğer bölümleri bozmaz. */
export function useImageDiscovery(client: ImageClient | null, apply: (section: DiscoverySection, payload: Record<string, unknown>) => void) {
  const [states, setStates] = useState<Record<DiscoverySection, AsyncState<null>>>({ providers: { status: "loading" }, gallery: { status: "loading" }, flows: { status: "loading" } });
  const owner = useRef(0);
  const sequences = useRef({ providers: 0, gallery: 0, flows: 0 });
  const [galleryCursor, setGalleryCursor] = useState<[number, string] | null>(null);
  const cursor = useRef<[number, string] | null>(null);
  const appendPending = useRef(false);
  const load = useCallback(async (section: DiscoverySection, append = false) => {
    if (append && (section !== "gallery" || !cursor.current || appendPending.current)) return;
    if (append) appendPending.current = true;
    const requestedCursor = append ? cursor.current : null;
    const generation = owner.current, sequence = ++sequences.current[section];
    setStates((previous) => ({ ...previous, [section]: { status: "loading" } }));
    try {
      if (!client) throw new Error("Çekirdek bağlı değil.");
      const payload = await client.request(ENDPOINTS[section], section === "gallery" ? { sinir: 50, cursor: requestedCursor } : {});
      if (generation !== owner.current || sequence !== sequences.current[section]) return;
      const result = operationResult(payload, "Görsel verileri okunamadı.");
      if (!result.ok) { setStates((previous) => ({ ...previous, [section]: { status: "error", message: result.message } })); return; }
      if (section === "gallery") {
        const next = payload.next_cursor ?? null;
        if (next !== null && (!Array.isArray(next) || next.length !== 2 || typeof next[0] !== "number" || !Number.isFinite(next[0]) || next[0] < 0 || typeof next[1] !== "string" || !/^[0-9a-f-]{36}$/i.test(next[1]) || JSON.stringify(next) === JSON.stringify(requestedCursor))) throw new Error("Galeri sayfa işareti doğrulanamadı.");
        cursor.current = next as [number, string] | null;
        setGalleryCursor(cursor.current);
      }
      apply(section, { ...payload, append });
      setStates((previous) => ({ ...previous, [section]: { status: "ready", value: null } }));
    } catch (reason) {
      if (generation === owner.current && sequence === sequences.current[section]) setStates((previous) => ({ ...previous, [section]: { status: "error", message: errorMessage(reason) } }));
    } finally {
      if (section === "gallery" && generation === owner.current && sequence === sequences.current[section]) appendPending.current = false;
    }
  }, [client, apply]);
  useEffect(() => {
    const generation = ++owner.current;
    cursor.current = null; setGalleryCursor(null); appendPending.current = false;
    void load("providers"); void load("gallery"); void load("flows");
    return () => { owner.current = generation + 1; };
  }, [load]);
  return { states, load, galleryCursor };
}

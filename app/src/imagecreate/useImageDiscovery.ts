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
  const load = useCallback(async (section: DiscoverySection) => {
    const generation = owner.current, sequence = ++sequences.current[section];
    setStates((previous) => ({ ...previous, [section]: { status: "loading" } }));
    try {
      if (!client) throw new Error("Çekirdek bağlı değil.");
      const payload = await client.request(ENDPOINTS[section], {});
      if (generation !== owner.current || sequence !== sequences.current[section]) return;
      const result = operationResult(payload, "Görsel verileri okunamadı.");
      if (!result.ok) { setStates((previous) => ({ ...previous, [section]: { status: "error", message: result.message } })); return; }
      apply(section, payload);
      setStates((previous) => ({ ...previous, [section]: { status: "ready", value: null } }));
    } catch (reason) {
      if (generation === owner.current && sequence === sequences.current[section]) setStates((previous) => ({ ...previous, [section]: { status: "error", message: errorMessage(reason) } }));
    }
  }, [client, apply]);
  useEffect(() => {
    const generation = ++owner.current;
    void load("providers"); void load("gallery"); void load("flows");
    return () => { owner.current = generation + 1; };
  }, [load]);
  return { states, load };
}

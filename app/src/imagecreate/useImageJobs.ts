import { useEffect, useRef, useState } from "react";
import type { IstekFn } from "./akisCalistir";
import { ImageJobController, type ImageJobControllerState } from "./imageJobController";
import { ImageJobJournal } from "./imageJobJournal";

type Payload = Record<string, unknown>;
interface Client { request: IstekFn }
const WAITING: ImageJobControllerState = { ready: false, error: null, jobs: [] };

export function useImageJobs(client: Client | null, enabled: boolean, scope: string | undefined, onRecovered: (result: Payload) => void) {
  const [snapshot, setSnapshot] = useState<{ client: Client | null; scope: string | undefined; state: ImageJobControllerState } | null>(null);
  const owner = useRef<ImageJobController | null>(null);
  const recovered = useRef(onRecovered);
  recovered.current = onRecovered;
  useEffect(() => {
    if (!enabled || !client) { owner.current = null; return; }
    if (!scope) {
      setSnapshot({ client, scope, state: { ...WAITING, error: "Sohbet kapsamı doğrulanamadı; görsel işi başlatılmadı." } });
      return;
    }
    let controller: ImageJobController;
    try {
      controller = new ImageJobController((name, data) => client.request(name, data), new ImageJobJournal(localStorage, scope),
        (state) => setSnapshot({ client, scope, state }));
    } catch (error) {
      setSnapshot({ client, scope, state: { ...WAITING, error: error instanceof Error ? error.message : "Görsel iş kaydı açılamadı." } });
      return;
    }
    owner.current = controller;
    void controller.initialize();
    return () => { if (owner.current === controller) owner.current = null; controller.dispose(); };
  }, [client, enabled, scope]);
  const state = snapshot?.client === client && snapshot.scope === scope ? snapshot.state : WAITING;
  const blocked = enabled && (!state.ready || state.jobs.length > 0);
  const start = (data: Payload) => {
    const controller = owner.current;
    if (!enabled || !controller) throw new Error("Görsel iş bağlantısı hazır değil.");
    return controller.start(data);
  };
  const recover = async (jobId: string, cancel: boolean) => {
    const controller = owner.current;
    if (!controller) return;
    try {
      const result = await (cancel ? controller.cancel(jobId) : controller.observe(jobId));
      if (owner.current === controller) recovered.current(result);
    } catch { /* Controller hatayı iş kartında saklar; yeni üretim engeli korunur. */ }
  };
  return { state, blocked, start, recover, retry: () => { void owner.current?.initialize(); } };
}

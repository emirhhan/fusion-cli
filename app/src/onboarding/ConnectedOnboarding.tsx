import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import type { AsyncState } from "../protocol/asyncState";
import { errorMessage, operationResult } from "../protocol/result";
import { ControlPanel } from "../control/ControlPanel";
import { Onboarding } from "./Onboarding";
import { clearProgress, persistProgress, restoreProgress } from "./persistence";
import type { ApprenticeStatus, DiscoveredSource, ProviderSummary, SampleProject, OnboardingValue } from "./types";

interface ControlSummary { providers: ProviderSummary[]; apprentice: ApprenticeStatus }
function controlSummary(control: Record<string, unknown>): ControlSummary {
  const rows = Array.isArray(control.saglayicilar) ? control.saglayicilar : [];
  const model = (control.model ?? {}) as Record<string, unknown>;
  return {
    providers: rows.map((raw) => {
      const row = raw as Record<string, unknown>;
      return { id: String(row.id ?? ""), name: String(row.ad ?? row.id ?? "Sağlayıcı"), secretConfigured: row.kurulu === true,
        status: row.kurulu === true ? "configured-unverified" : "needs-setup" };
    }),
    apprentice: { active: typeof model.cirak_aktif === "boolean" ? model.cirak_aktif : null,
      recommendedModel: typeof model.onerilen_cirak === "string" ? model.onerilen_cirak : null },
  };
}
export function ConnectedOnboarding({ client, projects, runtimeVersion, onFinish }: {
  client: ProtocolClient; projects: SampleProject[]; runtimeVersion?: string; onFinish: (projectId: string | null) => void;
}) {
  const [value, setValue] = useState<OnboardingValue>(() => restoreProgress(projects));
  const [sources, setSources] = useState<AsyncState<DiscoveredSource[]>>({ status: "loading" });
  const [control, setControl] = useState<AsyncState<ControlSummary>>({ status: "loading" });
  const [lastControl, setLastControl] = useState<ControlSummary | null>(null);
  const [resetPending, setResetPending] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);
  const [storageError, setStorageError] = useState(false);
  const [provider, setProvider] = useState<string | null>(null);
  const owner = useRef(0);
  const sourcesRequest = useRef(0);
  const controlRequest = useRef(0);
  const resetGuard = useRef(false);
  const loadSources = useCallback(async () => {
    const generation = owner.current, sequence = ++sourcesRequest.current;
    setSources({ status: "loading" });
    try {
      const history = await client.request("gecmis.kaynaklar", {});
      if (generation !== owner.current || sequence !== sourcesRequest.current) return;
      const result = operationResult(history, "Kaynaklar okunamadı.", true);
      if (!result.ok) { setSources({ status: "error", message: result.message }); return; }
      const found = new Set(Array.isArray(history.kaynaklar) ? history.kaynaklar.map((raw) => String((raw as Record<string, unknown>).ad ?? "")) : []);
      setSources({ status: "ready", value: (["claude", "codex", "hermes"] as const).map((kind) => ({ kind, status: found.has(kind) ? "found" : "not-found" })) });
    } catch (reason) { if (generation === owner.current && sequence === sourcesRequest.current) setSources({ status: "error", message: errorMessage(reason) }); }
  }, [client]);
  const loadControl = useCallback(async () => {
    const generation = owner.current, sequence = ++controlRequest.current;
    setControl({ status: "loading" });
    try {
      const payload = await client.request("kontrol.durum", {});
      if (generation !== owner.current || sequence !== controlRequest.current) return;
      const result = operationResult(payload, "Kontrol durumu okunamadı.", true);
      if (result.ok) setLastControl(controlSummary(payload));
      setControl(result.ok ? { status: "ready", value: controlSummary(payload) } : { status: "error", message: result.message });
    } catch (reason) { if (generation === owner.current && sequence === controlRequest.current) setControl({ status: "error", message: errorMessage(reason) }); }
  }, [client]);
  useEffect(() => {
    const generation = ++owner.current;
    resetGuard.current = false; setResetPending(false); setResetError(null); setLastControl(null);
    void loadSources(); void loadControl();
    return () => { owner.current = generation + 1; };
  }, [loadSources, loadControl]);
  const reset = async () => {
    if (resetGuard.current) return;
    resetGuard.current = true; setResetPending(true); setResetError(null);
    const generation = owner.current;
    try {
      const payload = await client.request("kontrol.cirak_varsayilanina_don", {});
      if (generation !== owner.current) return;
      const result = operationResult(payload, "Ücretsiz çırağa dönülemedi.");
      if (!result.ok) { setResetError(result.message); return; }
      await loadControl();
    } catch (reason) { if (generation === owner.current) setResetError(errorMessage(reason)); }
    finally { if (generation === owner.current) { resetGuard.current = false; setResetPending(false); } }
  };
  const change = (next: OnboardingValue) => {
    setValue(next);
    setStorageError(!persistProgress(next).ok);
  };
  const finish = (id: string | null) => { clearProgress(); onFinish(id); };
  if (provider !== null) return <ControlPanel client={client} initialProviderId={provider} title="Sağlayıcıya bağlan"
    onClose={() => { setProvider(null); void loadControl(); }} onProvidersChanged={() => void loadControl()} />;
  const summary = control.status === "ready" ? control.value : lastControl;
  return <>
    {storageError && <p role="status">Kurulum ilerlemesi saklanamadı; bu oturumda geçerli.</p>}
    <Onboarding apprentice={summary?.apprentice ?? { active: null, recommendedModel: null }}
      sources={sources.status === "ready" ? sources.value : []} sourcesState={sources}
      providers={summary?.providers ?? []} controlState={control} controlHasSnapshot={summary !== null}
      onRetrySources={() => void loadSources()} onRetryControl={() => void loadControl()}
      onChange={change} onComplete={({ selectedProjectId }) => finish(selectedProjectId)} onSkip={() => finish(null)}
      onConnectProvider={setProvider} onResetToApprentice={() => void reset()} resetPending={resetPending} resetError={resetError}
      projects={projects} runtime={{ status: "ready", version: runtimeVersion }} value={value} />
  </>;
}

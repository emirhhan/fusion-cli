import { useWindowChrome } from "./platform/windowChrome";
import { readStorage, writeStorage } from "./platform/storage";
import { COMPLETION_KEY } from "./onboarding/persistence";
import { useState } from "react";
import type { RuntimeTransport } from "./runtime/types";
import { useRuntime } from "./runtime/useRuntime";
import { RuntimeSetup } from "./screens/RuntimeSetup";
import type { SessionTransport } from "./sessions/types";
import { SessionUygulama } from "./SessionApplication";

export { CoreConnectedApp, SessionUygulama, Uygulama } from "./SessionApplication";

interface AppProps {
  runtimeTransport?: RuntimeTransport;
  sessionTransport?: SessionTransport;
}

export default function App({ runtimeTransport, sessionTransport }: AppProps = {}) {
  useWindowChrome();
  const runtime = useRuntime(runtimeTransport);
  const [onboardingComplete, setOnboardingComplete] = useState(
    () => { const result = readStorage(() => window.localStorage, COMPLETION_KEY); return result.ok && result.value === "true"; },
  );
  const [completionWarning, setCompletionWarning] = useState(false);
  if (runtime.state !== "hazir") {
    return <RuntimeSetup {...runtime} onRepair={runtime.repair} />;
  }
  return (
    <>
    {completionWarning && <p role="status">Kurulum tercihi saklanamadı; bu oturumda geçerli.</p>}
    <SessionUygulama
      onboarding={!onboardingComplete}
      onOnboardingComplete={() => {
        setOnboardingComplete(true);
        setCompletionWarning(!writeStorage(() => window.localStorage, COMPLETION_KEY, "true").ok);
      }}
      runtimeVersion={runtime.version}
      transport={sessionTransport}
    />
    </>
  );
}

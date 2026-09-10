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
  const runtime = useRuntime(runtimeTransport);
  const [onboardingComplete, setOnboardingComplete] = useState(
    () => localStorage.getItem("fusion.onboarding.completed.v1") === "true",
  );
  if (runtime.state !== "hazir") {
    return <RuntimeSetup {...runtime} onRepair={runtime.repair} />;
  }
  return (
    <SessionUygulama
      onboarding={!onboardingComplete}
      onOnboardingComplete={() => {
        localStorage.setItem("fusion.onboarding.completed.v1", "true");
        setOnboardingComplete(true);
      }}
      runtimeVersion={runtime.version}
      transport={sessionTransport}
    />
  );
}

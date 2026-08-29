export type OnboardingStepId =
  | "welcome"
  | "runtime"
  | "sources"
  | "providers"
  | "project"
  | "complete";

export interface OnboardingValue {
  step: OnboardingStepId;
  selectedProjectId: string | null;
}

export interface RuntimeSummary {
  status: "checking" | "ready" | "repairable" | "error";
  version?: string;
}

export interface DiscoveredSource {
  kind: "claude" | "codex" | "hermes";
  status: "found" | "not-found";
  itemCount?: number;
}

export interface ProviderSummary {
  id: string;
  name: string;
  secretConfigured: boolean;
  status: "ready" | "needs-setup" | "unavailable";
}

export interface SampleProject {
  description: string;
  id: string;
  name: string;
  path?: string;
}

export interface OnboardingCompletion {
  selectedProjectId: string | null;
}


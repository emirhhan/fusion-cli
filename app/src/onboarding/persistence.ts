import { readStorage, writeStorage, removeStorage } from "../platform/storage";
import type { OnboardingValue, SampleProject } from "./types";
export const COMPLETION_KEY = "fusion.onboarding.completed.v1";
export const PROGRESS_KEY = "fusion.onboarding.progress.v1";
const STEPS = ["welcome", "runtime", "sources", "providers", "project", "complete"];
export function restoreProgress(projects: SampleProject[]): OnboardingValue {
  const initial: OnboardingValue = { step: "welcome", selectedProjectId: null };
  const result = readStorage(() => window.localStorage, PROGRESS_KEY);
  if (!result.ok || !result.value) return initial;
  try {
    const value = JSON.parse(result.value) as Record<string, unknown>;
    if (value.version !== 1 || typeof value.step !== "string" || !STEPS.includes(value.step)) return initial;
    return { step: value.step as OnboardingValue["step"], selectedProjectId: projects.some((project) => project.id === value.selectedProjectId) ? String(value.selectedProjectId) : null };
  } catch { return initial; }
}
export function persistProgress(value: OnboardingValue) {
  return writeStorage(() => window.localStorage, PROGRESS_KEY, JSON.stringify({ version: 1, step: value.step, selectedProjectId: value.selectedProjectId }));
}
export function clearProgress() { return removeStorage(() => window.localStorage, PROGRESS_KEY); }

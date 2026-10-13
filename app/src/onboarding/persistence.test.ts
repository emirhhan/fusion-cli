import { afterEach, expect, it } from "vitest";
import { PROGRESS_KEY, persistProgress, restoreProgress } from "./persistence";
afterEach(() => localStorage.clear());
it("bilinmeyen adımı reddeder ve kaybolan proje kimliğini temizler", () => {
  localStorage.setItem(PROGRESS_KEY, JSON.stringify({ version: 1, step: "unknown", selectedProjectId: "gone" }));
  expect(restoreProgress([])).toEqual({ step: "welcome", selectedProjectId: null });
  localStorage.setItem(PROGRESS_KEY, JSON.stringify({ version: 1, step: "project", selectedProjectId: "gone" }));
  expect(restoreProgress([])).toEqual({ step: "project", selectedProjectId: null });
});
it("yalnız doğrulanmış adım ve proje kimliğini saklar", () => {
  persistProgress({ step: "providers", selectedProjectId: null });
  expect(Object.keys(JSON.parse(localStorage.getItem(PROGRESS_KEY)!))).toEqual(["version", "step", "selectedProjectId"]);
});

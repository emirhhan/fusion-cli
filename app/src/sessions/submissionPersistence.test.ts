import { beforeEach, describe, expect, it, vi } from "vitest";
import { loadSubmissions, saveSubmission, updateSubmission } from "./submissionPersistence";

beforeEach(() => localStorage.clear());
describe("Kalıcı gönderim snapshot", () => {
  it("retry kimliği ve kuyruk girdisi sohbet restore'da korunur", () => {
    saveSubmission({requestId: "kalici", sessionId: "sohbet", root: "/proje", task: "iş", attachments: [], state: "queued"});
    updateSubmission("sohbet", "kalici", "failed");
    expect(loadSubmissions("sohbet")).toEqual([{requestId: "kalici", sessionId: "sohbet", root: "/proje", task: "iş", attachments: [], state: "failed"}]);
    expect(loadSubmissions("başka")).toEqual([]);
  });
  it("storage arızası sessiz kabul olmaz", () => {
    const setter = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("test kota"); });
    try {
      expect(() => saveSubmission({requestId: "kalici", sessionId: "sohbet", root: "/proje", task: "iş", attachments: [], state: "queued"})).toThrow();
    } finally { setter.mockRestore(); }
  });
});

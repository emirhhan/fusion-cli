import { beforeEach, describe, expect, it, vi } from "vitest";
import { loadSubmissions, MAX_FINISHED_SUBMISSIONS, saveSubmission, updateSubmission } from "./submissionPersistence";

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
  // U4-10 — Ölçüldü (29 Ekim): bozuk JSON `loadSubmissions`ta fırlıyor, `send` içindeki
  // saveSubmission her seferinde düşüyor ve o sohbete mesaj gönderilemiyordu.
  it("bozuk kayıt atılır, sohbet kilitlenmez", () => {
    localStorage.setItem("fusion.submissions:sohbet", "{kısmi yazım");
    expect(loadSubmissions("sohbet")).toEqual([]);
    expect(localStorage.getItem("fusion.submissions:sohbet")).toBeNull();
    expect(() => saveSubmission({requestId: "yeni", sessionId: "sohbet", root: "/p", task: "iş", attachments: [], state: "pending"})).not.toThrow();
    expect(loadSubmissions("sohbet")).toHaveLength(1);
  });
  it("dizi olmayan kayıt da sıfırlanır", () => {
    localStorage.setItem("fusion.submissions:sohbet", "{\"a\":1}");
    expect(loadSubmissions("sohbet")).toEqual([]);
    expect(localStorage.getItem("fusion.submissions:sohbet")).toBeNull();
  });
  it("tamamlanan girdiler sınırlanır, bekleyen/başarısız girdiler korunur", () => {
    saveSubmission({requestId: "bekleyen", sessionId: "sohbet", root: "/p", task: "iş", attachments: [], state: "pending"});
    for (let i = 0; i < 40; i++) {
      saveSubmission({requestId: `t${i}`, sessionId: "sohbet", root: "/p", task: "iş", attachments: [], state: "completed"});
    }
    const kayitlar = loadSubmissions("sohbet");
    expect(kayitlar.filter((k) => k.state === "completed").length).toBeLessThanOrEqual(MAX_FINISHED_SUBMISSIONS);
    expect(kayitlar.some((k) => k.requestId === "t39")).toBe(true);
    expect(kayitlar.some((k) => k.requestId === "t0")).toBe(false);
    expect(kayitlar.some((k) => k.requestId === "bekleyen")).toBe(true);
  });
  it("updateSubmission ile tamamlanan girdiler de sınırlanır", () => {
    for (let i = 0; i < 40; i++) {
      saveSubmission({requestId: `u${i}`, sessionId: "sohbet", root: "/p", task: "iş", attachments: [], state: "pending"});
      updateSubmission("sohbet", `u${i}`, "completed");
    }
    expect(loadSubmissions("sohbet").length).toBeLessThanOrEqual(MAX_FINISHED_SUBMISSIONS);
  });
  it("kota dolunca eski tamamlananlar atılıp bir kez yeniden denenir", () => {
    for (let i = 0; i < 5; i++) {
      saveSubmission({requestId: `e${i}`, sessionId: "sohbet", root: "/p", task: "iş", attachments: [], state: "completed"});
    }
    const gercek = Storage.prototype.setItem;
    let ilk = true;
    const setter = vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, k: string, v: string) {
      if (ilk) { ilk = false; throw new DOMException("dolu", "QuotaExceededError"); }
      gercek.call(this, k, v);
    });
    try {
      saveSubmission({requestId: "yeni", sessionId: "sohbet", root: "/p", task: "iş", attachments: [], state: "pending"});
    } finally { setter.mockRestore(); }
    expect(loadSubmissions("sohbet").map((k) => k.requestId)).toEqual(["yeni"]);
  });
});

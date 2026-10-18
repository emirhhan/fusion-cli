import { describe, expect, it } from "vitest";
import {
  addProject, assignChat, emptyRegistry, forgetChat, loadRegistry, PROJECT_REGISTRY_KEY,
  removeProject, renameProject, saveRegistry,
} from "./projectRecords";

function storage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  } as Storage;
}

describe("proje kayıtları", () => {
  it("preserves spaces in native folder paths", () => {
    const value = addProject(emptyRegistry, { id: "p", name: "VFSbot", root: "/Desktop/VFS-BOT ", now: 1 });
    expect(value.projects[0].root).toBe("/Desktop/VFS-BOT ");
  });
  it("ad vererek proje oluşturur; klasör isteğe bağlıdır", () => {
    const a = addProject(emptyRegistry, { id: "p1", name: "  Site  ", now: 5 });
    expect(a.projects).toEqual([{ id: "p1", name: "Site", createdAt: 5 }]);
    const b = addProject(a, { id: "p2", name: "API", root: "/x/api", now: 6 });
    expect(b.projects[1]).toEqual({ id: "p2", name: "API", root: "/x/api", createdAt: 6 });
    expect(emptyRegistry.projects).toHaveLength(0);
  });

  it("boş ya da aynı adı reddeder", () => {
    expect(() => addProject(emptyRegistry, { id: "p", name: "   ", now: 1 })).toThrow("Proje adı");
    const a = addProject(emptyRegistry, { id: "p1", name: "Site", now: 1 });
    expect(() => addProject(a, { id: "p2", name: "site", now: 2 })).toThrow("zaten var");
  });

  it("yeniden adlandırır ve kendi adını yeniden kabul eder", () => {
    const a = addProject(emptyRegistry, { id: "p1", name: "Site", now: 1 });
    expect(renameProject(a, "p1", "Mağaza").projects[0].name).toBe("Mağaza");
    expect(renameProject(a, "p1", "Site").projects[0].name).toBe("Site");
    expect(() => renameProject(a, "yok", "X")).toThrow("bulunamadı");
  });

  it("silince sohbetler projeden çıkar ama sohbet kaydı tutulur", () => {
    let r = addProject(emptyRegistry, { id: "p1", name: "Site", now: 1 });
    r = assignChat(r, "c1", "p1");
    r = assignChat(r, "c2", "p1");
    const kalan = removeProject(r, "p1");
    expect(kalan.projects).toHaveLength(0);
    expect(kalan.chats).toEqual({});
  });

  it("sohbeti taşır, projeden çıkarır ve unutur", () => {
    let r = addProject(emptyRegistry, { id: "p1", name: "Site", now: 1 });
    r = assignChat(r, "c1", "p1");
    expect(r.chats).toEqual({ c1: "p1" });
    expect(assignChat(r, "c1", null).chats).toEqual({});
    expect(forgetChat(r, "c1").chats).toEqual({});
    expect(() => assignChat(r, "c1", "yok")).toThrow("bulunamadı");
  });

  it("kaydeder, yükler; bozuk veriyi boş sayar", () => {
    const s = storage();
    const r = assignChat(addProject(emptyRegistry, { id: "p1", name: "Site", now: 1 }), "c1", "p1");
    saveRegistry(s, r);
    expect(loadRegistry(s)).toEqual(r);
    s.setItem(PROJECT_REGISTRY_KEY, "{bozuk");
    expect(loadRegistry(s)).toEqual(emptyRegistry);
    s.setItem(PROJECT_REGISTRY_KEY, JSON.stringify({ version: 1, projects: [{ id: 3 }], chats: {} }));
    expect(loadRegistry(s)).toEqual(emptyRegistry);
  });
});

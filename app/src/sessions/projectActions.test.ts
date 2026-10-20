import { describe, expect, it, vi } from "vitest";
import { createAndOpenProject, openProjectChat } from "./projectActions";
import { addProject, assignChat, emptyRegistry, type ProjectRegistry } from "./projectRecords";

function setup(fail = false) {
  let registry: ProjectRegistry = emptyRegistry;
  const createChat = vi.fn(async (_input: { root: string; mode: "kod" }) => {
    if (fail) throw new Error("çalışma dizini bulunamadı: /work/blog");
    return "chat-1";
  });
  const actions = {
    createChat,
    desktopRoot: async () => "/Desktop",
    createRecord: (input: { name: string; root?: string }) => {
      registry = addProject(registry, { ...input, id: "p1", now: 1 });
      return "p1";
    },
    assign: (chat: string, project: string) => { registry = assignChat(registry, chat, project); },
  };
  return { actions, registry: () => registry };
}

describe("project actions", () => {
  it("opens the exact native path including trailing spaces", async () => {
    const s = setup();
    await createAndOpenProject({ name: "VFSbot", root: "/Desktop/VFS-BOT " }, s.actions);
    expect(s.actions.createChat).toHaveBeenCalledWith({ root: "/Desktop/VFS-BOT ", mode: "kod" });
  });
  it("creates the first chat in the selected folder and assigns it", async () => {
    const s = setup();
    await createAndOpenProject({ name: "Blog", root: "/work/blog" }, s.actions);
    expect(s.actions.createChat).toHaveBeenCalledWith({ root: "/work/blog", mode: "kod" });
    expect(s.registry().chats["chat-1"]).toBe("p1");
  });
  it("opens a fresh chat in the existing project's folder", async () => {
    const s = setup();
    s.actions.createRecord({ name: "Blog", root: "/work/blog" });
    await openProjectChat(s.registry().projects[0], s.actions);
    expect(s.actions.createChat).toHaveBeenCalledWith({ root: "/work/blog", mode: "kod" });
    expect(s.registry().chats["chat-1"]).toBe("p1");
  });
  it("preserves a failed project's record for retry without assigning a chat", async () => {
    const s = setup(true);
    await expect(createAndOpenProject({ name: "Blog", root: "/work/blog" }, s.actions)).rejects.toThrow("çalışma dizini bulunamadı");
    expect(s.registry().projects).toHaveLength(1);
    expect(s.registry().chats).toEqual({});
  });
  it("resolves Desktop only for a project without a folder", async () => {
    const s = setup();
    await createAndOpenProject({ name: "Notes" }, s.actions);
    expect(s.actions.createChat).toHaveBeenCalledWith({ root: "/Desktop", mode: "kod" });
  });
});

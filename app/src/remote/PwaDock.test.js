import { afterEach, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/dom";
import { createDock } from "../../../src/fusion_cli/remote/pwa/dock.js";
afterEach(() => { document.body.innerHTML = ""; });
it("aynı kimlikli sekme ve pencereyi doğru türle odaklar, uzak simge yüklemez", async () => {
  const rpc = vi.fn(async () => ({ ok: true, data: { windows: [{ kind: "window", id: 1, pid: 2, app: "Notlar", title: "Taslak", icon: "https://example.com/logo.png" }], tabs: [{ kind: "tab", id: 1, title: "Belgeler" }] } }));
  const root = document.createElement("div"); document.body.append(root);
  const dock = createDock({ rpc, root, toast: vi.fn() }); await dock.refresh();
  fireEvent.click(screen.getByRole("button", { name: "Notlar: Taslak penceresini öne getir" }));
  expect(rpc).toHaveBeenCalledWith("desktop.focus", { target: { kind: "window", id: 1, pid: 2 } });
  fireEvent.click(screen.getByRole("button", { name: "Belgeler sekmesini öne getir" }));
  expect(rpc).toHaveBeenCalledWith("desktop.focus", { target: { kind: "tab", id: 1 } });
  expect(root.querySelector("img")).toBeNull(); dock.close(); expect(root.childElementCount).toBe(0);
});
it("kapanan hedef hatasını görünür tutar ve eşzamanlı yenilemeleri birleştirir", async () => {
  const rpc = vi.fn(async (method) => method === "desktop.targets" ? { ok: true, data: { tabs: [{ kind: "tab", id: 1, title: "Belgeler" }] } } : { ok: false, message: "Sekme kapandı." });
  const root = document.createElement("div"); document.body.append(root);
  const dock = createDock({ rpc, root }); await Promise.all([dock.refresh(), dock.refresh()]);
  expect(rpc).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Belgeler sekmesini öne getir" }));
  await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Sekme kapandı."));
  dock.close();
});

import { afterEach, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/dom";
import { appCount, createDock, groupApps, soleTarget } from "../../../src/fusion_cli/remote/pwa/dock.js";

afterEach(() => { document.body.innerHTML = ""; });

const PNG = "data:image/png;base64,iVBORw0KGgo=";
const windows = [
  { kind: "window", id: 10, pid: 100, app: "Google Chrome", title: "Fusion", icon: PNG, visible: true },
  { kind: "window", id: 11, pid: 100, app: "Google Chrome", title: "Gizli", visible: false },
  { kind: "window", id: 20, pid: 200, app: "Finder", title: "Masaüstü", visible: false },
  { kind: "window", id: 30, pid: 300, app: "Slack", title: "genel", icon: "https://example.com/logo.png" },
  { kind: "window", id: 31, pid: 301, app: "Slack", title: "ekip" },
];
const tabs = [
  { kind: "tab", id: 1, windowId: 5, title: "Belgeler", url: "https://www.example.com/a", active: true, icon: PNG },
  { kind: "tab", id: 2, windowId: 5, title: "Posta", url: "https://mail.example.org/" },
  { kind: "tab", id: 3, windowId: 6, title: "Haberler", url: "https://news.example.net/" },
];

function setup(payload = { windows, tabs }, rpcImpl) {
  const rpc = vi.fn(rpcImpl ?? (async (method) => (method === "desktop.targets" ? { ok: true, data: payload } : { ok: true })));
  const root = document.createElement("div");
  document.body.append(root);
  const dock = createDock({ rpc, root, toast: vi.fn() });
  return { rpc, root, dock };
}

it("pencereleri ve sekmeleri uygulamalara toplar; Chrome sekmeleri Chrome'a bağlanır", () => {
  const apps = groupApps(windows, tabs);
  expect(apps.map((app) => app.name)).toEqual(["Google Chrome", "Finder", "Slack"]); // etkin önce
  const chrome = apps[0];
  expect(chrome.windows).toHaveLength(2);
  expect(chrome.tabs).toHaveLength(3);
  expect(appCount(chrome)).toBe(5);
  expect(chrome.active).toBe(true);
  expect(soleTarget(apps[1])).toEqual({ kind: "window", id: 20, pid: 200 });
  expect(soleTarget(chrome)).toBeNull();
});

it("pencere satırı yokken bile sekmeler 'Chrome' uygulaması altında görünür", () => {
  const apps = groupApps([], tabs);
  expect(apps).toHaveLength(1);
  expect(apps[0].name).toBe("Chrome");
});

it("1. aşamada yalnız uygulamalar görünür; sekme/pencere yığılmaz", async () => {
  const { root, dock } = setup();
  await dock.refresh();
  expect(root.querySelectorAll(".mini-dock__app")).toHaveLength(3);
  expect(root.querySelector(".mini-dock__row")).toBeNull();
  const chrome = root.querySelector('[data-app="Google Chrome"]');
  expect(chrome.querySelector(".mini-dock__badge").textContent).toBe("5");
  expect(chrome.classList.contains("is-active")).toBe(true);
  expect(chrome.querySelector("img").getAttribute("src")).toBe(PNG);
  expect(root.querySelector('[data-app="Slack"] img')).toBeNull(); // uzak simge yüklenmez, harf gösterilir
  expect(root.querySelector('[data-app="Slack"] .mini-dock__letter').textContent).toBe("S");
  dock.close();
});

it("tek hedefli uygulamada ikinci aşama atlanır ve doğrudan odaklanır", async () => {
  const { rpc, root, dock } = setup();
  await dock.refresh();
  fireEvent.click(screen.getByRole("button", { name: "Finder uygulamasını öne getir" }));
  expect(rpc).toHaveBeenCalledWith("desktop.focus", { target: { kind: "window", id: 20, pid: 200 } });
  expect(root.querySelector(".mini-dock__back")).toBeNull();
  dock.close();
});

it("çok hedefli uygulama 2. aşamayı açar: pencere başına gruplu sekmeler, etkin işaret, geri düğmesi", async () => {
  const { rpc, root, dock } = setup();
  await dock.refresh();
  fireEvent.click(root.querySelector('[data-app="Google Chrome"]'));
  expect(root.querySelector(".mini-dock__apps")).toBeNull();
  const groups = [...root.querySelectorAll(".mini-dock__group")].map((node) => node.textContent);
  expect(groups).toEqual(["Pencereler (2)", "Pencere 1 · 2 sekme", "Pencere 2 · 1 sekme"]);
  expect(root.querySelector(".mini-dock__mark").textContent).toBe("Etkin");
  expect(within(root).getByText("example.com")).toBeTruthy(); // www. atılır
  fireEvent.click(screen.getByRole("button", { name: "Belgeler sekmesini öne getir" }));
  expect(rpc).toHaveBeenCalledWith("desktop.focus", { target: { kind: "tab", id: 1 } });
  fireEvent.click(screen.getByRole("button", { name: "Google Chrome: Fusion penceresini öne getir" }));
  expect(rpc).toHaveBeenCalledWith("desktop.focus", { target: { kind: "window", id: 10, pid: 100 } });
  fireEvent.click(screen.getByRole("button", { name: "Uygulamalara dön" }));
  expect(root.querySelectorAll(".mini-dock__app")).toHaveLength(3);
  dock.close();
});

it("uzun listede arama görünür ve süzer; kısa listede görünmez", async () => {
  const many = Array.from({ length: 12 }, (_, index) => ({ kind: "tab", id: index + 1, windowId: 1, title: index === 7 ? "Hedef sayfa" : `Sayfa ${index}`, url: `https://s${index}.test/` }));
  const { root, dock } = setup({ windows: [], tabs: many });
  await dock.refresh();
  fireEvent.click(root.querySelector('[data-app="Chrome"]'));
  const search = screen.getByRole("searchbox", { name: "Chrome içinde ara" });
  fireEvent.input(search, { target: { value: "hedef" } });
  expect(root.querySelectorAll(".mini-dock__row")).toHaveLength(1);
  fireEvent.input(screen.getByRole("searchbox"), { target: { value: "yok-boyle" } });
  expect(root.textContent).toContain("Aramayla eşleşen yok.");
  dock.close();
  const small = setup();
  await small.dock.refresh();
  fireEvent.click(small.root.querySelector('[data-app="Google Chrome"]'));
  expect(small.root.querySelector(".mini-dock__search")).toBeNull(); // 5 öğe: eşik altı
  small.dock.close();
});

it("kapanan hedef hatasını görünür tutar ve eşzamanlı yenilemeleri birleştirir", async () => {
  const { rpc, root, dock } = setup({ windows: [], tabs: [tabs[0]] }, async (method) => (method === "desktop.targets" ? { ok: true, data: { windows: [], tabs: [tabs[0]] } } : { ok: false, message: "Sekme kapandı." }));
  await Promise.all([dock.refresh(), dock.refresh()]);
  expect(rpc).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Chrome uygulamasını öne getir" }));
  await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Sekme kapandı."));
  dock.close();
});

it("boş, yetki ve ağ hatası durumlarını açık Türkçe gösterir", async () => {
  const empty = setup({ windows: [], tabs: [] });
  await empty.dock.refresh();
  expect(empty.root.textContent).toContain("Açık uygulama yok.");
  empty.dock.close();
  const permission = setup({ windows: [], tabs: [], native_error: "Ekran Kaydı izni gerekli." });
  await permission.dock.refresh();
  expect(screen.getByRole("status").textContent).toBe("Ekran Kaydı izni gerekli.");
  permission.dock.close();
  const offline = setup(undefined, async () => { throw new Error("Bilgisayara ulaşılamıyor."); });
  await offline.dock.refresh();
  expect(offline.root.textContent).toContain("Uygulamalar şu an alınamadı.");
  expect(offline.root.querySelector(".mini-dock__error").textContent).toBe("Bilgisayara ulaşılamıyor.");
  offline.dock.close();
  expect(offline.root.childElementCount).toBe(0);
});

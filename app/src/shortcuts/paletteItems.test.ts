import { afterEach, describe, expect, it, vi } from "vitest";
import { buildPaletteItems } from "./paletteSources";
import { DEFAULT_KEYMAP } from "./keys";
import { fold, parseQuery, rankItems, readRecent, rememberRecent, score, type PaletteItem } from "./paletteItems";
import { runAppAction, type AppActionDeps } from "./appActions";

const item = (id: string, kind: PaletteItem["kind"], label: string, keywords = ""): PaletteItem => ({ id, kind, label, keywords, run: vi.fn() });

afterEach(() => localStorage.clear());

describe("palet sorgusu", () => {
  it("önekler türü daraltır", () => {
    expect(parseQuery("> yeni")).toEqual({ text: "yeni", kinds: ["eylem", "ekran"] });
    expect(parseQuery("@app.py").kinds).toEqual(["dosya"]);
    expect(parseQuery("#dün").kinds).toEqual(["sohbet"]);
    expect(parseQuery("terminal")).toEqual({ text: "terminal", kinds: null });
  });

  it("Türkçe harfleri katlar ve baştan eşleşmeyi öne alır", () => {
    expect(fold("Kenar Çubuğu")).toBe("kenar cubugu");
    expect(score("cubugu", "Kenar çubuğunu aç/kapat")).toBeGreaterThan(0);
    expect(score("ter", "Terminali aç")).toBeGreaterThan(score("ter", "Ayarlar › Filtre"));
    expect(score("trm", "Terminal")).toBeGreaterThan(0);
    expect(score("xyz", "Terminal")).toBe(-1);
  });

  it("boş sorguda son kullanılanlar başta, dosyalar yok; sorguda puan sırası", () => {
    const items = [item("a", "eylem", "Yeni sohbet"), item("b", "ekran", "Kitaplık"), item("c", "dosya", "app.py")];
    expect(rankItems(items, "", ["b"]).map((x) => x.id)).toEqual(["b", "a"]);
    expect(rankItems(items, "@", []).map((x) => x.id)).toEqual(["c"]);
    expect(rankItems(items, "kit", []).map((x) => x.id)).toEqual(["b"]);
    expect(rankItems(items, ">app", [])).toEqual([]);
  });

  it("son kullanılanları en çok sekiz tutar ve tekrarlamaz", () => {
    for (let index = 0; index < 10; index += 1) rememberRecent(`x${index}`);
    rememberRecent("x5");
    const recent = readRecent();
    expect(recent).toHaveLength(8);
    expect(recent[0]).toBe("x5");
    expect(new Set(recent).size).toBe(8);
  });
});

describe("palet kaynakları ve eylemler", () => {
  it("her eylem tuşuyla, ekranlar, sohbetler, komutlar ve ayarlar listelenir", () => {
    const runAction = vi.fn(), insert = vi.fn();
    const items = buildPaletteItems({
      keymap: DEFAULT_KEYMAP, mac: true, chats: [{ id: "s1", title: "Dün", project: "proje" }],
      commands: [{ ad: "status", aciklama: "durum" }], runAction, openScreen: vi.fn(), openChat: vi.fn(),
      insertCommand: insert, openSettings: vi.fn(),
    });
    const terminal = items.find((x) => x.id === "eylem:terminal");
    expect(terminal?.shortcut).toBe("⌘J");
    terminal?.run();
    expect(runAction).toHaveBeenCalledWith("terminal");
    expect(items.some((x) => x.id === "eylem:palet")).toBe(false);
    expect(items.some((x) => x.kind === "ekran" && x.label === "Zamanlananlar")).toBe(true);
    expect(items.some((x) => x.kind === "ayar" && x.label === "Kısayollar")).toBe(true);
    items.find((x) => x.id === "komut:status")?.run();
    expect(insert).toHaveBeenCalledWith("status");
  });

  it("eylem adlarını uygulama işlerine eşler", () => {
    const deps = Object.fromEntries(
      ["openPalette", "newChat", "openSettings", "toggleSidebar", "toggleTerminal", "openPreview", "toggleInspector", "back", "forward", "openHistory", "share", "help", "closeSplit", "runCommand"]
        .map((name) => [name, vi.fn()]),
    ) as unknown as AppActionDeps;
    deps.selectChat = vi.fn(() => true);
    expect(runAppAction("dosya_ara", deps)).toBe(true);
    expect(deps.openPalette).toHaveBeenCalledWith("@");
    expect(runAppAction("kisayollar", deps)).toBe(true);
    expect(deps.openSettings).toHaveBeenCalledWith("kisayollar");
    expect(runAppAction("sohbet_3", deps)).toBe(true);
    expect(deps.selectChat).toHaveBeenCalledWith(2);
    expect(runAppAction("komut:status", deps)).toBe(true);
    expect(deps.runCommand).toHaveBeenCalledWith("/status");
    expect(runAppAction("ucmak", deps)).toBe(false);
    expect(runAppAction("komut:", deps)).toBe(false);
  });
});

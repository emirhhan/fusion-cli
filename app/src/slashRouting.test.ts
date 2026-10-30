import { describe, expect, it } from "vitest";
import { attachmentsFromDroppedFiles, isFolderCommand, startsWithFilePath } from "./slashRouting";

describe("startsWithFilePath (U3-25)", () => {
  it("mutlak yolla başlayan normal istemi komut saymaz", () => {
    expect(startsWithFilePath("/Users/ben/app.py neden çöküyor?")).toBe(true);
    expect(startsWithFilePath("/etc/hosts dosyasını oku")).toBe(true);
    expect(startsWithFilePath("/tmp/x.log bak")).toBe(true);
    expect(startsWithFilePath("/proje/README.md")).toBe(true);
  });
  it("gerçek komutlar ve tek sözcüklü yazımlar komut kalır", () => {
    for (const komut of ["/model", "/mcp github", "/resumeclaude", "/klasor", "/foo", "/effort high", "/"]) {
      expect(startsWithFilePath(komut)).toBe(false);
    }
  });
});

describe("isFolderCommand (U3-34)", () => {
  it("argümanlı /klasor da klasör komutudur", () => {
    expect(isFolderCommand("/klasor", "klasor")).toBe(true);
    expect(isFolderCommand("/Klasor ~/proje", "klasor")).toBe(true);
    expect(isFolderCommand("/klasorler", "klasor")).toBe(false);
    expect(isFolderCommand("klasor", "klasor")).toBe(false);
  });
});

describe("attachmentsFromDroppedFiles (U3-26)", () => {
  const dosya = (ad: string, path?: string, type = "") => {
    const file = new File(["x"], ad, { type });
    if (path !== undefined) Object.defineProperty(file, "path", { value: path });
    return file;
  };
  it("yalnız mutlak yolu olanları ekler; çıplak dosya adı yol sayılmaz", () => {
    const sonuc = attachmentsFromDroppedFiles([
      dosya("a.png", "/proje/a.png", "image/png"),
      dosya("b.txt"),
      dosya("c.txt", "c.txt"),
      dosya("d.txt", "C:\\proje\\d.txt"),
    ]);
    expect(sonuc.additions).toEqual([
      { kind: "image", name: "a.png", path: "/proje/a.png" },
      { kind: "file", name: "d.txt", path: "C:\\proje\\d.txt" },
    ]);
    expect(sonuc.unresolved).toBe(2);
  });
  it("aynı yolu ikinci kez eklemez", () => {
    const mevcut = [{ kind: "file" as const, name: "a.txt", path: "/p/a.txt" }];
    const sonuc = attachmentsFromDroppedFiles([dosya("a.txt", "/p/a.txt"), dosya("a.txt", "/p/a.txt")], mevcut);
    expect(sonuc.additions).toEqual([]);
    expect(sonuc.unresolved).toBe(0);
  });
});

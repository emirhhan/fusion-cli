import { describe, expect, it } from "vitest";
import { olayMetni } from "./olayMetni";

describe("olayMetni", () => {
  it("araç çalıştırmayı okunabilir yazar", () => {
    expect(olayMetni({ olay: "ToolExecuted", name: "write_file" })).toContain("write_file");
  });

  it("tur sonucunu açıkça bildirir", () => {
    expect(olayMetni({ olay: "TurnOutcome", status: "completed" })).toContain("tamamlandı");
    expect(olayMetni({ olay: "TurnOutcome", status: "failed" })).toContain("başarısız");
  });

  it("ham JSON sızdırmaz", () => {
    const metin = olayMetni({ olay: "ToolExecuted", name: "run_shell", args: { command: "ls" } });
    expect(metin).not.toContain("{");
  });

  it("bilinmeyen olay için null döner", () => {
    expect(olayMetni({ olay: "BilinmeyenOlay" })).toBeNull();
  });

  it("bozuk dosya listesi arayüzü düşürmez", () => {
    expect(() => olayMetni({ olay: "FilesChanged", paths: { path: "a.txt" } })).not.toThrow();
    expect(olayMetni({ olay: "FilesChanged", paths: { path: "a.txt" } })).toBeNull();
  });
});

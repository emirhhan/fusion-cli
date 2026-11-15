import { describe, expect, it } from "vitest";
import { DEFAULT_SKILL_TASK, isImageCommand, parseCapabilityInput, parseImageRequest, skillPrefixToSlash } from "./capabilityInput";

const names = {
  skills: ["seo-denetimi", "Rapor"],
  mcp: ["github", "notion"],
  commands: ["model", "rapor", "görsel"],
};

describe("parseCapabilityInput", () => {
  it("satır başındaki /beceri adını ve kalan görevi ayırır", () => {
    expect(parseCapabilityInput("/seo-denetimi ana sayfayı tara", names).skill).toEqual({
      ad: "seo-denetimi",
      rest: "ana sayfayı tara",
    });
    expect(parseCapabilityInput("/SEO-denetimi", names).skill).toEqual({ ad: "seo-denetimi", rest: "" });
  });

  it("komutla çakışan beceri adında komut kazanır", () => {
    expect(parseCapabilityInput("/rapor haftalık", names).skill).toBeNull();
    expect(parseCapabilityInput("/model x", names).skill).toBeNull();
  });

  it("bilinmeyen / ve satır ortası / beceri sayılmaz", () => {
    expect(parseCapabilityInput("/bilinmeyen x", names).skill).toBeNull();
    expect(parseCapabilityInput("bak /seo-denetimi", names).skill).toBeNull();
  });

  it("@mcp adlarını bulur; bilinmeyen ve dosya anmalarını yok sayar", () => {
    const parsed = parseCapabilityInput("@github issue aç, sonra @notion'a yaz @src/app.ts @yok", names);
    expect(parsed.mcp).toEqual(["github"]);
    expect(parseCapabilityInput("@notion, @GitHub.", names).mcp).toEqual(["notion", "github"]);
    expect(parseCapabilityInput("a@github.com mail", names).mcp).toEqual([]);
  });

  it("beceri ve MCP birlikte seçilebilir", () => {
    const parsed = parseCapabilityInput("/seo-denetimi @github depoyu incele", names);
    expect(parsed.skill?.ad).toBe("seo-denetimi");
    expect(parsed.mcp).toEqual(["github"]);
    expect(DEFAULT_SKILL_TASK("seo-denetimi")).toContain("seo-denetimi");
  });
});

describe("skillPrefixToSlash (P-052)", () => {
  it("$beceri bilinen adda slash olur; bilinmeyen ve fiyat metni dokunulmaz", () => {
    expect(skillPrefixToSlash("$seo-denetimi ana sayfa", ["seo-denetimi"])).toBe("/seo-denetimi ana sayfa");
    expect(skillPrefixToSlash("$5 fiyat", ["seo-denetimi"])).toBe("$5 fiyat");
    expect(skillPrefixToSlash("$yok x", ["seo-denetimi"])).toBe("$yok x");
    expect(parseCapabilityInput("$seo-denetimi tara", names).skill?.ad).toBe("seo-denetimi");
  });
});

describe("isImageCommand", () => {
  it("/görsel ve /gorsel sohbet turudur; benzer komutlar değildir", () => {
    for (const yes of ["/görsel kedi", "/gorsel", "  /GÖRSEL  kedi --oran 16:9"]) expect(isImageCommand(yes)).toBe(true);
    for (const no of ["/görselleştir x", "görsel çiz", "/model", "x /görsel"]) expect(isImageCommand(no)).toBe(false);
  });
});

describe("parseImageRequest", () => {
  it("istemi ve --oran değerini ayırır; oran yoksa 1:1", () => {
    expect(parseImageRequest("/görsel mavi kuş --oran 16:9")).toEqual({ prompt: "mavi kuş", aspect: "16:9" });
    expect(parseImageRequest("/gorsel   kedi   yağmurda")).toEqual({ prompt: "kedi yağmurda", aspect: "1:1" });
    expect(parseImageRequest("/GÖRSEL kedi --oran=9:16 yağmurda")).toEqual({ prompt: "kedi yağmurda", aspect: "9:16" });
    expect(parseImageRequest("/görsel")).toEqual({ prompt: "", aspect: "1:1" });
  });
});

describe("dalga 4 — U1-21 / U1-22", () => {
  it("/görseli ve /görseller çekirdekle aynı biçimde görsel komutudur (U1-22)", () => {
    for (const yes of ["/görseli kedi", "/görseller kedi", "/gorseller"]) expect(isImageCommand(yes)).toBe(true);
    expect(isImageCommand("/görselleştir x")).toBe(false);
  });

  it("MCP anması dosya anmasıyla aynı sınır karakterlerini kabul eder (U1-21)", () => {
    expect(parseCapabilityInput("(@github) ve [@notion] {@github}", { skills: [], mcp: ["github", "notion"], commands: [] }).mcp)
      .toEqual(["github", "notion"]);
  });
});

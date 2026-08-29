import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/** Ölçülmüş değerler sessizce değişmemeli; değişirse referanstan sapılmış olur. */
describe("tasarım token'ları", () => {
  const css = readFileSync(new URL("./tokens.css", import.meta.url), "utf8");

  it("ölçülmüş renkleri taşır", () => {
    expect(css).toContain("--zemin: #ffffff");
    expect(css).toContain("--kenar-cubugu: #f9f9fa");
    expect(css).toContain("--secili-satir: #efeff0");
    expect(css).toContain("--kullanici-balonu: #f5f5f5");
    expect(css).toContain("--vurgu-hapi: #ebebfa");
  });

  it("ölçülmüş kenar çubuğu genişliğini taşır", () => {
    expect(css).toContain("--kenar-cubugu-genislik: 281px");
  });
});

import { describe, expect, it } from "vitest";
import { isProjectRoot, projectName } from "./projectRoots";

describe("isProjectRoot", () => {
  it("dosya sistemi kökünü proje saymaz", () => {
    // GUI'den açılan oturumun kökü bir ara "/" olabiliyordu ve kenar çubuğunda
    // adı "/" olan anlamsız bir proje satırı beliriyordu.
    expect(isProjectRoot("/")).toBe(false);
    expect(isProjectRoot("")).toBe(false);
    expect(isProjectRoot("C:\\")).toBe(false);
  });

  it("ev dizinini tek başına proje saymaz", () => {
    expect(isProjectRoot("/Users/kullanici")).toBe(false);
    expect(isProjectRoot("/home/kullanici")).toBe(false);
  });

  it("Windows ev dizinini ve sürücü kökünü proje saymaz (U4-57)", () => {
    expect(isProjectRoot("C:\\Users\\ad")).toBe(false);
    expect(isProjectRoot("C:\\")).toBe(false);
    expect(isProjectRoot("C:\\Users\\ad\\Desktop")).toBe(true);
  });

  it("gerçek klasörleri proje sayar", () => {
    expect(isProjectRoot("/Users/kullanici/Desktop")).toBe(true);
    expect(isProjectRoot("/Users/kullanici/Desktop/fusion-cli")).toBe(true);
  });
});

describe("projectName", () => {
  it("son klasör adını verir", () => {
    expect(projectName("/Users/kullanici/Desktop/fusion-cli")).toBe("fusion-cli");
  });
});

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
    expect(isProjectRoot("/Users/emirhan")).toBe(false);
    expect(isProjectRoot("/home/emirhan")).toBe(false);
  });

  it("gerçek klasörleri proje sayar", () => {
    expect(isProjectRoot("/Users/emirhan/Desktop")).toBe(true);
    expect(isProjectRoot("/Users/emirhan/Desktop/fusion-cli")).toBe(true);
  });
});

describe("projectName", () => {
  it("son klasör adını verir", () => {
    expect(projectName("/Users/emirhan/Desktop/fusion-cli")).toBe("fusion-cli");
  });
});

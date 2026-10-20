import { describe, expect, it } from "vitest";
import { DEFAULT_TITLE, canApplySuggestedTitle } from "./title";

describe("canApplySuggestedTitle", () => {
  it("varsayılan adlı sekmeye öneriyi uygular", () => {
    expect(canApplySuggestedTitle(DEFAULT_TITLE, "Tarayıcı oyunu yaz")).toBe(true);
  });

  it("kullanıcının ya da devralmanın verdiği başlığı ezmez", () => {
    expect(canApplySuggestedTitle("Kendi başlığım", "Tarayıcı oyunu yaz")).toBe(false);
    expect(canApplySuggestedTitle("[claude] eski iş", "Tarayıcı oyunu yaz")).toBe(false);
  });

  it("boş öneride sekmeyi varsayılan adında bırakır", () => {
    expect(canApplySuggestedTitle(DEFAULT_TITLE, "  ")).toBe(false);
  });
});

import { describe, expect, it } from "vitest";
import { sirlariMaskele } from "./sirMaskesi";

describe("sirlariMaskele", () => {
  it.each([
    ["curl -H 'Authorization: Bearer abcdefghijkl123' https://x", "abcdefghijkl123"],
    ["OPENAI_API_KEY=sk-proj-abcdefghijklmnop", "sk-proj-abcdefghijklmnop"],
    ["export GROQ=gsk_abcdefghijklmnop1234", "gsk_abcdefghijklmnop1234"],
    ["hf_abcdefghijklmnopqrstuv", "hf_abcdefghijklmnopqrstuv"],
    ["nvapi-abcdefghijklmnop1234", "nvapi-abcdefghijklmnop1234"],
    ["eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4", "eyJhbGciOiJIUzI1"],
    ["parola: gizli123", "gizli123"],
  ])("%s içindeki sırrı gizler", (girdi, sir) => {
    const cikti = sirlariMaskele(girdi);
    expect(cikti).not.toContain(sir);
    expect(cikti).toContain("[gizlendi]");
  });

  it("sır içermeyen metne dokunmaz", () => {
    expect(sirlariMaskele("pytest -q tests/test_a.py")).toBe("pytest -q tests/test_a.py");
  });
});

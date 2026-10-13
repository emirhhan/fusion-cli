import { describe, it, expect } from "vitest";
import { visibleModelForSession } from "./modelSnapshot";

describe("session-owned model display", () => {
  const a = {};
  const b = {};
  const snapshot = { sessionId: "A", client: a, model: "provider/alpha", label: "Alpha" };
  it("shows the verified model only in the matching session", () => {
    expect(visibleModelForSession(snapshot, "A", a)).toEqual({ model: "provider/alpha", label: "Alpha" });
    expect(visibleModelForSession(snapshot, "B", a)).toEqual({ model: "", label: "" });
  });
  it("does not transfer model identity across transport owners", () => {
    expect(visibleModelForSession(snapshot, "A", b)).toEqual({ model: "", label: "" });
    expect(visibleModelForSession(snapshot, undefined, a)).toEqual({ model: "", label: "" });
    expect(visibleModelForSession(null, "A", a)).toEqual({ model: "", label: "" });
  });
});

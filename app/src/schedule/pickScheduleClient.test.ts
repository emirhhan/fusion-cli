import { describe, expect, it } from "vitest";
import { pickScheduleClient } from "./pickScheduleClient";

const core = () => ({ request: async () => ({ ok: true }) });

describe("pickScheduleClient", () => {
  it("etkin oturum hazırsa onun istemcisini seçer", () => {
    const [a, b] = [core(), core()];
    const active = { client: a, status: "ready" };
    expect(pickScheduleClient(active, [{ client: b, status: "ready" }, active])).toBe(a);
  });

  it("etkin sohbet yokken hazır başka oturumun istemcisini seçer", () => {
    const b = core();
    expect(pickScheduleClient(null, [{ client: core(), status: "closed" }, { client: b, status: "ready" }])).toBe(b);
  });

  it("etkin oturum çöktüyse ölü istemci yerine hazır olanı seçer", () => {
    const b = core();
    const dead = { client: core(), status: "crashed" };
    expect(pickScheduleClient(dead, [dead, { client: b, status: "ready" }])).toBe(b);
  });

  it("hazır oturum yoksa null döner", () => {
    expect(pickScheduleClient(null, [])).toBeNull();
    expect(pickScheduleClient(undefined, [{ client: core(), status: "crashed" }])).toBeNull();
  });
});

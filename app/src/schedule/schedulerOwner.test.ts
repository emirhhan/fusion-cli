import { afterEach, describe, expect, it } from "vitest";
import { schedulerOwnerId } from "./schedulerOwner";

afterEach(() => sessionStorage.clear());

describe("schedulerOwnerId", () => {
  it("aynı pencerede (yeniden yüklemede de) aynı kimliği verir", () => {
    const first = schedulerOwnerId();
    expect(first.length).toBeGreaterThan(8);
    expect(schedulerOwnerId()).toBe(first);
  });

  it("yeni pencere (boş oturum depolaması) farklı kimlik alır", () => {
    const first = schedulerOwnerId();
    sessionStorage.clear();
    expect(schedulerOwnerId({ fresh: true })).not.toBe(first);
  });

  it("depolama kullanılamazsa da kimlik üretir", () => {
    const broken = { getItem: () => { throw new Error("kapalı"); }, setItem: () => { throw new Error("kapalı"); } } as unknown as Storage;
    expect(schedulerOwnerId({ storage: broken, fresh: true }).length).toBeGreaterThan(8);
  });
});

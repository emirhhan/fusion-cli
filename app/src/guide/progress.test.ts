import { beforeEach, expect, it } from "vitest";
import { GUIDE_PROGRESS_KEY, markSeen, pendingIds, readSeen } from "./progress";

beforeEach(() => window.localStorage.clear());

it("başlangıçta hiçbir konu görülmüş sayılmaz", () => {
  expect(readSeen().size).toBe(0);
});

it("görülen konu saklanır, atlanan konu bekleyen kalır", () => {
  markSeen("chrome");
  markSeen("uzak");
  const seen = readSeen();
  expect([...seen].sort()).toEqual(["chrome", "uzak"]);
  expect(pendingIds(["chrome", "uzak", "kits"], seen)).toEqual(["kits"]);
});

it("bozuk kayıt sıfırlanmış sayılır", () => {
  window.localStorage.setItem(GUIDE_PROGRESS_KEY, "{bozuk");
  expect(readSeen().size).toBe(0);
  window.localStorage.setItem(GUIDE_PROGRESS_KEY, JSON.stringify({ version: 2, seen: ["x"] }));
  expect(readSeen().size).toBe(0);
});

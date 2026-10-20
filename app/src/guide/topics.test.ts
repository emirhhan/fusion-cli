import { readdirSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { expect, it } from "vitest";
import { GUIDE_GROUPS, GUIDE_TOPICS, ONBOARDING_TOPICS, guideImageUrl } from "./topics";

const GUIDE_DIR = resolve(__dirname, "../../public/guide");
const MAX_IMAGE_BYTES = 80_000;

it("konu kimlikleri benzersiz ve her konunun adımı var", () => {
  const ids = GUIDE_TOPICS.map((topic) => topic.id);
  expect(new Set(ids).size).toBe(ids.length);
  for (const topic of GUIDE_TOPICS) {
    expect(topic.steps.length, topic.id).toBeGreaterThan(1);
    expect(Object.keys(GUIDE_GROUPS)).toContain(topic.group);
    expect(topic.imageAlt.length, topic.id).toBeGreaterThan(10);
  }
});

it("her konunun görseli pakete girer ve küçüktür", () => {
  const files = new Set(readdirSync(GUIDE_DIR));
  for (const topic of GUIDE_TOPICS) {
    const name = `${topic.image}.webp`;
    expect(files.has(name), name).toBe(true);
    expect(statSync(resolve(GUIDE_DIR, name)).size, name).toBeLessThan(MAX_IMAGE_BYTES);
    expect(guideImageUrl(topic)).toBe(`/guide/${name}`);
  }
});

it("kurulum eğitimi Tailscale, Chrome eklentisi, Kits, ses ve sohbeti kapsar", () => {
  const ids = ONBOARDING_TOPICS.map((topic) => topic.id);
  expect(ids).toEqual(expect.arrayContaining(["uzak", "chrome", "kits", "ses", "sohbet", "proje"]));
});

it("Chrome konusu tek tık ve bir kerelik Erişilebilirlik iznini anlatır", () => {
  const chrome = GUIDE_TOPICS.find((topic) => topic.id === "chrome")!;
  const text = chrome.steps.join(" ");
  expect(text).toContain("Eklentiyi kur");
  expect(text).toContain("Erişilebilirlik");
});

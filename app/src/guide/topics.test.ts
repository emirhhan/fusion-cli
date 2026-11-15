import { readdirSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { expect, it } from "vitest";
import { APPROVAL_MODES } from "../screens/ApprovalModeMenu";
import { SETTINGS_SECTIONS } from "../settings/search";
import { GUIDE_GROUPS, GUIDE_TOPICS, ONBOARDING_TOPICS, guideImageUrl } from "./topics";

const GUIDE_DIR = resolve(__dirname, "../../public/guide");
const MAX_IMAGE_BYTES = 80_000;

it("konu kimlikleri benzersiz ve her konunun adımı var", () => {
  const ids = GUIDE_TOPICS.map((topic) => topic.id);
  expect(new Set(ids).size).toBe(ids.length);
  for (const topic of GUIDE_TOPICS) {
    expect(topic.steps.length, topic.id).toBeGreaterThan(1);
    expect(topic.steps.length, topic.id).toBeLessThanOrEqual(4);
    expect(Object.keys(GUIDE_GROUPS)).toContain(topic.group);
    if (topic.settingsSection) expect(SETTINGS_SECTIONS, topic.id).toContain(topic.settingsSection);
  }
});

it("görseli olan konunun görseli pakete girer ve küçüktür; kurulumdaki her konunun görseli vardır", () => {
  const files = new Set(readdirSync(GUIDE_DIR));
  for (const topic of GUIDE_TOPICS) {
    if (!topic.image) {
      expect(topic.inOnboarding, topic.id).toBe(false);
      expect(guideImageUrl(topic)).toBeNull();
      continue;
    }
    const name = `${topic.image}.webp`;
    expect(files.has(name), name).toBe(true);
    expect(statSync(resolve(GUIDE_DIR, name)).size, name).toBeLessThan(MAX_IMAGE_BYTES);
    expect(guideImageUrl(topic)).toBe(`/guide/${name}`);
    expect(topic.imageAlt?.length ?? 0, topic.id).toBeGreaterThan(10);
  }
});

// 0.7.19 (1 Kasım): "Nasıl yapılır" eski sürümden kalmıştı. Güncel görevlerin hepsi kapsanır.
it("0.7.19 görevlerini kapsar: izinler, bilgisayar kullanımı, oturum aktarma, Kits, alt ajanlar, beceriler, MCP, kancalar, /rewind, arka plan, uzaktan", () => {
  const metin = GUIDE_TOPICS.map((topic) => `${topic.title} ${topic.where} ${topic.steps.join(" ")}`).join(" ");
  for (const parca of ["Yeni sohbet", "Projeler", "Bash(npm test *)", "Ayarlar → Bu bilgisayar", "Web oturumları", "Kits", "/persona", "/subtask", "$ad", "MCP bağlantıları", "hooks", "/rewind", "/resume", "/bg", "/tasks", "Uzaktan Erişim"]) {
    expect(metin, parca).toContain(parca);
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

// Ölçüldü (29 Ekim, U6-28): izin konusu üç mod (Otomatik/Yalnız plan/Güvenli) anlatıyordu;
// menüde beş mod var ve adları farklı ("Manuel", "Plan", "Düzenlemeleri kabul et", "İzinleri atla").
it("izin konusu menüdeki bütün modları menüdeki adlarıyla anlatır", () => {
  const izin = GUIDE_TOPICS.find((topic) => topic.id === "izin")!;
  const metin = izin.steps.join(" ");
  for (const mod of APPROVAL_MODES) expect(metin, mod.label).toContain(mod.label);
  expect(metin).not.toContain("Güvenli modda");
});

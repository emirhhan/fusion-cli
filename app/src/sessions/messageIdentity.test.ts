import { expect, it } from "vitest";
import { migrateMessageIds } from "./messageIdentity";

it("legacy mesaj kimliği başına yeni satır eklendiğinde değişmez", () => {
  const messages = [{rol: "kullanici" as const, metin: "eski"}, {rol: "asistan" as const, metin: "yanıt"}];
  const first = migrateMessageIds(messages, "sohbet");
  const shifted = migrateMessageIds([{rol: "asistan", metin: "yeni"}, ...messages], "sohbet");
  expect(shifted[1].id).toBe(first[0].id);
  expect(shifted[2].id).toBe(first[1].id);
});
it("persistent id korunur, özdeş eski satırlar ayrı occurrence alır", () => {
  const messages = migrateMessageIds([{rol: "kullanici", metin: "aynı"}, {rol: "kullanici", metin: "aynı"}, {rol: "asistan", metin: "yanıt", id: "kalıcı"}], "sohbet");
  expect(messages[0].id).not.toBe(messages[1].id);
  expect(messages[2].id).toBe("kalıcı");
});

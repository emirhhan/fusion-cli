import { afterEach, describe, expect, it } from "vitest";
import {
  NOTIFICATION_STORAGE_KEY,
  VARSAYILAN_BILDIRIM_TERCIHLERI,
  getNotificationPreferences,
  parseNotificationPreferences,
  readNotificationPreferences,
  resetNotificationPreferencesCache,
  setNotificationPreference,
} from "./preferences";

afterEach(() => {
  localStorage.clear();
  resetNotificationPreferencesCache();
});

describe("bildirim tercihleri", () => {
  it("varsayılan: bildirimler açık, ses kapalı", () => {
    expect(VARSAYILAN_BILDIRIM_TERCIHLERI).toEqual({ turBitti: true, onayBekliyor: true, arkaPlanBitti: true, ses: false });
  });

  it("bozuk ya da eksik saklı değer varsayılana düşer, bilinen alanlar korunur", () => {
    expect(parseNotificationPreferences("{bozuk")).toEqual(VARSAYILAN_BILDIRIM_TERCIHLERI);
    expect(parseNotificationPreferences(JSON.stringify({ ses: true, turBitti: "evet" }))).toEqual({ ...VARSAYILAN_BILDIRIM_TERCIHLERI, ses: true });
  });

  it("değişiklik kalıcılaşır ve aynı değer okunur", () => {
    setNotificationPreference("onayBekliyor", false);
    expect(getNotificationPreferences().onayBekliyor).toBe(false);
    expect(JSON.parse(localStorage.getItem(NOTIFICATION_STORAGE_KEY) ?? "{}").onayBekliyor).toBe(false);
    resetNotificationPreferencesCache();
    expect(readNotificationPreferences().onayBekliyor).toBe(false);
  });

  it("depo erişimi düşerse varsayılanla sürer", () => {
    const bozuk = { getItem: () => { throw new Error("SecurityError"); } };
    expect(readNotificationPreferences(bozuk)).toEqual(VARSAYILAN_BILDIRIM_TERCIHLERI);
  });
});

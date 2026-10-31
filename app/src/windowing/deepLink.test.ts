import { describe, expect, it } from "vitest";
import { deepLinkFor, deepLinkRootDecision, parseDeepLink } from "./deepLink";

describe("derin bağlantı yükü (P-064)", () => {
  it("sohbet hedefini yalnız geçerli kimlikle kabul eder", () => {
    expect(parseDeepLink({ hedef: "sohbet", id: "abc-1_X" })).toEqual({ hedef: "sohbet", id: "abc-1_X" });
    expect(parseDeepLink({ hedef: "sohbet", id: "../x" })).toBeNull();
    expect(parseDeepLink({ hedef: "sohbet" })).toBeNull();
  });

  it("yeni sohbet kökü yalnız mutlak yol olabilir; yoksa null", () => {
    expect(parseDeepLink({ hedef: "yeni", kok: "/Users/a/proje" })).toEqual({ hedef: "yeni", kok: "/Users/a/proje" });
    expect(parseDeepLink({ hedef: "yeni", kok: "goreli/yol" })).toEqual({ hedef: "yeni", kok: null });
    expect(parseDeepLink({ hedef: "yeni" })).toEqual({ hedef: "yeni", kok: null });
  });

  it("ayarlar bölümü küçük harf kimliktir; bilinmeyen hedef ve bozuk yük yok sayılır", () => {
    expect(parseDeepLink({ hedef: "ayarlar", bolum: "bildirimler" })).toEqual({ hedef: "ayarlar", bolum: "bildirimler" });
    expect(parseDeepLink({ hedef: "ayarlar", bolum: "<script>" })).toEqual({ hedef: "ayarlar", bolum: null });
    expect(parseDeepLink({ hedef: "bilinmez" })).toBeNull();
    expect(parseDeepLink("fusion://sohbet/x")).toBeNull();
    expect(parseDeepLink(null)).toBeNull();
  });

  it("bağlantıdan gelen kök: çok geniş ve sistem klasörleri reddedilir, kalanı onaya gider", () => {
    for (const kok of ["/", "/Users", "/Users/ali", "/home/ali", "/etc", "/private/tmp/x", "/System/Library", "/Volumes", "/Users/ali/../x", "goreli"]) {
      expect(deepLinkRootDecision(kok), kok).toBe("reddet");
    }
    for (const kok of ["/Users/ali/proje", "/home/ali/kod/app", "/Volumes/Disk/proje", "/Users/ali/Masaüstü"]) {
      expect(deepLinkRootDecision(kok), kok).toBe("onayla");
    }
  });

  it("adres üretimi çözümlemeyle simetriktir", () => {
    expect(deepLinkFor({ hedef: "sohbet", id: "q1" })).toBe("fusion://sohbet/q1");
    expect(deepLinkFor({ hedef: "yeni", kok: "/Users/a/Masaüstü" })).toBe("fusion://yeni?kok=%2FUsers%2Fa%2FMasa%C3%BCst%C3%BC");
    expect(deepLinkFor({ hedef: "ayarlar", bolum: null })).toBe("fusion://ayarlar");
  });
});

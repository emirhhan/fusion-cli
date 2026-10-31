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

  it("Windows sürücü yolu kabul edilir; sürücü kökü, kullanıcı klasörü ve sistem klasörleri reddedilir", () => {
    // Ölçüldü (31 Ekim): `kok` yalnız `/` ile başlarsa kabul ediliyordu; Windows'ta
    // `fusion://yeni?kok=C%3A%5CUsers%5Cali%5Cproje` klasörsüz yeni sohbete düşüyordu.
    expect(parseDeepLink({ hedef: "yeni", kok: "C:\\Users\\ali\\proje" })).toEqual({ hedef: "yeni", kok: "C:\\Users\\ali\\proje" });
    for (const kok of ["C:\\", "C:\\Users\\ali", "c:/users/ali", "C:\\Windows\\System32", "C:\\Program Files\\X", "C:\\ProgramData\\x", "C:\\Users\\ali\\..\\x", "\\\\sunucu\\pay\\x", "C:\\proje"]) {
      expect(deepLinkRootDecision(kok), kok).toBe("reddet");
    }
    for (const kok of ["C:\\Users\\ali\\proje", "D:\\isler\\app", "c:/users/ali/kod"]) {
      expect(deepLinkRootDecision(kok), kok).toBe("onayla");
    }
  });

  it("adres üretimi çözümlemeyle simetriktir", () => {
    expect(deepLinkFor({ hedef: "sohbet", id: "q1" })).toBe("fusion://sohbet/q1");
    expect(deepLinkFor({ hedef: "yeni", kok: "/Users/a/Masaüstü" })).toBe("fusion://yeni?kok=%2FUsers%2Fa%2FMasa%C3%BCst%C3%BC");
    expect(deepLinkFor({ hedef: "ayarlar", bolum: null })).toBe("fusion://ayarlar");
  });
});

describe("fusion://ayarlar/<bölüm> hedefi", () => {
  it("tanınan her bölüm açılır (kisayollar dahil); bilinmeyen genel'e düşer", async () => {
    // Ölçüldü (31 Ekim): yalnız kisisellestirme ve bildirimler tanınıyordu; diğerleri Genel açıyordu.
    const { isSettingsSection } = await import("../settings/search");
    for (const bolum of ["kisayollar", "izinler", "uzak", "bildirimler"]) expect(isSettingsSection(bolum), bolum).toBe(true);
    expect(isSettingsSection("bilinmez")).toBe(false);
    expect(isSettingsSection(null)).toBe(false);
  });
});

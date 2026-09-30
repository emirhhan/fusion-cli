import { describe, expect, test } from "vitest";
import { adimOzeti, sureMetni, tokenMetni } from "./adimOzeti";

describe("adimOzeti", () => {
  test("araç türlerini ilk görülme sırasıyla sayar", () => {
    const ozet = adimOzeti([
      { metin: "", arac: "run_shell", durum: "ok" },
      { metin: "", arac: "glob", durum: "ok" },
      { metin: "", arac: "read_file", durum: "ok", ayrinti: "a.py" },
      { metin: "", arac: "read_file", durum: "ok", ayrinti: "b.py" },
      { metin: "", arac: "run_shell", durum: "ok" },
      { metin: "", arac: "search_code", durum: "ok" },
      { metin: "", arac: "todo_write", durum: "ok" },
    ]);
    expect(ozet).toBe("2 komut çalıştırıldı, dosyalar bulundu, 2 dosya okundu, kod arandı");
  });

  test("tek dosya okuması dosyanın adını yazar", () => {
    expect(adimOzeti([{ metin: "", arac: "read_file", durum: "ok", ayrinti: "Makefile" }])).toBe("Makefile okundu");
  });

  test("tarayıcı ve masaüstü araçları önekten tanınır", () => {
    expect(adimOzeti([
      { metin: "", arac: "chrome_click" },
      { metin: "", arac: "browser_read" },
      { metin: "", arac: "desktop_key" },
    ])).toBe("Tarayıcıda 2 işlem yapıldı, masaüstünde 1 işlem yapıldı");
  });
});

describe("sureMetni ve tokenMetni", () => {
  test.each([
    [0, "0 sn"], [42, "42 sn"], [554, "9 dk 14 sn"], [1313, "21 dk 53 sn"], [3720, "1 sa 2 dk"],
  ])("%i sn → %s", (saniye, beklenen) => {
    expect(sureMetni(saniye)).toBe(beklenen);
  });

  test.each([[850, "850 token"], [2034, "2,0 bin token"], [15_480, "15,5 bin token"]])(
    "%i → %s",
    (adet, beklenen) => {
      expect(tokenMetni(adet)).toBe(beklenen);
    },
  );
});

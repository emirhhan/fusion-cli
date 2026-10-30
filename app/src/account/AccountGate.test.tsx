import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { AccountGate } from "./AccountGate";
import { hesapBasHarfleri } from "./types";
import type { AccountController } from "./useAccount";

afterEach(cleanup);

function denetleyici(ekle: Partial<AccountController> = {}): AccountController {
  return {
    durum: { hesaplar: [], etkin: "", kurulum_gerekli: true },
    yukleniyor: false,
    hata: null,
    kurtarmaKodu: null,
    kayit: vi.fn(async () => null),
    giris: vi.fn(async () => false),
    cikis: vi.fn(async () => undefined),
    kurtar: vi.fn(async () => false),
    guncelle: vi.fn(async () => false),
    sil: vi.fn(async () => false),
    tazele: vi.fn(async () => undefined),
    ...ekle,
  };
}

describe("hesapBasHarfleri", () => {
  test("kullanıcı adından en çok iki baş harf üretir", () => {
    expect(hesapBasHarfleri({ kullanici_adi: "kullanici" })).toBe("K");
    expect(hesapBasHarfleri({ kullanici_adi: "kullanici yildiz" })).toBe("KY");
  });
});

describe("AccountGate", () => {
  test("hiç hesap yokken kayıt ekranıyla açılır", () => {
    render(<AccountGate account={denetleyici()} />);

    expect(screen.getByRole("heading", { name: "Kayıt Ol" })).toBeTruthy();
    // Kurulumda "zaten hesabım var" yolu yoktur: gidilecek hesap yok.
    expect(screen.queryByRole("button", { name: /giriş yap/i })).toBeNull();
  });

  test("hesap varken giriş ekranıyla açılır ve kurtarma yolu sunar", () => {
    render(
      <AccountGate
        account={denetleyici({
          durum: {
            hesaplar: [
              {
                kimlik: "1",
                kullanici_adi: "kullanici",
                eposta: "e@ornek.com",
                avatar: "",
                olusturuldu: 0,
              },
            ],
            etkin: "",
            kurulum_gerekli: false,
          },
        })}
      />,
    );

    expect(screen.getByRole("heading", { name: "Giriş Yap" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /şifremi unuttum/i })).toBeTruthy();
  });

  /* Ürünün açık sözü: sunucu yok. Kullanıcı bunu kurtarma kodunu kaydetmeden
     ÖNCE bilmeli, parolasını unuttuktan sonra değil. */
  test("verinin bu bilgisayarda kaldığını ekranda söyler", () => {
    render(<AccountGate account={denetleyici()} />);

    expect(screen.getByText(/yalnız bu bilgisayarda tutulur/i)).toBeTruthy();
  });

  test("kayıt bilgileri çekirdeğe olduğu gibi iletilir", async () => {
    const kayit = vi.fn(async () => null);
    render(<AccountGate account={denetleyici({ kayit })} />);

    fireEvent.change(screen.getByLabelText("Kullanıcı adınız"), { target: { value: "kullanici" } });
    fireEvent.change(screen.getByLabelText("E-posta adresiniz"), { target: { value: "e@ornek.com" } });
    fireEvent.change(screen.getByLabelText("Şifreniz"), { target: { value: "parola1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Kayıt Ol" }));

    await waitFor(() =>
      expect(kayit).toHaveBeenCalledWith({
        kullanici_adi: "kullanici",
        eposta: "e@ornek.com",
        parola: "parola1234",
        avatar: "",
      }),
    );
  });

  test("kurtarma kodu kopyalanmadan devam edilemez", async () => {
    const kayit = vi.fn(async () => ({
      hesap: {
        kimlik: "1",
        kullanici_adi: "kullanici",
        eposta: "e@ornek.com",
        avatar: "",
        olusturuldu: 0,
      },
      kurtarma_kodu: "ABCD-EFGH-JKMN-PQRS",
      devralinan_ayarlar: [],
    }));
    render(<AccountGate account={denetleyici({ kayit })} />);

    fireEvent.change(screen.getByLabelText("Kullanıcı adınız"), { target: { value: "kullanici" } });
    fireEvent.change(screen.getByLabelText("E-posta adresiniz"), { target: { value: "e@ornek.com" } });
    fireEvent.change(screen.getByLabelText("Şifreniz"), { target: { value: "parola1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Kayıt Ol" }));

    expect(await screen.findByText("ABCD-EFGH-JKMN-PQRS")).toBeTruthy();
    // Kod kaybolursa hesap da kaybolur; devam düğmesi kopyalanana kadar kapalı.
    expect(screen.getByRole("button", { name: /kaydettim/i }).hasAttribute("disabled")).toBe(true);
  });

  test("çekirdekten gelen hata olduğu gibi gösterilir", () => {
    render(<AccountGate account={denetleyici({ hata: "Kullanıcı adı zaten kullanılıyor." })} />);

    expect(screen.getByRole("alert").textContent).toBe("Kullanıcı adı zaten kullanılıyor.");
  });

  // Ölçüldü (29 Ekim, U5-29): pano yoksa ya da yazım reddedilirse Devam sonsuza dek kapalıydı.
  describe("kurtarma kodu ekranı pano başarısızken", () => {
    const kodlu = () => denetleyici({ kurtarmaKodu: "ABCD-EFGH-JKMN-PQRS" });
    afterEach(() => vi.unstubAllGlobals());

    test("pano reddederse elle kaydettim onayıyla devam edilir", async () => {
      vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn(async () => { throw new Error("izin yok"); }) } });
      render(<AccountGate account={kodlu()} />);
      const devam = screen.getByRole("button", { name: /kaydettim/i });
      expect(devam.hasAttribute("disabled")).toBe(true);

      fireEvent.click(screen.getByRole("button", { name: "Kopyala" }));
      fireEvent.click(await screen.findByLabelText("Kodu elle kaydettim"));

      expect(devam.hasAttribute("disabled")).toBe(false);
    });

    test("pano API'si yoksa da elle onay yolu açılır", async () => {
      vi.stubGlobal("navigator", {});
      render(<AccountGate account={kodlu()} />);

      fireEvent.click(screen.getByRole("button", { name: "Kopyala" }));
      fireEvent.click(await screen.findByLabelText("Kodu elle kaydettim"));

      expect(screen.getByRole("button", { name: /kaydettim/i }).hasAttribute("disabled")).toBe(false);
    });
  });
});

// Ölçüldü (30 Ekim): "Beni Hatırla" hiçbir yere iletilmeyen ölü kutuydu (U5-31); kip değişince eski hata görünüyor,
// parola alanlarında autocomplete yoktu (U5-35); emoji baş harf yarım vekil çifti üretiyordu (U5-36); "Bu hesaba geç"
// seçilen kimliği taşımıyordu (U5-32).
describe("AccountGate (30 Ekim)", () => {
  const giris = { durum: { hesaplar: [{ kimlik: "1", kullanici_adi: "k", eposta: "e@o.com", avatar: "", olusturuldu: 0 }], etkin: "", kurulum_gerekli: false } };

  test("var olmayan 'Beni Hatırla' vaadi yoktur", () => {
    render(<AccountGate account={denetleyici(giris)} />);
    expect(screen.queryByText(/beni hatırla/i)).toBeNull();
  });

  test("parola yöneticisi için autocomplete nitelikleri vardır", () => {
    render(<AccountGate account={denetleyici(giris)} />);
    expect(screen.getByLabelText("Şifreniz").getAttribute("autocomplete")).toBe("current-password");
    expect(screen.getByLabelText(/E-posta adresiniz veya/).getAttribute("autocomplete")).toBe("username");
  });

  test("kip değişince eski kipin hatası görünmez", () => {
    render(<AccountGate account={denetleyici({ ...giris, hata: "Giriş yapılamadı." })} />);
    expect(screen.getByRole("alert").textContent).toBe("Giriş yapılamadı.");
    fireEvent.click(screen.getByRole("button", { name: /şifremi unuttum/i }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("hesap değiştirirken önerilen kimlik giriş alanına gelir", () => {
    sessionStorage.setItem("fusion.hesap.giris-onerisi", "ikinci@o.com");
    render(<AccountGate account={denetleyici(giris)} />);
    expect((screen.getByLabelText(/E-posta adresiniz veya/) as HTMLInputElement).value).toBe("ikinci@o.com");
    expect(sessionStorage.getItem("fusion.hesap.giris-onerisi")).toBeNull();
  });

  test("emoji ile başlayan ad yarım vekil çifti üretmez", () => {
    expect(hesapBasHarfleri({ kullanici_adi: "🏍️ Moto" })).toBe("🏍M");
  });
});

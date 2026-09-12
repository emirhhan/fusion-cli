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
    expect(hesapBasHarfleri({ kullanici_adi: "emirhan" })).toBe("E");
    expect(hesapBasHarfleri({ kullanici_adi: "emirhan yildiz" })).toBe("EY");
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
                kullanici_adi: "emirhan",
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

    fireEvent.change(screen.getByLabelText("Kullanıcı adınız"), { target: { value: "emirhan" } });
    fireEvent.change(screen.getByLabelText("E-posta adresiniz"), { target: { value: "e@ornek.com" } });
    fireEvent.change(screen.getByLabelText("Şifreniz"), { target: { value: "parola1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Kayıt Ol" }));

    await waitFor(() =>
      expect(kayit).toHaveBeenCalledWith({
        kullanici_adi: "emirhan",
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
        kullanici_adi: "emirhan",
        eposta: "e@ornek.com",
        avatar: "",
        olusturuldu: 0,
      },
      kurtarma_kodu: "ABCD-EFGH-JKMN-PQRS",
      devralinan_ayarlar: [],
    }));
    render(<AccountGate account={denetleyici({ kayit })} />);

    fireEvent.change(screen.getByLabelText("Kullanıcı adınız"), { target: { value: "emirhan" } });
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
});

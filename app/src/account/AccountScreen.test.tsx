import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { AccountScreen } from "./AccountScreen";
import type { Hesap } from "./types";
import type { AccountController } from "./useAccount";

afterEach(cleanup);

const EMIRHAN: Hesap = {
  kimlik: "1",
  kullanici_adi: "emirhan",
  eposta: "e@ornek.com",
  avatar: "🏍️",
  olusturuldu: 0,
};
const IKINCI: Hesap = {
  kimlik: "2",
  kullanici_adi: "ikinci",
  eposta: "i@ornek.com",
  avatar: "",
  olusturuldu: 0,
};

function denetleyici(hesaplar: Hesap[], ekle: Partial<AccountController> = {}): AccountController {
  return {
    durum: { hesaplar, etkin: hesaplar[0]?.kimlik ?? "", kurulum_gerekli: false },
    yukleniyor: false,
    hata: null,
    kayit: vi.fn(async () => null),
    giris: vi.fn(async () => false),
    cikis: vi.fn(async () => undefined),
    kurtar: vi.fn(async () => false),
    guncelle: vi.fn(async () => true),
    sil: vi.fn(async () => false),
    tazele: vi.fn(async () => undefined),
    ...ekle,
  };
}

describe("AccountScreen", () => {
  test("etkin hesabın bilgilerini gösterir", () => {
    render(<AccountScreen account={denetleyici([EMIRHAN])} onClose={vi.fn()} />);

    // Ad hem profil başlığında hem silme onayında geçer; ikisi de beklenen.
    expect(screen.getAllByText("emirhan").length).toBeGreaterThan(0);
    expect(screen.getByText("e@ornek.com")).toBeTruthy();
    expect(screen.getByLabelText("Kullanıcı adı")).toHaveProperty("value", "emirhan");
  });

  test("profil değişikliği çekirdeğe iletilir", async () => {
    const guncelle = vi.fn(async () => true);
    render(<AccountScreen account={denetleyici([EMIRHAN], { guncelle })} onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Kullanıcı adı"), { target: { value: "emir" } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));

    expect(guncelle).toHaveBeenCalledWith(expect.objectContaining({ kullanici_adi: "emir" }));
  });

  test("tek hesap varken değiştirilecek hesap olmadığı söylenir", () => {
    render(<AccountScreen account={denetleyici([EMIRHAN])} onClose={vi.fn()} />);

    expect(screen.getByText(/başka hesap yok/i)).toBeTruthy();
  });

  test("diğer hesaplar listelenir", () => {
    render(<AccountScreen account={denetleyici([EMIRHAN, IKINCI])} onClose={vi.fn()} />);

    expect(screen.getByText("ikinci")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Bu hesaba geç" })).toBeTruthy();
  });

  /* Silme geri alınamaz. Tek tıkla silinebilen bir şey için bu onay ağır olurdu;
     geri getirilemeyen bir şey için değil. */
  test("silme, kullanıcı adı elle yazılana kadar kapalıdır", () => {
    const sil = vi.fn(async () => true);
    render(<AccountScreen account={denetleyici([EMIRHAN], { sil })} onClose={vi.fn()} />);

    const dugme = screen.getByRole("button", { name: /kalıcı olarak sil/i });
    expect(dugme.hasAttribute("disabled")).toBe(true);

    fireEvent.change(screen.getByLabelText(/onaylamak için/i), { target: { value: "yanlis" } });
    expect(dugme.hasAttribute("disabled")).toBe(true);

    fireEvent.change(screen.getByLabelText(/onaylamak için/i), { target: { value: "emirhan" } });
    expect(dugme.hasAttribute("disabled")).toBe(false);
  });

  test("silmenin neyi götürdüğünü açıkça yazar", () => {
    render(<AccountScreen account={denetleyici([EMIRHAN])} onClose={vi.fn()} />);

    expect(screen.getByText(/kalıcı olarak silinir/i)).toBeTruthy();
    expect(screen.getByText(/geri alınamaz/i)).toBeTruthy();
  });
});

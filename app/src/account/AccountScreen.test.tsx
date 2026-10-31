import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { AccountScreen } from "./AccountScreen";
import type { Hesap } from "./types";
import type { AccountController } from "./useAccount";

afterEach(cleanup);

const KULLANICI: Hesap = {
  kimlik: "1",
  kullanici_adi: "kullanici",
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
    cikis: vi.fn(async () => true),
    kurtar: vi.fn(async () => false),
    guncelle: vi.fn(async () => true),
    sil: vi.fn(async () => false),
    tazele: vi.fn(async () => undefined),
    ...ekle,
  };
}

describe("AccountScreen", () => {
  test("etkin hesabın bilgilerini gösterir", () => {
    render(<AccountScreen account={denetleyici([KULLANICI])} onClose={vi.fn()} />);

    // Profil özeti açık, düzenleme formu isteğe bağlıdır.
    expect(screen.getAllByText("kullanici").length).toBeGreaterThan(0);
    expect(screen.getByText("e@ornek.com")).toBeTruthy();
    fireEvent.click(screen.getByText("Profili düzenle"));
    expect(screen.getByLabelText("Kullanıcı adı")).toHaveProperty("value", "kullanici");
  });

  test("profil değişikliği çekirdeğe iletilir", async () => {
    const guncelle = vi.fn(async () => true);
    render(<AccountScreen account={denetleyici([KULLANICI], { guncelle })} onClose={vi.fn()} />);

    fireEvent.click(screen.getByText("Profili düzenle"));
    fireEvent.change(screen.getByLabelText("Kullanıcı adı"), { target: { value: "emir" } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));

    expect(guncelle).toHaveBeenCalledWith(expect.objectContaining({ kullanici_adi: "emir" }));
  });

  test("avatar seçimi düzenleme bölümü kapalıyken de kaydedilir", async () => {
    const guncelle = vi.fn(async () => true);
    render(<AccountScreen account={denetleyici([KULLANICI], { guncelle })} onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Avatarı değiştir" }));
    fireEvent.click(screen.getByRole("button", { name: "Avatar: 🚀" }));
    expect(guncelle).toHaveBeenCalledWith(expect.objectContaining({ avatar: "🚀" }));
  });

  test("tek hesap varken değiştirilecek hesap olmadığı söylenir", () => {
    render(<AccountScreen account={denetleyici([KULLANICI])} onClose={vi.fn()} />);

    fireEvent.click(screen.getByText("Hesap yönetimi"));
    expect(screen.getByText(/başka hesap yok/i)).toBeTruthy();
  });

  test("diğer hesaplar listelenir", () => {
    render(<AccountScreen account={denetleyici([KULLANICI, IKINCI])} onClose={vi.fn()} />);

    fireEvent.click(screen.getByText("Hesap yönetimi"));
    expect(screen.getByText("ikinci")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Bu hesaba geç" })).toBeTruthy();
  });

  /* Silme geri alınamaz. Tek tıkla silinebilen bir şey için bu onay ağır olurdu;
     geri getirilemeyen bir şey için değil. */
  test("silme, kullanıcı adı elle yazılana kadar kapalıdır", () => {
    const sil = vi.fn(async () => true);
    render(<AccountScreen account={denetleyici([KULLANICI], { sil })} onClose={vi.fn()} />);

    fireEvent.click(screen.getByText("Hesabı sil"));
    const dugme = screen.getByRole("button", { name: /kalıcı olarak sil/i });
    expect(dugme.hasAttribute("disabled")).toBe(true);

    fireEvent.change(screen.getByLabelText(/onaylamak için/i), { target: { value: "yanlis" } });
    expect(dugme.hasAttribute("disabled")).toBe(true);

    fireEvent.change(screen.getByLabelText(/onaylamak için/i), { target: { value: "kullanici" } });
    // Kullanıcı adı tek başına yetmez: parola da gerekir (U5-33).
    expect(dugme.hasAttribute("disabled")).toBe(true);
    fireEvent.change(screen.getByLabelText("Parolan"), { target: { value: "parola1234" } });
    expect(dugme.hasAttribute("disabled")).toBe(false);
  });

  test("silme isteği parolayı taşır; parola alanı gizlidir (U5-33)", () => {
    const sil = vi.fn(async () => false);
    render(<AccountScreen account={denetleyici([KULLANICI], { sil })} onClose={vi.fn()} />);

    fireEvent.click(screen.getByText("Hesabı sil"));
    expect(screen.getByLabelText("Parolan")).toHaveProperty("type", "password");
    fireEvent.change(screen.getByLabelText(/onaylamak için/i), { target: { value: "kullanici" } });
    fireEvent.change(screen.getByLabelText("Parolan"), { target: { value: "parola1234" } });
    fireEvent.click(screen.getByRole("button", { name: /kalıcı olarak sil/i }));
    expect(sil).toHaveBeenCalledWith(KULLANICI.kimlik, { parola: "parola1234" });
  });

  test("parolasını unutan kurtarma koduyla silebilir (U5-33)", () => {
    const sil = vi.fn(async () => false);
    render(<AccountScreen account={denetleyici([KULLANICI], { sil })} onClose={vi.fn()} />);

    fireEvent.click(screen.getByText("Hesabı sil"));
    fireEvent.click(screen.getByRole("button", { name: /Parolamı unuttum/ }));
    fireEvent.change(screen.getByLabelText(/onaylamak için/i), { target: { value: "kullanici" } });
    fireEvent.change(screen.getByLabelText("Kurtarma kodun"), { target: { value: " ABCD-EFGH " } });
    fireEvent.click(screen.getByRole("button", { name: /kalıcı olarak sil/i }));
    expect(sil).toHaveBeenCalledWith(KULLANICI.kimlik, { kurtarma_kodu: "ABCD-EFGH" });
  });

  test("silmenin neyi götürdüğünü açıkça yazar", () => {
    render(<AccountScreen account={denetleyici([KULLANICI])} onClose={vi.fn()} />);

    fireEvent.click(screen.getByText("Hesabı sil"));
    expect(screen.getByText(/kalıcı olarak silinir/i)).toBeTruthy();
    expect(screen.getByText(/geri alınamaz/i)).toBeTruthy();
  });
});

// Ölçüldü (31 Ekim, P-066): Hesabım ekranında sağlayıcı oturumu (ChatGPT/Claude web) görünmüyordu;
// "sağlayıcıyla giriş" yalnız Kontrol Paneli'nin derinindeydi.
describe("AccountScreen sağlayıcı hesapları", () => {
  const istemci = () => ({
    request: vi.fn(async (name: string) =>
      name === "web.saglayicilar"
        ? { ok: true, saglayicilar: [
            { id: "chatgpt", kart_id: "chatgpt", ad: "ChatGPT", hesap: "main", bagli: true, profil_var: true },
            { id: "claude", kart_id: "claude", ad: "Claude", hesap: "main", bagli: false, profil_var: false },
          ] }
        : { ok: true, kullanim: { cagri: 0, toplam_token: 0 } },
    ),
  }) as unknown as import("../protocol/client").ProtocolClient;

  test("bağlı/bağlı değil durumunu gösterir ve girişi Kontrol Paneli'ne yönlendirir", async () => {
    const onOpenProviders = vi.fn();
    render(<AccountScreen account={denetleyici([KULLANICI])} client={istemci()} onClose={vi.fn()} onOpenProviders={onOpenProviders} />);
    expect(await screen.findByText("ChatGPT")).toBeTruthy();
    expect(screen.getByText("Bağlı")).toBeTruthy();
    expect(screen.getByText("Giriş yapılmadı")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Sağlayıcıyla giriş yap" }));
    expect(onOpenProviders).toHaveBeenCalledWith("claude");
  });

  test("yönlendirme verilmezse bölüm çizilmez ve sağlayıcı listesi okunmaz", () => {
    const client = istemci();
    render(<AccountScreen account={denetleyici([KULLANICI])} client={client} onClose={vi.fn()} />);
    expect(screen.queryByText("Sağlayıcı hesapları")).toBeNull();
    expect((client.request as ReturnType<typeof vi.fn>).mock.calls.some(([name]) => name === "web.saglayicilar")).toBe(false);
  });
});

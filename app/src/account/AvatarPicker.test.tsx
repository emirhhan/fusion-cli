import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { AvatarPicker, AvatarView, gorselAvatarMi } from "./AvatarPicker";
import { FUSION_AVATARLARI, VARSAYILAN_FUSION_AVATARI } from "./fusionAvatars";

afterEach(cleanup);

describe("gorselAvatarMi", () => {
  test("yol ayıracı taşıyan avatar dosyadır, taşımayan emojidir", () => {
    expect(gorselAvatarMi("/Users/kullanici/.config/fusion-cli/accounts/1/avatar.png")).toBe(true);
    expect(gorselAvatarMi("C:\\\\Users\\\\kullanici\\\\avatar.png")).toBe(true);
    expect(gorselAvatarMi("🏍️")).toBe(false);
    expect(gorselAvatarMi("")).toBe(false);
  });
});

describe("AvatarView", () => {
  test("hazır Fusion avatarını görsel olarak gösterir", () => {
    const { container } = render(<AvatarView avatar="fusion:emre" kullaniciAdi="kullanici" />);

    expect(container.querySelector("img")?.getAttribute("data-avatar")).toBe("emre");
    expect(container.querySelector("img")?.getAttribute("src")).toMatch(/emre\.svg/);
  });

  test("eski emoji seçimi olan hesapta varsayılan avatar gösterilir (geri uyum)", () => {
    const { container } = render(<AvatarView avatar="🏍️" kullaniciAdi="kullanici" />);

    expect(container.textContent).not.toContain("🏍️");
    expect(container.querySelector("img")?.getAttribute("data-avatar")).toBe(VARSAYILAN_FUSION_AVATARI.id);
  });

  test("tanınmayan hazır avatar kimliği varsayılana düşer", () => {
    const { container } = render(<AvatarView avatar="fusion:silinmis" kullaniciAdi="kullanici" />);

    expect(container.querySelector("img")?.getAttribute("data-avatar")).toBe(VARSAYILAN_FUSION_AVATARI.id);
  });

  test("avatar yoksa baş harfe düşer", () => {
    const { container } = render(<AvatarView avatar="" kullaniciAdi="kullanici" />);

    expect(container.textContent).toBe("K");
  });

  /* Kabuk yokken yerel dosya adresi üretilemez. Kırık bir görsel yerine baş
     harf göstermek, boş bir kutudan iyidir. */
  test("kabuk yokken dosya avatarı baş harfe düşer, kırık görsel basmaz", () => {
    const { container } = render(<AvatarView avatar="/tmp/avatar.png" kullaniciAdi="kullanici" />);

    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toBe("K");
  });
});

describe("AvatarPicker", () => {
  const varsayilan = {
    avatar: "",
    kullaniciAdi: "kullanici",
    onSelect: vi.fn(),
    onUpload: vi.fn(async () => null),
  };

  test("kapalıyken seçenek çizilmez", () => {
    render(<AvatarPicker {...varsayilan} />);

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("Değiştir 7 Fusion avatarlı seçiciyi açar; emoji sunulmaz", () => {
    render(<AvatarPicker {...varsayilan} />);

    fireEvent.click(screen.getByRole("button", { name: "Avatarı değiştir" }));

    const dialog = screen.getByRole("dialog", { name: "Avatar seçenekleri" });
    const secenekler = Array.from(dialog.querySelectorAll(".account-avatar__option"));
    expect(secenekler).toHaveLength(7);
    expect(secenekler.map((item) => item.getAttribute("aria-label"))).toEqual(FUSION_AVATARLARI.map((item) => `Avatar: ${item.ad}`));
    expect(dialog.textContent).not.toMatch(/\p{Extended_Pictographic}/u);
  });

  test("seçili hazır avatar işaretli görünür", () => {
    render(<AvatarPicker {...varsayilan} avatar="fusion:elif" />);

    fireEvent.click(screen.getByRole("button", { name: "Avatarı değiştir" }));

    expect(screen.getByRole("button", { name: "Avatar: Elif" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Avatar: Deniz" }).getAttribute("aria-pressed")).toBe("false");
  });

  test("hazır avatar seçimi fusion:<kimlik> olarak iletilir ve seçici kapanır", () => {
    const onSelect = vi.fn();
    render(<AvatarPicker {...varsayilan} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: "Avatarı değiştir" }));
    fireEvent.click(screen.getByRole("button", { name: "Avatar: Kerem" }));

    expect(onSelect).toHaveBeenCalledWith("fusion:kerem");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("görsel yükleme kaydedilen yolu seçim olarak iletir", async () => {
    const onSelect = vi.fn();
    const onUpload = vi.fn(async () => "/hesap/avatar.png");
    render(<AvatarPicker {...varsayilan} onSelect={onSelect} onUpload={onUpload} />);

    fireEvent.click(screen.getByRole("button", { name: "Avatarı değiştir" }));
    fireEvent.click(screen.getByRole("button", { name: "Görsel yükle" }));

    await waitFor(() => expect(onSelect).toHaveBeenCalledWith("/hesap/avatar.png"));
  });

  test("yükleme iptal edilirse seçim değişmez", async () => {
    const onSelect = vi.fn();
    render(<AvatarPicker {...varsayilan} onSelect={onSelect} onUpload={vi.fn(async () => null)} />);

    fireEvent.click(screen.getByRole("button", { name: "Avatarı değiştir" }));
    fireEvent.click(screen.getByRole("button", { name: "Görsel yükle" }));

    await waitFor(() => expect(screen.getByRole("dialog")).toBeTruthy());
    expect(onSelect).not.toHaveBeenCalled();
  });

  test("avatar varsa kaldırma yolu sunulur", () => {
    const onSelect = vi.fn();
    render(<AvatarPicker {...varsayilan} avatar="🏍️" onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: "Avatarı değiştir" }));
    fireEvent.click(screen.getByRole("button", { name: "Kaldır" }));

    expect(onSelect).toHaveBeenCalledWith("");
  });
});

// Ölçüldü (30 Ekim): menü Escape/dış tıklamayla kapanmıyor, tetikleyicide aria-expanded yok, yükleme hatası
// işlenmemiş reddedilmeydi (U5-34).
describe("AvatarPicker erişilebilirlik ve hata (30 Ekim)", () => {
  const props = { avatar: "", kullaniciAdi: "kullanici", onSelect: vi.fn(), onUpload: vi.fn(async () => null) };

  test("tetikleyici durumu bildirir, Escape menüyü kapatıp odağı geri verir", () => {
    render(<AvatarPicker {...props} />);
    const tetikleyici = screen.getByRole("button", { name: "Avatarı değiştir" });
    expect(tetikleyici.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(tetikleyici);
    expect(tetikleyici.getAttribute("aria-expanded")).toBe("true");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(tetikleyici);
  });

  test("dışarı tıklayınca menü kapanır", () => {
    render(<AvatarPicker {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Avatarı değiştir" }));
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("yükleme hatası kullanıcıya gösterilir", async () => {
    render(<AvatarPicker {...props} onUpload={vi.fn(async () => { throw new Error("kopyalanamadı"); })} />);
    fireEvent.click(screen.getByRole("button", { name: "Avatarı değiştir" }));
    fireEvent.click(screen.getByRole("button", { name: "Görsel yükle" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
  });

  test("yükleme işleyicisi verilmezse 'Görsel yükle' düğmesi çizilmez", () => {
    render(<AvatarPicker avatar="" kullaniciAdi="k" onSelect={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Avatarı değiştir" }));
    expect(screen.queryByRole("button", { name: "Görsel yükle" })).toBeNull();
  });
});

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { AvatarPicker, AvatarView, gorselAvatarMi } from "./AvatarPicker";

afterEach(cleanup);

describe("gorselAvatarMi", () => {
  test("yol ayıracı taşıyan avatar dosyadır, taşımayan emojidir", () => {
    expect(gorselAvatarMi("/Users/emirhan/.config/fusion-cli/accounts/1/avatar.png")).toBe(true);
    expect(gorselAvatarMi("C:\\\\Users\\\\emirhan\\\\avatar.png")).toBe(true);
    expect(gorselAvatarMi("🏍️")).toBe(false);
    expect(gorselAvatarMi("")).toBe(false);
  });
});

describe("AvatarView", () => {
  test("emoji avatarı olduğu gibi gösterir", () => {
    const { container } = render(<AvatarView avatar="🏍️" kullaniciAdi="emirhan" />);

    expect(container.textContent).toBe("🏍️");
  });

  test("avatar yoksa baş harfe düşer", () => {
    const { container } = render(<AvatarView avatar="" kullaniciAdi="emirhan" />);

    expect(container.textContent).toBe("E");
  });

  /* Kabuk yokken yerel dosya adresi üretilemez. Kırık bir görsel yerine baş
     harf göstermek, boş bir kutudan iyidir. */
  test("kabuk yokken dosya avatarı baş harfe düşer, kırık görsel basmaz", () => {
    const { container } = render(<AvatarView avatar="/tmp/avatar.png" kullaniciAdi="emirhan" />);

    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toBe("E");
  });
});

describe("AvatarPicker", () => {
  const varsayilan = {
    avatar: "",
    kullaniciAdi: "emirhan",
    onSelect: vi.fn(),
    onUpload: vi.fn(async () => null),
  };

  test("kapalıyken seçenek çizilmez", () => {
    render(<AvatarPicker {...varsayilan} />);

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("avatara tıklayınca emoji ızgarası açılır", () => {
    render(<AvatarPicker {...varsayilan} />);

    fireEvent.click(screen.getByRole("button", { name: "Avatarı değiştir" }));

    expect(screen.getByRole("dialog", { name: "Avatar seçenekleri" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Avatar: 🏍️" })).toBeTruthy();
  });

  test("emoji seçimi iletilir ve seçici kapanır", () => {
    const onSelect = vi.fn();
    render(<AvatarPicker {...varsayilan} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: "Avatarı değiştir" }));
    fireEvent.click(screen.getByRole("button", { name: "Avatar: 🚀" }));

    expect(onSelect).toHaveBeenCalledWith("🚀");
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

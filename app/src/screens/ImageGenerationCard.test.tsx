import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Conversation, type Mesaj } from "./Conversation";
import { ImageGenerationCard } from "./ImageGenerationCard";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("ImageGenerationCard", () => {
  it("oluşturuluyor durumunu, istemi ve istenen oranı gösterir", () => {
    const { container } = render(<ImageGenerationCard aspect="16:9" prompt="gün batımında bir dağ evi" />);
    const status = screen.getByRole("status", { name: "Görsel oluşturuluyor" });
    expect(status.getAttribute("aria-busy")).toBe("true");
    expect(screen.getByText("gün batımında bir dağ evi")).toBeTruthy();
    expect((container.querySelector(".image-generation__canvas") as HTMLElement).style.aspectRatio).toBe("16 / 9");
  });

  it("geçersiz oranda 1:1'e düşer ve geçen süreyi saniye saniye sayar", () => {
    vi.useFakeTimers();
    const { container } = render(<ImageGenerationCard aspect="0:9" prompt="" />);
    expect((container.querySelector(".image-generation__canvas") as HTMLElement).style.aspectRatio).toBe("1 / 1");
    expect(screen.getByText("Başlıyor")).toBeTruthy();
    act(() => { vi.advanceTimersByTime(3200); });
    expect(screen.getByText("3 sn")).toBeTruthy();
  });
});

describe("Conversation — /görsel çalışırken kart", () => {
  const user = (metin: string): Mesaj => ({ id: "u1", rol: "kullanici", metin });

  it("son istek /görsel, cevap yok ve görev sürüyorsa kartı gösterir", () => {
    render(<Conversation mesajlar={[user("/görsel mavi kuş --oran 9:16")]} running />);
    expect(screen.getByRole("status", { name: "Görsel oluşturuluyor" })).toBeTruthy();
    expect(screen.getByText("mavi kuş")).toBeTruthy();
  });

  it("cevap gelince, görev bitince ya da normal mesajda kart yoktur", () => {
    const { rerender } = render(
      <Conversation mesajlar={[user("/görsel mavi kuş"), { id: "a1", rol: "asistan", metin: "hazır" }]} running />,
    );
    expect(screen.queryByRole("status", { name: "Görsel oluşturuluyor" })).toBeNull();
    rerender(<Conversation mesajlar={[user("/görsel mavi kuş")]} running={false} />);
    expect(screen.queryByRole("status", { name: "Görsel oluşturuluyor" })).toBeNull();
    rerender(<Conversation mesajlar={[user("merhaba")]} running />);
    expect(screen.queryByRole("status", { name: "Görsel oluşturuluyor" })).toBeNull();
  });

  it("eski bir /görsel isteğinden sonra yeni normal mesajda kart çıkmaz", () => {
    render(
      <Conversation
        mesajlar={[user("/görsel kedi"), { id: "a1", rol: "asistan", metin: "x" }, { id: "u2", rol: "kullanici", metin: "teşekkürler" }]}
        running
      />,
    );
    expect(screen.queryByRole("status", { name: "Görsel oluşturuluyor" })).toBeNull();
  });
});

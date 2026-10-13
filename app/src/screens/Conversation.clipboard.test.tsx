import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Conversation } from "./Conversation";

const originalClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");
afterEach(() => {
  cleanup();
  if (originalClipboard) Object.defineProperty(navigator, "clipboard", originalClipboard);
  else Reflect.deleteProperty(navigator, "clipboard");
});

describe("Yanıt kopyalama makbuzu", () => {
  it("kopyalama reddedilince nedeni görünür olur", async () => {
    const failed = Promise.reject(new Error("Pano izni reddedildi."));
    // Mevcut ürün promise'i işlemiyor; fixture unhandled rejection üretmeden görünür sonucu ölçer.
    void failed.catch(() => undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn(() => failed) } });
    render(<Conversation mesajlar={[{ id: "answer-a", rol: "asistan", metin: "Sonuç" }]} />);
    fireEvent.click(screen.getByRole("button", { name: "Yanıtı kopyala" }));
    expect(await screen.findByText(/Pano izni reddedildi/)).toBeTruthy();
  });
  it("aynı mesajın bekleyen kopyalamasını ikinci kez başlatmaz", () => {
    const writeText = vi.fn(() => new Promise<void>(() => undefined));
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(<Conversation mesajlar={[{ id: "answer-a", rol: "asistan", metin: "Sonuç" }]} />);
    const button = screen.getByRole("button", { name: "Yanıtı kopyala" });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(writeText).toHaveBeenCalledTimes(1);
  });
  it("geçmiş prepend sonrasında pending makbuz doğru message id üzerinde kalır", async () => {
    let resolveCopy!: () => void;
    const writeText = vi.fn(() => new Promise<void>((resolve) => { resolveCopy = resolve; }));
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const original = { id: "answer-a", rol: "asistan" as const, metin: "Yeni sonuç" };
    const { rerender } = render(<Conversation mesajlar={[original]} />);
    fireEvent.click(screen.getByRole("button", { name: "Yanıtı kopyala" }));
    rerender(<Conversation mesajlar={[{ id: "history-b", rol: "asistan", metin: "Eski sonuç" }, original]} />);
    await act(async () => resolveCopy());
    const articles = screen.getAllByRole("article", { name: "Fusion yanıtı" });
    expect(within(articles[1]).getByText("Kopyalandı")).toBeTruthy();
    expect(within(articles[0]).queryByText("Kopyalandı")).toBeNull();
  });
  it("clipboard başarıyla çözülünce görünür başarı verir", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(<Conversation mesajlar={[{ id: "answer-a", rol: "asistan", metin: "Sonuç" }]} />);
    fireEvent.click(screen.getByRole("button", { name: "Yanıtı kopyala" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("Sonuç"));
    expect(await screen.findByText("Kopyalandı")).toBeTruthy();
  });
  it("clipboard yoksa manuel kopyalama yönlendirmesi verir", () => {
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined });
    render(<Conversation mesajlar={[{ id: "answer-a", rol: "asistan", metin: "Sonuç" }]} />);
    fireEvent.click(screen.getByRole("button", { name: "Yanıtı kopyala" }));
    expect(screen.getByText(/manuel.*kopyala|seç.*kopyala/i)).toBeTruthy();
  });
});

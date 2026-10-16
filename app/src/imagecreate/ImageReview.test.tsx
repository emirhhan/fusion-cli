import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ImageReview } from "./ImageReview";
afterEach(() => { cleanup(); vi.restoreAllMocks(); localStorage.clear(); });
const image = { yol: "/gallery/a.png", istem: "İlk", saglayici: "Test", genislik: 32, yukseklik: 32 };
it("yerel görsel notu aynı konuşma/dosya için yeniden açılır ve karşılaştırma ayrı seçilir", () => {
  const compare = vi.fn();
  const props = { image, images: [image, { ...image, yol: "/gallery/b.png", istem: "İkinci" }], scope: "conversation", comparison: "", onCompare: compare };
  render(<ImageReview {...props} />);
  fireEvent.change(screen.getByLabelText("Görsel notu"), { target: { value: "Kenar boşluğunu azalt." } });
  fireEvent.change(screen.getByLabelText("Karşılaştırılacak görsel"), { target: { value: "/gallery/b.png" } });
  expect(compare).toHaveBeenCalledWith("/gallery/b.png");
  cleanup();
  render(<ImageReview {...props} />);
  expect((screen.getByLabelText("Görsel notu") as HTMLTextAreaElement).value).toBe("Kenar boşluğunu azalt.");
});
it("depolama hatası notu silmez veya kaydedildi diye göstermez", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
  const drafts = new Map<string, string>();
  const props = { image, images: [image], scope: "conversation", comparison: "", onCompare: vi.fn(), drafts };
  render(<ImageReview {...props} />);
  fireEvent.change(screen.getByLabelText("Görsel notu"), { target: { value: "Saklanamayan taslak" } });
  expect((screen.getByLabelText("Görsel notu") as HTMLTextAreaElement).value).toBe("Saklanamayan taslak");
  expect(screen.getByRole("alert").textContent).toContain("kaydedilemedi");
  cleanup();
  render(<ImageReview {...props} />);
  expect((screen.getByLabelText("Görsel notu") as HTMLTextAreaElement).value).toBe("Saklanamayan taslak");
  expect(screen.getByRole("button", { name: "Notu indir" })).toBeTruthy();
});

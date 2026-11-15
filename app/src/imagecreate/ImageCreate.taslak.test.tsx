import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ImageCreate } from "./ImageCreate";

afterEach(cleanup);

function istemci(olustur: (data: Record<string, unknown>) => Promise<Record<string, unknown>>) {
  return {
    request: vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "gorsel.saglayicilar") {
        return { ok: true, secenekler: [{ deger: "gemini_web/main", etiket: "Gemini", referans: true }] };
      }
      if (name === "gorsel.galeri") return { ok: true, dosyalar: [] };
      if (name === "gorsel.akislar") return { ok: true, akislar: [] };
      return olustur(data);
    }),
  };
}

describe("ImageCreate — üretim sürerken yazılan taslak", () => {
  it("çalışan işin girdisi değişmez, yeni taslak sonuç gelince silinmez", async () => {
    let bitir: (sonuc: Record<string, unknown>) => void = () => {};
    const olustur = vi.fn(() => new Promise<Record<string, unknown>>((coz) => { bitir = coz; }));
    render(<ImageCreate client={istemci(olustur)} toUrl={(yol) => `asset://${yol}`} chooseSavePath={vi.fn()} />);
    await screen.findByRole("option", { name: "Gemini" });
    const kutu = screen.getByLabelText("Nasıl bir görsel istiyorsun?") as HTMLTextAreaElement;
    fireEvent.change(kutu, { target: { value: "dağ" } });
    fireEvent.click(screen.getByRole("button", { name: "Görsel oluştur" }));
    await waitFor(() => expect(olustur).toHaveBeenCalledTimes(1));

    // Üretim sürerken kullanıcı bir sonraki istemi yazmaya başlar.
    fireEvent.change(kutu, { target: { value: "deniz" } });
    bitir({ ok: true, dosyalar: [{ yol: "/veri/galeri/d.jpg" }] });
    await screen.findByRole("img", { name: "dağ" });

    expect(olustur).toHaveBeenCalledWith(expect.objectContaining({ istem: "dağ" }));
    expect(kutu.value).toBe("deniz");
  });

  it("iş akışı kipinde de sürerken düzenlenen metin düğümü korunur", async () => {
    let bitir: (sonuc: Record<string, unknown>) => void = () => {};
    const olustur = vi.fn(() => new Promise<Record<string, unknown>>((coz) => { bitir = coz; }));
    render(<ImageCreate client={istemci(olustur)} toUrl={(yol) => `asset://${yol}`} chooseSavePath={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
    await screen.findAllByRole("option", { name: "Gemini" });
    const kutu = screen.getByLabelText("Metin istemi") as HTMLTextAreaElement;
    fireEvent.change(kutu, { target: { value: "kask" } });
    fireEvent.click(screen.getByRole("button", { name: "Çalıştır" }));
    await waitFor(() => expect(olustur).toHaveBeenCalledTimes(1));

    fireEvent.change(kutu, { target: { value: "eldiven" } });
    bitir({ ok: true, dosyalar: [{ yol: "/veri/galeri/k.jpg" }] });
    await screen.findByRole("img", { name: "kask" });

    expect(olustur).toHaveBeenCalledWith(expect.objectContaining({ istem: "kask" }));
    expect((screen.getByLabelText("Metin istemi") as HTMLTextAreaElement).value).toBe("eldiven");
  });
});

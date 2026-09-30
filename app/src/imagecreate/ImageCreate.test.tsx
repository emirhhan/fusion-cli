import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ImageCreate } from "./ImageCreate";

afterEach(cleanup);

function istemci(olustur: (data: Record<string, unknown>) => Promise<Record<string, unknown>>) {
  return {
    request: vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "gorsel.saglayicilar") {
        return {
          ok: true,
          secenekler: [
            { deger: "nvidia_nim/black-forest-labs/flux.1-dev", etiket: "FLUX.1-dev (NVIDIA NIM)", referans: false },
            { deger: "gemini_web/main", etiket: "Gemini", referans: true },
          ],
        };
      }
      if (name === "gorsel.galeri") return { ok: true, dosyalar: [] };
      if (name === "gorsel.akislar") return { ok: true, akislar: [] };
      if (name === "gorsel.kaydet") return { ok: true };
      if (name === "gorsel.akis.kaydet") return { ok: true, id: "akis-1" };
      return olustur(data);
    }),
  };
}

describe("ImageCreate — düğümlü akış", () => {
  it("basit modda istemi alır ve sonucu iş akışında sürdürür", async () => {
    const client = istemci(async () => ({ ok: true, dosyalar: [{ yol: "/veri/galeri/a.jpg" }] }));
    render(<ImageCreate client={client} toUrl={(yol) => `asset://${yol}`} chooseSavePath={vi.fn()} />);
    await screen.findByRole("option", { name: "Gemini" });
    fireEvent.change(screen.getByLabelText("Nasıl bir görsel istiyorsun?"), { target: { value: "kask" } });
    fireEvent.click(screen.getByRole("button", { name: "Görsel oluştur" }));
    await screen.findByRole("img", { name: "kask" });
    fireEvent.click(screen.getByRole("button", { name: "Varyasyonla devam et" }));
    expect(screen.getByRole("region", { name: "Görsel iş akışı tuvali" })).toBeTruthy();
    expect(screen.getByText("Varyasyon düğümü eklendi. Talimatı ve sağlayıcıyı kontrol edip akışı çalıştır.")).toBeTruthy();
  });

  it("galeriden düzenleme dalı açınca bağımsız metin girdisi ister", async () => {
    const client = istemci(async () => ({ ok: true, dosyalar: [{ yol: "/veri/galeri/a.jpg" }] }));
    render(<ImageCreate client={client} toUrl={(yol) => `asset://${yol}`} chooseSavePath={vi.fn()} />);
    await screen.findByRole("option", { name: "Gemini" });
    fireEvent.change(screen.getByLabelText("Nasıl bir görsel istiyorsun?"), { target: { value: "kask" } });
    fireEvent.click(screen.getByRole("button", { name: "Görsel oluştur" }));
    await screen.findByRole("img", { name: "kask" });
    fireEvent.click(screen.getByRole("button", { name: "Düzenleyerek devam et" }));
    const metinler = screen.getAllByLabelText("Metin istemi") as HTMLTextAreaElement[];
    expect(metinler).toHaveLength(2);
    // Basit istem iş akışına taşınmaz; düzenleme için ayrı, boş bir talimat açılır.
    expect(metinler[0].value).toBe("");
    expect(metinler[1].value).toBe("");
    fireEvent.change(metinler[1], { target: { value: "arka planı mavi yap" } });
    fireEvent.click(screen.getByRole("button", { name: "Çalıştır" }));
    await waitFor(() => expect(client.request.mock.calls.some(([name, data]) =>
      name === "gorsel.olustur" && data.islem === "duzenle" && data.referans === "/veri/galeri/a.jpg",
    )).toBe(true));
  });

  it("basit mod, yarım bırakılmış iş akışından bağımsız görsel üretir", async () => {
    const client = istemci(async () => ({ ok: true, dosyalar: [{ yol: "/veri/galeri/a.jpg" }] }));
    render(<ImageCreate client={client} toUrl={(yol) => `asset://${yol}`} chooseSavePath={vi.fn()} />);
    await screen.findByRole("option", { name: "Gemini" });
    fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
    fireEvent.click(screen.getByRole("button", { name: "+ Varyasyon" }));
    fireEvent.click(screen.getByRole("button", { name: "Basit oluştur" }));
    fireEvent.change(screen.getByLabelText("Nasıl bir görsel istiyorsun?"), { target: { value: "kask" } });
    fireEvent.click(screen.getByRole("button", { name: "Görsel oluştur" }));

    await screen.findByRole("img", { name: "kask" });
    fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
    expect(screen.getByRole("button", { name: "Varyasyon düğümünü sil" })).toBeTruthy();
  });

  it("başlangıç akışını çalıştırır; sonuç galeride kalır ve diske inmez", async () => {
    const client = istemci(async () => ({
      ok: true, saglayici: "FLUX.1-dev",
      dosyalar: [{ yol: "/veri/galeri/a.jpg", genislik: 1024, yukseklik: 1024 }],
    }));
    render(<ImageCreate client={client} toUrl={(yol) => `asset://${yol}`} chooseSavePath={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));

    await screen.findAllByRole("option", { name: "FLUX.1-dev (NVIDIA NIM)" });
    fireEvent.change(screen.getByLabelText("Metin istemi"), { target: { value: "kırmızı kask" } });
    fireEvent.click(screen.getByRole("button", { name: "Çalıştır" }));

    await screen.findByRole("img", { name: "kırmızı kask" });
    const cagri = client.request.mock.calls.find(([name]) => name === "gorsel.olustur");
    expect(cagri?.[1]).toMatchObject({ istem: "kırmızı kask", islem: "uret", saglayici: "nvidia_nim/black-forest-labs/flux.1-dev" });
    expect(client.request.mock.calls.some(([name]) => name === "gorsel.kaydet")).toBe(false);
    expect(screen.getByRole("status").textContent).toContain("Akış tamamlandı");
  });

  it("İndir yalnız kullanıcının seçtiği yere kopyalar", async () => {
    const client = istemci(async () => ({ ok: true, dosyalar: [{ yol: "/veri/galeri/a.jpg" }] }));
    const kayitYeri = vi.fn(async () => "/Users/kullanici/Desktop/kask.jpg");
    render(<ImageCreate client={client} toUrl={() => null} chooseSavePath={kayitYeri} />);
    fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
    await screen.findAllByRole("option", { name: "Gemini" });
    fireEvent.change(screen.getByLabelText("Metin istemi"), { target: { value: "kask" } });
    fireEvent.click(screen.getByRole("button", { name: "Çalıştır" }));
    await screen.findAllByRole("button", { name: "İndir" });

    fireEvent.click(screen.getAllByRole("button", { name: "İndir" })[0]);

    await waitFor(() => expect(client.request).toHaveBeenCalledWith(
      "gorsel.kaydet", { yol: "/veri/galeri/a.jpg", hedef: "/Users/kullanici/Desktop/kask.jpg" },
    ));
  });

  it("eksik girdiyle çalıştırmaz ve nedenini söyler", async () => {
    const client = istemci(async () => ({ ok: true }));
    render(<ImageCreate client={client} toUrl={() => null} chooseSavePath={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
    await screen.findAllByRole("option", { name: "Gemini" });

    fireEvent.click(screen.getByRole("button", { name: "Çalıştır" }));

    expect(await screen.findByText("Metin düğümü boş.")).toBeTruthy();
    expect(client.request.mock.calls.some(([name]) => name === "gorsel.olustur")).toBe(false);
  });

  it("referans gerektiren düğümde yalnız referans alabilen sağlayıcı listelenir", async () => {
    const client = istemci(async () => ({ ok: true }));
    render(<ImageCreate client={client} toUrl={() => null} chooseSavePath={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
    await screen.findAllByRole("option", { name: "Gemini" });

    fireEvent.click(screen.getByRole("button", { name: "+ Varyasyon" }));

    const secici = screen.getByLabelText("Varyasyon sağlayıcısı") as HTMLSelectElement;
    const etiketler = Array.from(secici.options).map((option) => option.textContent);
    expect(etiketler).toEqual(["Sağlayıcı seç", "Gemini"]);
  });

  it("hatalı üretimde düğüm hatayı gösterir, sonraki işlem çalışmaz", async () => {
    const client = istemci(async () => ({ ok: false, metin: "Gemini oturumu doğrulama bekliyor." }));
    render(<ImageCreate client={client} toUrl={() => null} chooseSavePath={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
    await screen.findAllByRole("option", { name: "Gemini" });
    fireEvent.change(screen.getByLabelText("Metin istemi"), { target: { value: "kask" } });
    fireEvent.click(screen.getByRole("button", { name: "Çalıştır" }));

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("Gemini oturumu doğrulama bekliyor.");
  });
});

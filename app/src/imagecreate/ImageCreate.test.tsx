import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

describe("ImageCreate — basit kip", () => {
  it("seçilen en-boy oranını çekirdeğe gönderir, kare oranı göndermez", async () => {
    const olustur = vi.fn(async () => ({ ok: true, dosyalar: [{ yol: "/veri/galeri/o.jpg" }] }));
    render(<ImageCreate client={istemci(olustur)} toUrl={(yol) => `asset://${yol}`} chooseSavePath={vi.fn()} />);
    await screen.findByRole("option", { name: "Gemini" });
    fireEvent.change(screen.getByLabelText("Nasıl bir görsel istiyorsun?"), { target: { value: "dağ" } });
    fireEvent.click(screen.getByRole("radio", { name: "16:9" }));
    fireEvent.click(screen.getByRole("button", { name: "Görsel oluştur" }));
    await waitFor(() => expect(olustur).toHaveBeenCalledWith(expect.objectContaining({ istem: "dağ", oran: "16:9" })));

    fireEvent.click(screen.getByRole("radio", { name: "1:1" }));
    fireEvent.click(screen.getByRole("button", { name: "Görsel oluştur" }));
    await waitFor(() => expect(olustur).toHaveBeenCalledTimes(2));
    expect(olustur.mock.calls[1][0]).not.toHaveProperty("oran");
  });
});

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

it("kısmi varyasyon sonucunu tamamlandı diye sunmaz ve kontrolleri açar", async () => {
  let count = 0;
  const client = istemci(async () => (++count === 1
    ? { ok: true, dosyalar: [{ yol: "/veri/galeri/kismi.jpg" }] }
    : { ok: false, metin: "kota doldu" }));
  render(<ImageCreate client={client} toUrl={(path) => `asset://${path}`} chooseSavePath={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
  await screen.findAllByRole("option", { name: "Gemini" });
  fireEvent.change(screen.getByLabelText("Metin istemi"), { target: { value: "kask" } });
  fireEvent.change(screen.getByLabelText("Üret varyasyon sayısı"), { target: { value: "2" } });
  fireEvent.click(screen.getByRole("button", { name: "Çalıştır" }));
  await waitFor(() => expect(screen.getByRole("status").textContent).toContain("1/2 varyasyon üretildi: kota doldu"));
  expect(screen.queryByText("Akış tamamlandı; sonuçlar galeride.")).toBeNull();
  expect((screen.getByRole("button", { name: "Çalıştır" }) as HTMLButtonElement).disabled).toBe(false);
  expect(count).toBe(2);
});

it("aynı olay döngüsünde çift oluştur tek üretim başlatır", async () => {
  const create = vi.fn(() => new Promise<Record<string, unknown>>(() => {}));
  render(<ImageCreate client={istemci(create)} toUrl={() => null} chooseSavePath={vi.fn()} />);
  await screen.findByRole("option", { name: "Gemini" });
  fireEvent.change(screen.getByLabelText("Nasıl bir görsel istiyorsun?"), { target: { value: "dağ" } });
  const button = screen.getByRole("button", { name: "Görsel oluştur" });
  act(() => { button.click(); button.click(); });
  expect(create).toHaveBeenCalledTimes(1);
});
it("istemci değişince eski üretim yeni galeriye sonuç veya sonraki varyasyon eklemez", async () => {
  let finish!: (value: Record<string, unknown>) => void;
  const create = vi.fn(() => new Promise<Record<string, unknown>>((resolve) => { finish = resolve; }));
  const { rerender } = render(<ImageCreate client={istemci(create)} toUrl={() => null} chooseSavePath={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: 'İş akışı' }));
  await screen.findAllByRole('option', { name: 'Gemini' });
  fireEvent.change(screen.getByLabelText('Metin istemi'), { target: { value: 'kask' } });
  fireEvent.change(screen.getByLabelText('Üret varyasyon sayısı'), { target: { value: '2' } });
  fireEvent.click(screen.getByRole('button', { name: 'Çalıştır' }));
  await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
  rerender(<ImageCreate client={istemci(vi.fn())} toUrl={() => null} chooseSavePath={vi.fn()} />);
  await act(async () => { finish({ ok: true, dosyalar: [{ yol: '/old-scope.jpg' }] }); });
  expect(create).toHaveBeenCalledTimes(1);
  expect(screen.queryByText('old-scope.jpg')).toBeNull();
});

it("görsel görüntüleyicide odağı tutar ve Escape ile açan kontrole döner", async () => {
  const client = istemci(async () => ({ ok: true, dosyalar: [{ yol: "/galeri/focus.png", genislik: 9, yukseklik: 6 }] }));
  render(<ImageCreate client={client} toUrl={(path) => path} chooseSavePath={vi.fn()} />);
  await screen.findByRole("option", { name: "Gemini" });
  fireEvent.change(screen.getByLabelText("Nasıl bir görsel istiyorsun?"), { target: { value: "odak" } });
  fireEvent.click(screen.getByRole("button", { name: "Görsel oluştur" }));
  const opener = await screen.findByRole("button", { name: "odak büyük aç" });
  opener.focus(); fireEvent.click(opener);
  const dialog = await screen.findByRole("dialog", { name: "Görsel görüntüleyici" });
  const buttons = [...dialog.querySelectorAll<HTMLElement>("button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled)")];
  buttons[0].focus();
  fireEvent.keyDown(buttons[0], { key: "Tab", shiftKey: true });
  expect(document.activeElement).toBe(buttons.at(-1));
  fireEvent.keyDown(buttons.at(-1)!, { key: "Tab" });
  expect(document.activeElement).toBe(buttons[0]);
  fireEvent.keyDown(buttons[0], { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Görsel görüntüleyici" })).toBeNull());
  expect(document.activeElement).toBe(opener);
});

it("galeri yenilenince kaybolan görüntüleyici arka plan kilidini bırakır", async () => {
  const client = istemci(async () => ({ ok: true, dosyalar: [{ yol: "/galeri/removed.png" }] }));
  const { container, rerender } = render(<ImageCreate client={client} toUrl={(path) => path} chooseSavePath={vi.fn()} />);
  await screen.findByRole("option", { name: "Gemini" });
  fireEvent.change(screen.getByLabelText("Nasıl bir görsel istiyorsun?"), { target: { value: "kayıp" } });
  fireEvent.click(screen.getByRole("button", { name: "Görsel oluştur" }));
  const opener = await screen.findByRole("button", { name: "kayıp büyük aç" });
  opener.focus(); fireEvent.click(opener);
  await screen.findByRole("dialog", { name: "Görsel görüntüleyici" });
  expect(container.inert).toBe(true);
  rerender(<ImageCreate client={istemci(async () => ({ ok: false }))} toUrl={(path) => path} chooseSavePath={vi.fn()} />);
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Görsel görüntüleyici" })).toBeNull());
  expect(container.inert).not.toBe(true);
  expect(document.activeElement).not.toBe(document.body);
});

describe("ImageCreate — dalga 4 (U3-02..U3-12)", () => {
  it("Enter sessizce yutulmaz: istem boşken ve sağlayıcı yokken nedenini söyler (U3-03)", async () => {
    const olustur = vi.fn(async () => ({ ok: true, dosyalar: [] }));
    render(<ImageCreate client={istemci(olustur)} toUrl={(yol) => `asset://${yol}`} chooseSavePath={vi.fn()} />);
    await screen.findByRole("option", { name: "Gemini" });
    fireEvent.keyDown(screen.getByLabelText("Nasıl bir görsel istiyorsun?"), { key: "Enter" });
    expect((await screen.findByRole("status")).textContent).toContain("Önce nasıl bir görsel");
    expect(olustur).not.toHaveBeenCalled();
  });

  it("IME onayı veren Enter (keyCode 229) istemi göndermez (U3-04)", async () => {
    const olustur = vi.fn(async () => ({ ok: true, dosyalar: [{ yol: "/veri/galeri/a.jpg" }] }));
    render(<ImageCreate client={istemci(olustur)} toUrl={(yol) => `asset://${yol}`} chooseSavePath={vi.fn()} />);
    await screen.findByRole("option", { name: "Gemini" });
    const kutu = screen.getByLabelText("Nasıl bir görsel istiyorsun?");
    fireEvent.change(kutu, { target: { value: "山" } });
    fireEvent.keyDown(kutu, { key: "Enter", keyCode: 229 });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(olustur).not.toHaveBeenCalled();
    fireEvent.keyDown(kutu, { key: "Enter", keyCode: 13 });
    await waitFor(() => expect(olustur).toHaveBeenCalledOnce());
  });

  it("sayfa değişip dönünce istem ve kip korunur; kapsamsız kullanımda saklanmaz (U3-05)", async () => {
    const { taslaklariSifirla } = await import("./taslakDeposu");
    taslaklariSifirla();
    const client = istemci(async () => ({ ok: true, dosyalar: [] }));
    const ilk = render(<ImageCreate client={client} jobScope="oturum-1" toUrl={(yol) => yol} chooseSavePath={vi.fn()} />);
    await screen.findByRole("option", { name: "Gemini" });
    fireEvent.change(screen.getByLabelText("Nasıl bir görsel istiyorsun?"), { target: { value: "uzun bir istem" } });
    ilk.unmount();
    render(<ImageCreate client={client} jobScope="oturum-1" toUrl={(yol) => yol} chooseSavePath={vi.fn()} />);
    expect((screen.getByLabelText("Nasıl bir görsel istiyorsun?") as HTMLTextAreaElement).value).toBe("uzun bir istem");
    cleanup();
    render(<ImageCreate client={client} jobScope="oturum-2" toUrl={(yol) => yol} chooseSavePath={vi.fn()} />);
    expect((screen.getByLabelText("Nasıl bir görsel istiyorsun?") as HTMLTextAreaElement).value).toBe("");
    taslaklariSifirla();
  });

  it("sağlayıcı listesinden düşen seçili sağlayıcı temizlenir, eski değer çekirdeğe gitmez (U3-06)", async () => {
    const olustur = vi.fn(async () => ({ ok: true, dosyalar: [{ yol: "/veri/galeri/a.jpg" }] }));
    const client = istemci(olustur);
    const { rerender } = render(<ImageCreate client={client} toUrl={(yol) => yol} chooseSavePath={vi.fn()} />);
    await screen.findByRole("option", { name: "Gemini" });
    fireEvent.change(screen.getByLabelText("Görsel modeli"), { target: { value: "gemini_web/main" } });
    // Oturum kapanıp liste daralır.
    vi.mocked(client.request).mockImplementation(async (name: string) => {
      if (name === "gorsel.saglayicilar") return { ok: true, secenekler: [{ deger: "nvidia_nim/black-forest-labs/flux.1-dev", etiket: "FLUX.1-dev (NVIDIA NIM)", referans: false }] };
      if (name === "gorsel.galeri") return { ok: true, dosyalar: [] };
      if (name === "gorsel.akislar") return { ok: true, akislar: [] };
      return olustur();
    });
    const yeni = { request: client.request };
    rerender(<ImageCreate client={yeni} toUrl={(yol) => yol} chooseSavePath={vi.fn()} />);
    await waitFor(() => expect(screen.queryByRole("option", { name: "Gemini" })).toBeNull());
    await waitFor(() => expect((screen.getByLabelText("Görsel modeli") as HTMLSelectElement).value).not.toBe("gemini_web/main"));
    fireEvent.change(screen.getByLabelText("Nasıl bir görsel istiyorsun?"), { target: { value: "kask" } });
    await waitFor(() => expect((screen.getByRole("button", { name: "Görsel oluştur" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Görsel oluştur" }));
    await waitFor(() => expect(olustur).toHaveBeenCalled());
    expect(olustur).not.toHaveBeenCalledWith(expect.objectContaining({ saglayici: "gemini_web/main" }));
  });

  it("indirme penceresi reddedilirse kullanıcı nedenini görür, işlenmemiş söz reddi olmaz (U3-12)", async () => {
    const client = istemci(async () => ({ ok: true, dosyalar: [{ yol: "C:\\galeri\\a.jpg" }] }));
    const secici = vi.fn(async () => { throw new Error("izin reddedildi"); });
    render(<ImageCreate client={client} toUrl={(yol) => yol} chooseSavePath={secici} />);
    await screen.findByRole("option", { name: "Gemini" });
    fireEvent.change(screen.getByLabelText("Nasıl bir görsel istiyorsun?"), { target: { value: "kask" } });
    fireEvent.click(screen.getByRole("button", { name: "Görsel oluştur" }));
    await screen.findByRole("img", { name: "kask" });
    fireEvent.click(screen.getAllByRole("button", { name: "İndir" })[0]);
    expect((await screen.findByText(/Kaydedilemedi: izin reddedildi/)).textContent).toContain("izin reddedildi");
    // Windows yolu: varsayılan ad yalnız dosya adıdır.
    expect(secici).toHaveBeenCalledWith("a.jpg");
  });

  it("üretim sürerken Durdur bekleyişi bırakır ve kutuyu açar (U3-07)", async () => {
    const olustur = vi.fn(() => new Promise<Record<string, unknown>>(() => undefined));
    render(<ImageCreate client={istemci(olustur)} toUrl={(yol) => yol} chooseSavePath={vi.fn()} />);
    await screen.findByRole("option", { name: "Gemini" });
    fireEvent.change(screen.getByLabelText("Nasıl bir görsel istiyorsun?"), { target: { value: "kask" } });
    fireEvent.click(screen.getByRole("button", { name: "Görsel oluştur" }));
    fireEvent.click(await screen.findByRole("button", { name: "Durdur" }));
    await waitFor(() => expect((screen.getByRole("button", { name: "Görsel oluştur" }) as HTMLButtonElement).disabled).toBe(false));
    expect(screen.queryByRole("button", { name: "Durdur" })).toBeNull();
  });

  it("silinen hedef düğüm dal çalıştırma kipini sessizce sürdürmez (U3-09)", async () => {
    const client = istemci(async () => ({ ok: true, dosyalar: [{ yol: "/veri/galeri/a.jpg" }] }));
    render(<ImageCreate client={client} toUrl={(yol) => `asset://${yol}`} chooseSavePath={vi.fn()} />);
    await screen.findByRole("option", { name: "Gemini" });
    fireEvent.change(screen.getByLabelText("Nasıl bir görsel istiyorsun?"), { target: { value: "kask" } });
    fireEvent.click(screen.getByRole("button", { name: "Görsel oluştur" }));
    await screen.findByRole("img", { name: "kask" });
    fireEvent.click(screen.getByRole("button", { name: "Varyasyonla devam et" }));
    expect(screen.getByRole("button", { name: "Tüm akışı çalıştır" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Varyasyon düğümünü sil" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Tüm akışı çalıştır" })).toBeNull());
  });

  it("Yeni, kaydedilmemiş düzenlemeyi onaysız silmez (U3-10)", async () => {
    render(<ImageCreate client={istemci(async () => ({ ok: true }))} toUrl={(yol) => yol} chooseSavePath={vi.fn()} />);
    await screen.findByRole("option", { name: "Gemini" });
    fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
    const metin = screen.getByLabelText("Metin istemi") as HTMLTextAreaElement;
    fireEvent.change(metin, { target: { value: "değerli istem" } });
    fireEvent.click(screen.getByRole("button", { name: "Yeni" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Kaydedilmemiş");
    expect((screen.getByLabelText("Metin istemi") as HTMLTextAreaElement).value).toBe("değerli istem");
    fireEvent.click(screen.getByRole("button", { name: "Vazgeç" }));
    expect((screen.getByLabelText("Metin istemi") as HTMLTextAreaElement).value).toBe("değerli istem");
    fireEvent.click(screen.getByRole("button", { name: "Yeni" }));
    fireEvent.click(screen.getByRole("button", { name: "Sil ve devam et" }));
    expect((screen.getByLabelText("Metin istemi") as HTMLTextAreaElement).value).toBe("");
  });

  it("bozuk kayıtlı akış arayüzü çökertmez, hata gösterir (U3-10)", async () => {
    const client = istemci(async () => ({ ok: true }));
    const inner = vi.mocked(client.request).getMockImplementation()!;
    vi.mocked(client.request).mockImplementation(async (name: string, data: Record<string, unknown>) => {
      if (name === "gorsel.akislar") return { ok: true, akislar: [{ id: "a1", ad: "Bozuk" }] };
      if (name === "gorsel.akis.yukle") return { ok: true, akis: { ad: "Bozuk", dugumler: [{ id: "x", tur: "yok" }] } };
      return inner(name, data);
    });
    render(<ImageCreate client={client} toUrl={(yol) => yol} chooseSavePath={vi.fn()} />);
    await screen.findByRole("option", { name: "Gemini" });
    fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
    fireEvent.change(await screen.findByRole("combobox", { name: "Kayıtlı akışlar" }), { target: { value: "a1" } });
    expect((await screen.findByRole("alert")).textContent).toContain("geçersiz");
    expect(screen.getByLabelText("Görsel iş akışı tuvali")).toBeTruthy();
  });
});

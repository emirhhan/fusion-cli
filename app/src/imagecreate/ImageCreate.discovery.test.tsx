import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ImageCreate } from "./ImageCreate";

afterEach(cleanup);

it("galeri sonraki sayfayı aynı cursor ile ekler ve ilk görselleri korur", async () => {
  const cursor = [1, "12345678-1234-4234-8234-123456789012"];
  const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
    if (name === "gorsel.galeri") return data.cursor ? { ok: true, dosyalar: [{ yol: "/gallery/b.png", istem: "İkinci" }], next_cursor: null } : { ok: true, dosyalar: [{ yol: "/gallery/a.png", istem: "İlk" }], next_cursor: cursor };
    return { ok: true, secenekler: [], akislar: [] };
  });
  render(<ImageCreate client={{ request }} toUrl={path => path} />);
  await screen.findByRole("button", { name: "İlk büyük aç" });
  fireEvent.click(screen.getByRole("button", { name: "Daha fazla görsel göster" }));
  await screen.findByRole("button", { name: "İkinci büyük aç" });
  expect(screen.getByRole("button", { name: "İlk büyük aç" })).toBeTruthy();
  expect(request).toHaveBeenCalledWith("gorsel.galeri", { sinir: 50, cursor });
  expect(screen.queryByRole("button", { name: "Daha fazla görsel göster" })).toBeNull();
});

describe("Görsel bağımsız keşif durumu", () => {
  it("provider retry yalnız ilgili endpoint'i yeniden yükler", async () => {
    let isReady = false;
    const request = vi.fn(async (name: string) => {
      if (name === "gorsel.saglayicilar") return isReady ? { ok: true, secenekler: [{ deger: "test/model", etiket: "Test modeli" }] } : { ok: false, metin: "Sağlayıcı kapalı." };
      return { ok: true, dosyalar: [], akislar: [] };
    });
    render(<ImageCreate client={{ request }} toUrl={(path) => path} chooseSavePath={vi.fn()} />);
    await screen.findByText(/Sağlayıcı kapalı/);
    isReady = true;
    fireEvent.click(screen.getByRole("button", { name: "Sağlayıcılar: Yeniden dene" }));
    await screen.findByRole("option", { name: "Test modeli" });
    expect(request.mock.calls.filter(([name]) => name === "gorsel.saglayicilar")).toHaveLength(2);
    expect(request.mock.calls.filter(([name]) => name === "gorsel.galeri")).toHaveLength(1);
    expect(request.mock.calls.filter(([name]) => name === "gorsel.akislar")).toHaveLength(1);
  });
  it("geç gelen yükleme kullanıcı düzenlediği akış adını ezmez", async () => {
    let resolveLoad!: (result: Record<string, unknown>) => void;
    const client = { request: vi.fn(async (name: string) => {
      if (name === "gorsel.akis.yukle") return new Promise<Record<string, unknown>>((resolve) => { resolveLoad = resolve; });
      return { ok: true, secenekler: [], dosyalar: [], akislar: [{ id: "stored-a", ad: "Kayıtlı" }] };
    }) };
    render(<ImageCreate client={client} toUrl={(path) => path} chooseSavePath={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
    await screen.findByRole("option", { name: "Kayıtlı" });
    fireEvent.change(screen.getByLabelText("Kayıtlı akışlar"), { target: { value: "stored-a" } });
    fireEvent.change(screen.getByLabelText("Akış adı"), { target: { value: "Son düzenleme" } });
    await act(async () => resolveLoad({ ok: true, akis: { ad: "Eski kayıt", dugumler: [], baglantilar: [] } }));
    expect((screen.getByLabelText("Akış adı") as HTMLInputElement).value).toBe("Son düzenleme");
  });
  it("başarısız kayıt mevcut akışı ve sunucunun hata nedenini korur", async () => {
    const client = { request: vi.fn(async (name: string) => {
      if (name === "gorsel.akis.kaydet") return { ok: false, metin: "Akış deposu yazılamıyor." };
      return { ok: true, secenekler: [], dosyalar: [], akislar: [] };
    }) };
    render(<ImageCreate client={client} toUrl={(path) => path} chooseSavePath={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
    fireEvent.change(screen.getByLabelText("Akış adı"), { target: { value: "Yarım akış" } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    expect(await screen.findByText("Akış deposu yazılamıyor.")).toBeTruthy();
    expect((screen.getByLabelText("Akış adı") as HTMLInputElement).value).toBe("Yarım akış");
    expect(screen.getAllByLabelText("Metin istemi").length).toBeGreaterThan(0);
  });
  it("galeri reddedilse de başarılı sağlayıcı listesi kalır ve galeri nedeni görünür olur", async () => {
    const client = { request: vi.fn(async (name: string) => {
      if (name === "gorsel.saglayicilar") return { ok: true, secenekler: [{ deger: "test/model", etiket: "Test modeli", referans: false }] };
      if (name === "gorsel.galeri") throw new Error("Galeri okunamadı.");
      return { ok: true, akislar: [] };
    }) };
    render(<ImageCreate client={client} toUrl={(path) => path} chooseSavePath={vi.fn()} />);
    expect(await screen.findByRole("option", { name: "Test modeli" })).toBeTruthy();
    expect(await screen.findByText(/Galeri okunamadı/)).toBeTruthy();
  });
  it("akış kaydı beklerken çift kaydet tek mutasyon yapar", async () => {
    const client = { request: vi.fn(async (name: string) => {
      if (name === "gorsel.akis.kaydet") return new Promise<Record<string, unknown>>(() => undefined);
      return { ok: true, secenekler: [], dosyalar: [], akislar: [] };
    }) };
    render(<ImageCreate client={client} toUrl={(path) => path} chooseSavePath={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
    const save = screen.getByRole("button", { name: "Kaydet" });
    fireEvent.click(save);
    fireEvent.click(save);
    expect(client.request.mock.calls.filter(([name]) => name === "gorsel.akis.kaydet")).toHaveLength(1);
  });
  it("geç gelen kayıt başarısı kullanıcının yeni akış adını ezmez", async () => {
    let resolveSave!: (result: Record<string, unknown>) => void;
    const client = { request: vi.fn(async (name: string) => {
      if (name === "gorsel.akis.kaydet") return new Promise<Record<string, unknown>>((resolve) => { resolveSave = resolve; });
      return { ok: true, secenekler: [], dosyalar: [], akislar: [] };
    }) };
    render(<ImageCreate client={client} toUrl={(path) => path} chooseSavePath={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    fireEvent.change(screen.getByLabelText("Akış adı"), { target: { value: "Yeni düzenlenen akış" } });
    await act(async () => resolveSave({ ok: true, id: "saved-flow" }));
    expect((screen.getByLabelText("Akış adı") as HTMLInputElement).value).toBe("Yeni düzenlenen akış");
  });
  it("sağlayıcı keşfi beklerken bağlı sağlayıcı yok uyarısı vermez", () => {
    const client = { request: vi.fn(async (name: string) => {
      if (name === "gorsel.saglayicilar") return new Promise<Record<string, unknown>>(() => undefined);
      return { ok: true, dosyalar: [], akislar: [] };
    }) };
    render(<ImageCreate client={client} toUrl={(path) => path} chooseSavePath={vi.fn()} />);
    expect(screen.queryByText(/Görsel üretebilen bağlı sağlayıcı yok/)).toBeNull();
    expect(screen.getByText(/sağlayıcı.*yükleniyor/i)).toBeTruthy();
  });
  it("çözülmüş başarısız keşfin nedenini gösterir", async () => {
    const client = { request: vi.fn(async (name: string) => {
      if (name === "gorsel.saglayicilar") return { ok: false, metin: "Sağlayıcı keşfi reddedildi." };
      return { ok: true, dosyalar: [], akislar: [] };
    }) };
    render(<ImageCreate client={client} toUrl={(path) => path} chooseSavePath={vi.fn()} />);
    expect(await screen.findByText(/Sağlayıcı keşfi reddedildi/)).toBeTruthy();
    expect(screen.queryByText(/Görsel üretebilen bağlı sağlayıcı yok/)).toBeNull();
  });
});

it("galeri beklerken ve hata durumunda boş galeri iddia etmez; ready boşta gösterir", async () => {
  let reject!: (reason: Error) => void;
  let isReady = false;
  const request = vi.fn((name: string) => name === "gorsel.galeri" && !isReady ? new Promise((_, fail) => { reject = fail; }) : Promise.resolve({ ok: true, dosyalar: [], secenekler: [], akislar: [] }));
  render(<ImageCreate client={{ request }} toUrl={(path) => path} chooseSavePath={vi.fn()} />);
  expect(screen.queryByText("Hayal et, Fusion çizsin.")).toBeNull();
  await act(async () => reject(new Error("Galeri kapalı")));
  expect(screen.queryByText("Hayal et, Fusion çizsin.")).toBeNull();
  isReady = true;
  fireEvent.click(screen.getByRole("button", { name: "Galeri: Yeniden dene" }));
  expect(await screen.findByText("Hayal et, Fusion çizsin.")).toBeTruthy();
});

it("ikinci kayıtta sunucunun onayladığı revision gönderilir", async () => {
  const request = vi.fn(async (name: string, _data: Record<string, unknown>) => {
    if (name === "gorsel.akis.kaydet") return { ok: true, id: "a".repeat(32), revision: 1 };
    return { ok: true, secenekler: [], dosyalar: [], akislar: [] };
  });
  render(<ImageCreate client={{ request }} toUrl={(path) => path} chooseSavePath={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
  fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
  await screen.findByText("Akış kaydedildi.");
  fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
  await waitFor(() => expect(request.mock.calls.filter(([name]) => name === "gorsel.akis.kaydet")).toHaveLength(2));
  const saved = request.mock.calls.filter(([name]) => name === "gorsel.akis.kaydet");
  expect(saved[1][1].akis).toMatchObject({ id: "a".repeat(32), revision: 1 });
});

it("yazılmış ama kalıcılığı belirsiz kaydı yeniden oluşturmak yerine okur", async () => {
  const flowId = "c".repeat(32);
  const request = vi.fn(async (name: string, _data: Record<string, unknown>) => {
    if (name === "gorsel.akis.kaydet") return { ok: false, committed: true, id: flowId, revision: 1, metin: "Kalıcılık belirsiz." };
    if (name === "gorsel.akis.yukle") return { ok: false, metin: "Kayıt okunamadı." };
    return { ok: true, secenekler: [], dosyalar: [], akislar: [] };
  });
  render(<ImageCreate client={{ request }} toUrl={(path) => path} chooseSavePath={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
  fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
  await screen.findByText(/Kalıcılık belirsiz/);
  fireEvent.click(screen.getByRole("button", { name: "Yeniden dene" }));
  await waitFor(() => expect(request.mock.calls.some(([name]) => name === "gorsel.akis.yukle")).toBe(true));
  expect(request.mock.calls.filter(([name]) => name === "gorsel.akis.kaydet")).toHaveLength(1);
});

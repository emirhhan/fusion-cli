import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LibraryScreen, formatSize, type LibraryItem } from "./LibraryScreen";

afterEach(cleanup);

const rapor: LibraryItem = { ad: "rapor.md", boyut: 2048, degisim: 2, kaynak: "uretilen", kok: "/proje", tur: "belge", yol: "/proje/rapor.md" };
const kask: LibraryItem = { ad: "kask.png", boyut: 5, degisim: 1, kaynak: "gorsel", kok: "", tur: "gorsel", yol: "/galeri/kask.png" };

function fakeClient(responses: Record<string, Record<string, unknown>> = {}) {
  const request = vi.fn(async (name: string, _data: Record<string, unknown>) =>
    responses[name] ?? { ok: true, dosyalar: [rapor, kask], toplam: 2 });
  return { client: { request }, request };
}

describe("LibraryScreen", () => {
  it("dosyaları kaynağı ve boyutuyla listeler, görsele önizleme koyar", async () => {
    const { client } = fakeClient();
    const { container } = render(<LibraryScreen client={client} toUrl={(path) => `asset://${path}`} />);
    expect(await screen.findByText("rapor.md")).toBeTruthy();
    expect(screen.getByText("Fusion oluşturdu · 2.0 KB")).toBeTruthy();
    expect(container.querySelector("img")?.getAttribute("src")).toBe("asset:///galeri/kask.png");
  });

  it("tür süzgeci ve arama isteğe taşınır", async () => {
    const { client, request } = fakeClient();
    render(<LibraryScreen client={client} toUrl={() => null} />);
    await screen.findByText("rapor.md");
    fireEvent.click(screen.getByRole("tab", { name: "Belgeler" }));
    fireEvent.change(screen.getByLabelText("Kitaplıkta ara"), { target: { value: "rapor" } });
    await waitFor(() => expect(request).toHaveBeenLastCalledWith("kitaplik.liste", { tur: "belge", sorgu: "rapor" }));
  });

  it("dosya yükler, kaydı kaldırır ve klasörde gösterir", async () => {
    const { client, request } = fakeClient({ "kitaplik.ekle": { ok: true }, "kitaplik.kaldir": { ok: true } });
    const reveal = vi.fn(async () => undefined);
    render(<LibraryScreen chooseFiles={async () => ["/tmp/a.pdf"]} client={client} reveal={reveal} toUrl={() => null} />);
    await screen.findByText("rapor.md");
    fireEvent.click(screen.getByRole("button", { name: "Dosya yükle" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("kitaplik.ekle", { yol: "/tmp/a.pdf" }));
    fireEvent.click(screen.getByRole("button", { name: "rapor.md kaydını kaldır" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("kitaplik.kaldir", { yol: "/proje/rapor.md" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Klasörde göster" })[0]);
    expect(reveal).toHaveBeenCalledWith("/proje/rapor.md");
    // Galeri görseli kayıt defterinde değildir; kaldırma düğmesi sunulmaz.
    expect(screen.queryByRole("button", { name: "kask.png kaydını kaldır" })).toBeNull();
  });

  it("çekirdek hatasını ve boş durumu dürüstçe gösterir", async () => {
    const { client } = fakeClient({ "kitaplik.liste": { ok: false, metin: "Kitaplık bozuk." } });
    render(<LibraryScreen client={client} toUrl={() => null} />);
    expect((await screen.findByRole("alert")).textContent).toBe("Kitaplık bozuk.");
    cleanup();
    render(<LibraryScreen client={null} />);
    expect(screen.getByText("Kitaplığı görmek için Home'da bir sohbet aç.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Dosya yükle" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("yükleme hatası ardından gelen başarılı yenilemeyle silinmez", async () => {
    // Ölçüldü (29 Ekim): `load()` başarıda hatayı temizliyordu; yüklenemeyen dosyanın
    // hatası anında kayboluyor, kullanıcı dosyanın eklendiğini sanıyordu.
    const { client } = fakeClient({ "kitaplik.ekle": { ok: false, metin: "Dosya çok büyük." } });
    render(<LibraryScreen chooseFiles={async () => ["/tmp/dev.zip"]} client={client} toUrl={() => null} />);
    await screen.findByText("rapor.md");
    fireEvent.click(screen.getByRole("button", { name: "Dosya yükle" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Dosya çok büyük.");
    fireEvent.change(screen.getByLabelText("Kitaplıkta ara"), { target: { value: "r" } });
    await waitFor(() => expect(client.request).toHaveBeenLastCalledWith("kitaplik.liste", { tur: "", sorgu: "r" }));
    expect(screen.getByRole("alert").textContent).toBe("Dosya çok büyük.");
  });

  it("yeni başarılı işlem önceki işlem hatasını kaldırır", async () => {
    let fail = true;
    const request = vi.fn(async (name: string) => {
      if (name === "kitaplik.ekle") return fail ? { ok: false, metin: "Dosya çok büyük." } : { ok: true };
      return { ok: true, dosyalar: [rapor], toplam: 1 };
    });
    render(<LibraryScreen chooseFiles={async () => ["/tmp/a.pdf"]} client={{ request }} toUrl={() => null} />);
    await screen.findByText("rapor.md");
    fireEvent.click(screen.getByRole("button", { name: "Dosya yükle" }));
    await screen.findByRole("alert");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Dosya yükle" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("yavaş eski liste yanıtı yeni süzgecin sonucunu ezmez (U6-02)", async () => {
    // Ölçüldü (30 Ekim): son-istek-kazanır yoktu; yavaş eski yanıt yeni sorgunun listesini eziyordu.
    const bekleyen: Array<(deger: Record<string, unknown>) => void> = [];
    const request = vi.fn((_name: string, data: Record<string, unknown>) => {
      if (data.tur === "") return Promise.resolve({ ok: true, dosyalar: [rapor], toplam: 1 });
      return new Promise<Record<string, unknown>>((coz) => bekleyen.push(coz));
    });
    render(<LibraryScreen client={{ request }} toUrl={() => null} />);
    await screen.findByText("rapor.md");
    fireEvent.click(screen.getByRole("tab", { name: "Belgeler" }));
    fireEvent.click(screen.getByRole("tab", { name: "Videolar" }));
    await waitFor(() => expect(bekleyen.length).toBe(2));
    const yeni = { ...rapor, ad: "yeni.md", yol: "/proje/yeni.md" };
    const eski = { ...rapor, ad: "eski.md", yol: "/proje/eski.md" };
    bekleyen[1]({ ok: true, dosyalar: [yeni], toplam: 1 });
    await screen.findByText("yeni.md");
    bekleyen[0]({ ok: true, dosyalar: [eski], toplam: 1 });
    await new Promise((coz) => setTimeout(coz, 20));
    expect(screen.queryByText("eski.md")).toBeNull();
    expect(screen.getByText("yeni.md")).toBeTruthy();
  });

  it("arama kutusu her tuşta değil, yazma durunca bir kez sorar (U6-02)", async () => {
    const { client, request } = fakeClient();
    render(<LibraryScreen client={client} toUrl={() => null} />);
    await screen.findByText("rapor.md");
    request.mockClear();
    const kutu = screen.getByLabelText("Kitaplıkta ara");
    for (const deger of ["r", "ra", "rap"]) fireEvent.change(kutu, { target: { value: deger } });
    await waitFor(() => expect(request).toHaveBeenCalledWith("kitaplik.liste", { tur: "", sorgu: "rap" }));
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("dosya seçici reddedilirse yakalanmamış hata değil uyarı gösterir (U6-03)", async () => {
    const { client } = fakeClient();
    render(<LibraryScreen chooseFiles={async () => { throw new Error("diyalog"); }} client={client} toUrl={() => null} />);
    await screen.findByText("rapor.md");
    fireEvent.click(screen.getByRole("button", { name: "Dosya yükle" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Dosya seçici açılamadı.");
  });

  it("çok dosyada birden çok hata varsa kaçının eklenemediği ve ilk neden yazılır (U6-03)", async () => {
    // Ölçüldü (30 Ekim): her başarısız dosya öncekinin hatasını eziyor, yalnız sonuncusu kalıyordu.
    const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "kitaplik.ekle") return data.yol === "/tmp/b.pdf" ? { ok: true } : { ok: false, metin: `Reddedildi: ${String(data.yol)}` };
      return { ok: true, dosyalar: [rapor], toplam: 1 };
    });
    render(<LibraryScreen chooseFiles={async () => ["/tmp/a.zip", "/tmp/b.pdf", "/tmp/c.zip"]} client={{ request }} toUrl={() => null} />);
    await screen.findByText("rapor.md");
    fireEvent.click(screen.getByRole("button", { name: "Dosya yükle" }));
    expect((await screen.findByRole("alert")).textContent).toBe("2 dosya eklenemedi. İlk neden: Reddedildi: /tmp/a.zip");
    expect(request).toHaveBeenCalledWith("kitaplik.ekle", { yol: "/tmp/c.zip" });
  });

  it("boyutu okunur birimle yazar", () => {
    expect(formatSize(512)).toBe("512 B");
    expect(formatSize(1536)).toBe("1.5 KB");
    expect(formatSize(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});

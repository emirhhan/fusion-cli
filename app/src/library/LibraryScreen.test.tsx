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

  it("boyutu okunur birimle yazar", () => {
    expect(formatSize(512)).toBe("512 B");
    expect(formatSize(1536)).toBe("1.5 KB");
    expect(formatSize(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});

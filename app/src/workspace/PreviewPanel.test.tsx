import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
const { ayriAdres } = vi.hoisted(() => ({ ayriAdres: vi.fn(async (): Promise<string | null> => null) }));
vi.mock("./htmlPreviewSource", () => ({ ayriKokenliOnizlemeAdresi: ayriAdres }));

import { PreviewPanel, isLocalPreviewUrl } from "./PreviewPanel";

afterEach(cleanup);

const createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fusion-preview");
const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);

afterEach(() => {
  createObjectURL.mockClear();
  revokeObjectURL.mockClear();
});

describe("PreviewPanel", () => {
  it("yalnız localhost geliştirme adreslerini gömer", () => {
    expect(isLocalPreviewUrl("http://localhost:5173/game")).toBe(true);
    expect(isLocalPreviewUrl("http://127.0.0.1:3001")).toBe(true);
    expect(isLocalPreviewUrl("http://[::1]:8080")).toBe(true);
    expect(isLocalPreviewUrl("https://example.com")).toBe(false);
    expect(isLocalPreviewUrl("javascript:alert(1)")).toBe(false);
    expect(isLocalPreviewUrl("http://localhost.evil.example")).toBe(false);
  });

  it("uygulamanın kendi kökenini (aynı port) gömmeyi reddeder (U4-48)", () => {
    const own = new URL(window.location.href);
    expect(isLocalPreviewUrl(`http://localhost:${own.port}/`)).toBe(false);
    expect(isLocalPreviewUrl(`http://127.0.0.1:${own.port}/x`)).toBe(false);
    expect(isLocalPreviewUrl(`http://[::1]:${own.port}`)).toBe(false);
    expect(isLocalPreviewUrl(`http://localhost:${Number(own.port) + 1}/`)).toBe(true);
  });

  it("HTML dosya önizlemesi betik çalıştırır ama opak kökenli kalır: allow-scripts var, allow-same-origin yok (U4-47)", async () => {
    const html = "<script>document.title='x'</script><p>oyun</p>";
    const client = {
      request: vi.fn(async () => ({
        ok: true, yol: "oyun.html", tur: "html", mime: "text/html",
        boyut: html.length, base64: btoa(html),
      })),
    } as unknown as ProtocolClient;
    render(<PreviewPanel client={client} selectedPath="oyun.html" revision={0} />);
    const frame = await screen.findByTitle("oyun.html HTML önizlemesi");
    const sandbox = (frame.getAttribute("sandbox") ?? "").split(/\s+/);
    expect(sandbox).toContain("allow-scripts");
    expect(sandbox).not.toContain("allow-same-origin");
    expect(sandbox).not.toContain("allow-top-navigation");
    expect(sandbox).not.toContain("allow-popups");
  });

  /* Ölçüldü (30 Ekim): srcdoc önizlemesi ana pencerenin CSP'sini miras alıyor, paketli uygulamada satır içi
     betikler çalışmıyordu. Ayrı kökenli adres varsa iframe srcdoc yerine o adresle açılır (U4-47). */
  it("ayrı kökenli önizleme adresi varsa iframe onunla açılır, srcdoc kullanılmaz; sandbox aynı kalır", async () => {
    ayriAdres.mockResolvedValueOnce("fusion-preview://localhost/abc");
    const html = "<script>1</script>";
    const client = {
      request: vi.fn(async () => ({
        ok: true, yol: "oyun.html", tur: "html", mime: "text/html", boyut: html.length, base64: btoa(html),
      })),
    } as unknown as ProtocolClient;
    render(<PreviewPanel client={client} selectedPath="oyun.html" revision={0} />);

    const frame = await screen.findByTitle("oyun.html HTML önizlemesi");

    expect(frame.getAttribute("src")).toBe("fusion-preview://localhost/abc");
    expect(frame.hasAttribute("srcdoc")).toBe(false);
    expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
    expect(ayriAdres).toHaveBeenCalledWith(html);
  });

  it("seçili görseli protokolden güvenli veri adresiyle gösterir", async () => {
    const client = {
      request: vi.fn(async () => ({
        ok: true, yol: "assets/hero.png", tur: "image", mime: "image/png",
        boyut: 12, base64: "aGVsbG8=",
      })),
    } as unknown as ProtocolClient;

    render(<PreviewPanel client={client} selectedPath="assets/hero.png" />);

    const image = await screen.findByRole("img", { name: "assets/hero.png önizlemesi" });
    expect(image.getAttribute("src")).toBe("blob:fusion-preview");
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(client.request).toHaveBeenCalledWith("proje.onizle", { yol: "assets/hero.png" });
  });

  it("dış URL'yi gömmez ve desteklenmeyen dosyada açık hata gösterir", async () => {
    const client = {
      request: vi.fn(async () => ({
        ok: false, kod: "UNSUPPORTED_PREVIEW",
        metin: "Bu dosya türü uygulama içinde önizlenemiyor.",
      })),
    } as unknown as ProtocolClient;
    render(<PreviewPanel client={client} selectedPath="archive.zip" />);

    expect(await screen.findByText("Bu dosya türü uygulama içinde önizlenemiyor.")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Web" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Yerel önizleme adresi" }), {
      target: { value: "https://example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Adrese git" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("yalnız localhost"));
    expect(screen.queryByTitle("Yerel geliştirme önizlemesi")).toBeNull();
    expect(screen.getByRole("button", { name: "Dışarıda aç" }).hasAttribute("disabled")).toBe(true);
  });

  it("yerel web geçmişinde geri, ileri, yenile ve harici aç eylemlerini yönetir", async () => {
    const openExternal = vi.fn(async () => undefined);
    const client = {
      request: vi.fn(async (name: string, data: Record<string, unknown>) => name === "web.onizleme_dogrula"
        ? { ok: true, url: data.url, durum: 200 }
        : { ok: true }),
    } as unknown as ProtocolClient;
    render(<PreviewPanel client={client} openExternal={openExternal} selectedPath={null} />);

    fireEvent.click(screen.getByRole("tab", { name: "Web" }));
    const address = screen.getByRole("textbox", { name: "Yerel önizleme adresi" });
    fireEvent.change(address, { target: { value: "http://localhost:3001" } });
    fireEvent.click(screen.getByRole("button", { name: "Adrese git" }));
    await screen.findByTitle("Yerel geliştirme önizlemesi");
    fireEvent.change(address, { target: { value: "http://localhost:4173" } });
    fireEvent.click(screen.getByRole("button", { name: "Adrese git" }));
    await waitFor(() => expect(screen.getByTitle("Yerel geliştirme önizlemesi").getAttribute("src")).toBe("http://localhost:4173"));

    fireEvent.click(screen.getByRole("button", { name: "Geri" }));
    await waitFor(() => expect(screen.getByTitle("Yerel geliştirme önizlemesi").getAttribute("src")).toBe("http://localhost:3001"));
    fireEvent.click(screen.getByRole("button", { name: "İleri" }));
    await waitFor(() => expect(screen.getByTitle("Yerel geliştirme önizlemesi").getAttribute("src")).toBe("http://localhost:4173"));
    const before = screen.getByTitle("Yerel geliştirme önizlemesi").getAttribute("data-revision");
    fireEvent.click(screen.getByRole("button", { name: "Yenile" }));
    await waitFor(() => expect(screen.getByTitle("Yerel geliştirme önizlemesi").getAttribute("data-revision")).not.toBe(before));
    fireEvent.click(screen.getByRole("button", { name: "Dışarıda aç" }));
    await waitFor(() => expect(openExternal).toHaveBeenCalledWith("http://localhost:4173"));
  });

  it("metin dosyasını dosya modunda ve seçilen viewport ölçüsünü web modunda gösterir", async () => {
    const client = {
      request: vi.fn(async (name: string, data: Record<string, unknown>) => name === "web.onizleme_dogrula"
        ? { ok: true, url: data.url, durum: 200 }
        : {
            ok: true, yol: "README.md", tur: "text", mime: "text/markdown",
            boyut: 13, base64: "IyBGdXNpb24gQXBw",
          }),
    } as unknown as ProtocolClient;
    render(<PreviewPanel client={client} selectedPath="README.md" />);
    expect(await screen.findByText("# Fusion App")).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "Web" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Yerel önizleme adresi" }), {
      target: { value: "http://127.0.0.1:5173" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Adrese git" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Önizleme boyutu" }), {
      target: { value: "mobile" },
    });
    await waitFor(() => expect(screen.getByTestId("web-preview-viewport").getAttribute("data-viewport")).toBe("mobile"));
  });

  it("iframe yüklenemediğinde boş alan yerine açıklama ve harici açma sunar", async () => {
    const openExternal = vi.fn(async () => undefined);
    const client = {
      request: vi.fn(async () => ({ ok: false, metin: "Yerel sunucuya bağlanılamadı." })),
    } as unknown as ProtocolClient;
    render(<PreviewPanel client={client} openExternal={openExternal} selectedPath={null} />);
    fireEvent.click(screen.getByRole("tab", { name: "Web" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Yerel önizleme adresi" }), {
      target: { value: "http://localhost:9000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Adrese git" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("önizleme yüklenemedi");
    const external = alert.querySelector("button");
    expect(external?.textContent).toBe("Dışarıda aç");
    fireEvent.click(external as HTMLButtonElement);
    await waitFor(() => expect(openExternal).toHaveBeenCalledWith("http://localhost:9000"));
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("Dosya ve Web sekmelerini ok tuşlarıyla roving focus modelinde değiştirir", () => {
    const client = { request: vi.fn() } as unknown as ProtocolClient;
    render(<PreviewPanel client={client} selectedPath={null} />);
    const web = screen.getByRole("tab", { name: "Web" });
    const file = screen.getByRole("tab", { name: "Dosya" });

    expect(web.getAttribute("tabindex")).toBe("0");
    expect(file.getAttribute("tabindex")).toBe("-1");
    fireEvent.keyDown(web, { key: "ArrowLeft" });
    expect(file.getAttribute("aria-selected")).toBe("true");
    expect(file.getAttribute("tabindex")).toBe("0");
    expect(file.getAttribute("aria-controls")).toBe("preview-file-panel");
  });

  it("geciken doğrulama kullanıcının yazdığı yeni adresi açmaz veya ezmez", async () => {
    let resolveValidation: ((payload: Record<string, unknown>) => void) | null = null;
    const client = {
      request: vi.fn(() => new Promise<Record<string, unknown>>((resolve) => { resolveValidation = resolve; })),
    } as unknown as ProtocolClient;
    render(<PreviewPanel client={client} selectedPath={null} />);
    const address = screen.getByRole("textbox", { name: "Yerel önizleme adresi" }) as HTMLInputElement;
    fireEvent.change(address, { target: { value: "http://localhost:3001" } });
    fireEvent.click(screen.getByRole("button", { name: "Adrese git" }));
    fireEvent.change(address, { target: { value: "http://localhost:4173" } });
    resolveValidation?.({ ok: true, url: "http://localhost:3001", durum: 200 });

    await waitFor(() => expect(address.value).toBe("http://localhost:4173"));
    expect(screen.queryByTitle("Yerel geliştirme önizlemesi")).toBeNull();
  });

  it("geciken başarısız doğrulama yeni adrese eski hata ve dışarıda aç eylemi yazmaz", async () => {
    let resolveValidation: ((payload: Record<string, unknown>) => void) | null = null;
    const client = {
      request: vi.fn(() => new Promise<Record<string, unknown>>((resolve) => { resolveValidation = resolve; })),
    } as unknown as ProtocolClient;
    render(<PreviewPanel client={client} selectedPath={null} />);
    const address = screen.getByRole("textbox", { name: "Yerel önizleme adresi" }) as HTMLInputElement;
    fireEvent.change(address, { target: { value: "http://localhost:3001" } });
    fireEvent.click(screen.getByRole("button", { name: "Adrese git" }));
    fireEvent.change(address, { target: { value: "http://localhost:4173" } });
    resolveValidation?.({ ok: false, metin: "Eski adres açılamadı" });

    await waitFor(() => expect(address.value).toBe("http://localhost:4173"));
    expect(screen.queryByText("Eski adres açılamadı")).toBeNull();
    expect(screen.queryByRole("button", { name: "Dışarıda aç" })?.hasAttribute("disabled")).toBe(true);
  });
});

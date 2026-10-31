import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { PreviewLog, decodePageLog } from "./PreviewLog";
import { PreviewScreenshot, decodeScreenshot } from "./PreviewScreenshot";
import { findViewport } from "./previewViewports";

afterEach(cleanup);

const gunluk = {
  ok: true,
  url: "http://localhost:5173/",
  konsol: [
    { seviye: "log", metin: "hazır", kaynak: "" },
    { seviye: "error", metin: "x tanımsız", kaynak: "main.js:12" },
  ],
  ag: [
    { yontem: "GET", url: "http://localhost:5173/", durum: 200, tur: "document", hata: "", basarisiz: false },
    { yontem: "GET", url: "http://localhost:5173/app.css", durum: 404, tur: "stylesheet", hata: "", basarisiz: true },
  ],
  hata_sayisi: 1,
  basarisiz_istek: 1,
};

describe("PreviewLog (konsol/ağ günlüğü, P-041)", () => {
  it("yükü çözer, hatalı yükte çekirdeğin metniyle fırlatır", () => {
    const sonuc = decodePageLog(gunluk);
    expect(sonuc.konsol).toHaveLength(2);
    expect(sonuc.ag[1].basarisiz).toBe(true);
    expect(() => decodePageLog({ ok: false, metin: "Playwright kurulu değil" })).toThrow("Playwright kurulu değil");
  });

  it("konsol ve ağ sekmelerini sayılarla gösterir; 'yalnız sorunlar' süzer; yenile yeniden ister", async () => {
    const client = { request: vi.fn(async () => gunluk) } as unknown as ProtocolClient & { request: ReturnType<typeof vi.fn> };
    render(<PreviewLog client={client} onClose={vi.fn()} url="http://localhost:5173/" />);

    expect(await screen.findByText("x tanımsız")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Konsol (2 · 1 hata)" })).toBeTruthy();
    expect(client.request).toHaveBeenCalledWith("onizleme.gunluk", { url: "http://localhost:5173/" });

    fireEvent.click(screen.getByRole("checkbox", { name: "Yalnız sorunlar" }));
    expect(screen.queryByText("hazır")).toBeNull();

    fireEvent.click(screen.getByRole("tab", { name: "Ağ (2 · 1 başarısız)" }));
    expect(screen.getByText("GET http://localhost:5173/app.css")).toBeTruthy();
    expect(screen.queryByText("GET http://localhost:5173/")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Günlüğü yenile" }));
    await waitFor(() => expect(client.request).toHaveBeenCalledTimes(2));
  });

  it("çekirdek hatasını alert olarak gösterir ve kapatma geri çağrısını tetikler", async () => {
    const client = { request: vi.fn(async () => ({ ok: false, metin: "Yalnız localhost adresleri okunabilir." })) } as unknown as ProtocolClient;
    const onClose = vi.fn();
    render(<PreviewLog client={client} onClose={onClose} url="http://localhost:5173/" />);
    expect((await screen.findByRole("alert")).textContent).toContain("localhost");
    fireEvent.click(screen.getByRole("button", { name: "Günlüğü kapat" }));
    expect(onClose).toHaveBeenCalled();
  });
});

describe("PreviewScreenshot (P-041)", () => {
  it("seçili cihaz boyutuyla ister, görüntüyü ve dosya yolunu gösterir, tema seçimi yeniden ister", async () => {
    const client = {
      request: vi.fn(async () => ({
        ok: true, base64: "aGVsbG8=", mime: "image/png", yol: ".fusion/onizleme-ekran.png", genislik: 375, yukseklik: 812,
      })),
    } as unknown as ProtocolClient & { request: ReturnType<typeof vi.fn> };
    render(<PreviewScreenshot client={client} onClose={vi.fn()} url="http://localhost:5173/" viewport={findViewport("mobile")} />);

    const img = await screen.findByRole("img", { name: "http://localhost:5173/ ekran görüntüsü" });
    expect(img.getAttribute("src")).toBe("data:image/png;base64,aGVsbG8=");
    expect(screen.getByText(".fusion/onizleme-ekran.png")).toBeTruthy();
    expect(client.request).toHaveBeenCalledWith("onizleme.ekran_goruntusu", {
      url: "http://localhost:5173/", genislik: 375, yukseklik: 812,
    });

    fireEvent.change(screen.getByRole("combobox", { name: "Ekran görüntüsü teması" }), { target: { value: "dark" } });
    await waitFor(() => expect(client.request).toHaveBeenLastCalledWith("onizleme.ekran_goruntusu", {
      url: "http://localhost:5173/", genislik: 375, yukseklik: 812, tema: "dark",
    }));
  });

  it("hatalı yükte çekirdeğin metnini gösterir", async () => {
    expect(() => decodeScreenshot({ ok: false, metin: "Playwright kurulu değil" })).toThrow("Playwright kurulu değil");
    const client = { request: vi.fn(async () => ({ ok: false, metin: "Sayfa açılamadı: timeout" })) } as unknown as ProtocolClient;
    render(<PreviewScreenshot client={client} onClose={vi.fn()} url="http://localhost:5173/" viewport={findViewport("desktop")} />);
    expect((await screen.findByRole("alert")).textContent).toContain("Sayfa açılamadı");
  });
});

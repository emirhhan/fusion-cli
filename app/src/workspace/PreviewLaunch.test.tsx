import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { PreviewLaunch } from "./PreviewLaunch";

afterEach(cleanup);

const yapilandirmalar = [
  { ad: "web", komut: "npm run dev", url: "http://127.0.0.1:5173/", baglan: false, calisiyor: false },
  { ad: "api", komut: "", url: "http://localhost:8000/", baglan: true, calisiyor: false },
];

function istemci(baslat: Record<string, unknown> = { ok: true, url: "http://127.0.0.1:5173/" }) {
  let calisiyor = false;
  const request = vi.fn(async (name: string) => {
    if (name === "onizleme.yapilandirmalar") {
      return {
        ok: true, kaynak: ".fusion/launch.json",
        yapilandirmalar: yapilandirmalar.map((row) => (row.ad === "web" ? { ...row, calisiyor } : row)),
      };
    }
    if (name === "onizleme.baslat") { calisiyor = baslat.ok === true; return baslat; }
    if (name === "onizleme.durdur") { calisiyor = false; return { ok: true, durduruldu: true }; }
    return { ok: true };
  });
  return { request } as unknown as ProtocolClient & { request: typeof request };
}

describe("PreviewLaunch (launch.json başlatıcı, P-041)", () => {
  it("yapılandırmaları komutuyla listeler, Başlat çekirdeği çağırır ve adresi panele verir", async () => {
    const client = istemci();
    const onStarted = vi.fn();
    render(<PreviewLaunch client={client} onStarted={onStarted} />);

    const secici = await screen.findByRole("combobox", { name: "Dev sunucu yapılandırması" });
    expect(Array.from((secici as HTMLSelectElement).options).map((o) => o.textContent)).toEqual([
      "web — npm run dev", "api — bağlan",
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Başlat" }));

    await waitFor(() => expect(onStarted).toHaveBeenCalledWith("http://127.0.0.1:5173/"));
    expect(client.request).toHaveBeenCalledWith("onizleme.baslat", { ad: "web" });
    // Çalışan komutlu sunucu için düğme Durdur olur.
    await screen.findByRole("button", { name: "Durdur" });
    fireEvent.click(screen.getByRole("button", { name: "Durdur" }));
    await waitFor(() => expect(client.request).toHaveBeenCalledWith("onizleme.durdur", { ad: "web" }));
    await screen.findByRole("button", { name: "Başlat" });
  });

  it("başlatma hatasını çekirdeğin metniyle gösterir, adres açmaz", async () => {
    const client = istemci({ ok: false, metin: "'web' 45 sn içinde yanıt vermedi." });
    const onStarted = vi.fn();
    render(<PreviewLaunch client={client} onStarted={onStarted} />);
    fireEvent.click(await screen.findByRole("button", { name: "Başlat" }));

    expect((await screen.findByRole("alert")).textContent).toContain("yanıt vermedi");
    expect(onStarted).not.toHaveBeenCalled();
  });

  it("launch.json yoksa ya da çekirdek isteği tanımıyorsa hiçbir şey çizmez", async () => {
    const bos = { request: vi.fn(async () => ({ ok: true, kaynak: null, yapilandirmalar: [] })) } as unknown as ProtocolClient;
    const { unmount } = render(<PreviewLaunch client={bos} onStarted={vi.fn()} />);
    await waitFor(() => expect(bos.request).toHaveBeenCalled());
    expect(screen.queryByTestId("preview-launch")).toBeNull();
    unmount();

    const yabanci = { request: vi.fn(async () => ({ ok: false, metin: "Bu dosya türü önizlenemiyor." })) } as unknown as ProtocolClient;
    render(<PreviewLaunch client={yabanci} onStarted={vi.fn()} />);
    await waitFor(() => expect(yabanci.request).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("bozuk launch.json hatasını gösterir", async () => {
    const client = {
      request: vi.fn(async () => ({ ok: false, metin: ".fusion/launch.json geçerli JSON değil", yapilandirmalar: [] })),
    } as unknown as ProtocolClient;
    render(<PreviewLaunch client={client} onStarted={vi.fn()} />);
    expect((await screen.findByRole("alert")).textContent).toContain("geçerli JSON değil");
  });
});

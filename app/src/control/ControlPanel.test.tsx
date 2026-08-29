import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { ControlPanel } from "./ControlPanel";

afterEach(cleanup);

function client() {
  let gateway = "kapali";
  return {
    request: vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "kontrol.durum") return {
        ok: true,
        kok: "/Users/test/Fusion",
        model: { agent: "openrouter/agent", hakem: "openrouter/judge", adaylar: ["model/a", "model/b"], saglayici: "auto", yogunluk: "high" },
        izin: { mod: "ask", kokle_sinirli: false },
        mcp: [{ ad: "github", komut: "npx" }],
        saglayicilar: [
          { id: "openrouter", ad: "OpenRouter", ortam: "OPENROUTER_API_KEY", kurulu: false },
          { id: "nvidia_nim", ad: "NVIDIA NIM", ortam: "NVIDIA_NIM_API_KEY", kurulu: true },
        ],
        sir_deposu_hazir: true,
        gateway: { durum: gateway, adres: "http://127.0.0.1:8787/v1" },
      };
      if (name === "kontrol.gateway_baslat") gateway = "calisiyor";
      if (name === "kontrol.gateway_durdur") gateway = "kapali";
      return { ok: true, ...data, durum: gateway };
    }),
  } as unknown as ProtocolClient;
}

describe("ControlPanel", () => {
  it("model, izin, MCP ve gateway durumunu tek native görünümde gösterir", async () => {
    render(<ControlPanel client={client()} onClose={() => undefined} />);
    expect(await screen.findByText("openrouter/agent")).toBeTruthy();
    expect(screen.getByText("Her işlemde sor")).toBeTruthy();
    expect(screen.getByText("github")).toBeTruthy();
    expect(screen.getByText("http://127.0.0.1:8787/v1")).toBeTruthy();
  });

  it("anahtarı parola alanından kaydeder, değeri ekrana yansıtmaz ve alanı temizler", async () => {
    const fake = client();
    render(<ControlPanel client={fake} onClose={() => undefined} />);
    await screen.findByText("OpenRouter");
    const input = screen.getByLabelText("OpenRouter API anahtarı") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "sk-gizli-test-degeri" } });
    fireEvent.click(screen.getByRole("button", { name: "OpenRouter anahtarını kaydet" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("kontrol.anahtar_kaydet", {
      saglayici: "openrouter", deger: "sk-gizli-test-degeri",
    }));
    expect(input.value).toBe("");
    expect(screen.queryByText("sk-gizli-test-degeri")).toBeNull();
  });

  it("gateway'i başlatıp gerçek durumunu yeniden yükler", async () => {
    const fake = client();
    render(<ControlPanel client={fake} onClose={() => undefined} />);
    const start = await screen.findByRole("button", { name: "Gateway'i başlat" });
    fireEvent.click(start);
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("kontrol.gateway_baslat", {}));
    await waitFor(() => expect(screen.getByText("Çalışıyor")).toBeTruthy());
  });
});

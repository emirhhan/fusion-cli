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
      if (name === "saglayici.katalog") return {
        ok: true,
        saglayicilar: [
          { id: "chatgpt_web", ad: "ChatGPT Web", tur: "web", eylem: "oturum", bagli: false, hesap: "main" },
          { id: "openrouter", ad: "OpenRouter", tur: "anahtar", eylem: "anahtar", bagli: false, ortam: "OPENROUTER_API_KEY" },
        ],
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

  it("sağlayıcı satırına tıklayınca anahtarı parola alanından kaydeder, değeri ekrana yansıtmaz", async () => {
    const fake = client();
    render(<ControlPanel client={fake} onClose={() => undefined} />);
    // Anahtar alanı artık listede AÇIK durmuyor; satıra tıklayınca açılıyor.
    fireEvent.click(await screen.findByRole("button", { name: /OpenRouter/ }));
    const input = (await screen.findByLabelText(/API anahtarı/i)) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "sk-gizli-test-degeri" } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("kontrol.anahtar_kaydet", {
      saglayici: "openrouter", deger: "sk-gizli-test-degeri",
    }));
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

describe("ControlPanel — yönetim derinliği", () => {
  it("model düzenini komut köprüsünden değiştirir; kendi uç noktasını uydurmaz", async () => {
    const onCommand = vi.fn();
    render(<ControlPanel client={client()} onClose={() => undefined} onRunCommand={onCommand} />);
    await screen.findByText("Model düzeni");

    fireEvent.click(screen.getByRole("button", { name: "Ajan modelini değiştir" }));
    expect(onCommand).toHaveBeenCalledWith("/model");

    fireEvent.click(screen.getByRole("button", { name: "Düşünme düzeyini değiştir" }));
    expect(onCommand).toHaveBeenCalledWith("/level");

    fireEvent.click(screen.getByRole("button", { name: "Model profilini değiştir" }));
    expect(onCommand).toHaveBeenCalledWith("/mode");
  });

  it("çalışma klasörünü gösterir ve değiştirmeyi çağırana devreder", async () => {
    const onChangeRoot = vi.fn();
    render(<ControlPanel client={client()} onChangeRoot={onChangeRoot} onClose={() => undefined} />);

    expect(await screen.findByText("/Users/test/Fusion")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Çalışma klasörünü değiştir" }));
    expect(onChangeRoot).toHaveBeenCalled();
  });

  it("değiştirme geri çağrıları verilmediğinde düğmeleri hiç çizmez", async () => {
    render(<ControlPanel client={client()} onClose={() => undefined} />);
    await screen.findByText("Model düzeni");

    expect(screen.queryByRole("button", { name: "Ajan modelini değiştir" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Çalışma klasörünü değiştir" })).toBeNull();
  });
});

describe("ControlPanel — arama ve model ekleme", () => {
  it("arama, eşleşmeyen bölümleri gizler", async () => {
    render(<ControlPanel client={client()} onClose={() => undefined} />);
    await screen.findByText("Model düzeni");
    fireEvent.change(screen.getByRole("searchbox", { name: /panelde ara/i }), {
      target: { value: "gateway" },
    });

    expect(screen.getByText("Yerel Gateway")).toBeTruthy();
    expect(screen.queryByText("MCP sunucuları")).toBeNull();
  });

  it("eşleşme yoksa bunu söyler", async () => {
    render(<ControlPanel client={client()} onClose={() => undefined} />);
    await screen.findByText("Model düzeni");
    fireEvent.change(screen.getByRole("searchbox", { name: /panelde ara/i }), {
      target: { value: "kkkk" },
    });
    expect(screen.getByText(/eşleşen bölüm yok/i)).toBeTruthy();
  });

  it("yeni adayı komut köprüsünden ekler; kendi uç noktasını uydurmaz", async () => {
    const onCommand = vi.fn();
    const fake = client();
    render(<ControlPanel client={fake} onClose={() => undefined} onRunCommand={onCommand} />);
    await screen.findByText("Model düzeni");

    fireEvent.change(screen.getByLabelText("Aday adı"), { target: { value: "hizli" } });
    fireEvent.change(screen.getByLabelText("Model kimliği"), { target: { value: "ollama/q:7b" } });
    fireEvent.click(screen.getByRole("button", { name: "Adayı ekle" }));

    expect(onCommand).toHaveBeenCalledWith("/model add hizli ollama/q:7b");
    // Panel model havuzunu KENDİ yazmaz: protokole doğrudan yazma isteği gitmez.
    expect(fake.request).not.toHaveBeenCalledWith("kontrol.model_ekle", expect.anything());
  });

  it("iki alan da dolmadan ekleme düğmesi çalışmaz", async () => {
    const onCommand = vi.fn();
    render(<ControlPanel client={client()} onClose={() => undefined} onRunCommand={onCommand} />);
    await screen.findByText("Model düzeni");
    fireEvent.change(screen.getByLabelText("Aday adı"), { target: { value: "hizli" } });

    expect((screen.getByRole("button", { name: "Adayı ekle" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Adayı ekle" }));
    expect(onCommand).not.toHaveBeenCalled();
  });

  it("adayı komut köprüsünden çıkarır", async () => {
    const onCommand = vi.fn();
    render(<ControlPanel client={client()} onClose={() => undefined} onRunCommand={onCommand} />);
    await screen.findByText("Model düzeni");
    fireEvent.click(screen.getByRole("button", { name: "model/a adayını çıkar" }));
    expect(onCommand).toHaveBeenCalledWith("/model rm model/a");
  });
});

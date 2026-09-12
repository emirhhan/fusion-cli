import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PermissionBridge } from "../permissions/types";
import type { ProtocolClient } from "../protocol/client";
import { ControlPanel } from "./ControlPanel";

afterEach(cleanup);

function client(ekle: { sirHatasi?: string } = {}) {
  return {
    request: vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "kontrol.durum") return {
        ok: true,
        kok: "/Users/test/Fusion",
        saglayicilar: [
          { id: "openrouter", ad: "OpenRouter", ortam: "OPENROUTER_API_KEY", kurulu: false },
          { id: "nvidia_nim", ad: "NVIDIA NIM", ortam: "NVIDIA_NIM_API_KEY", kurulu: true },
        ],
        sir_deposu_hazir: !ekle.sirHatasi,
        sir_deposu_hatasi: ekle.sirHatasi ?? null,
      };
      if (name === "saglayici.katalog") return {
        ok: true,
        saglayicilar: [
          { id: "chatgpt_web", ad: "ChatGPT Web", tur: "web", eylem: "oturum", bagli: false, hesap: "main" },
          { id: "openrouter", ad: "OpenRouter", tur: "anahtar", eylem: "anahtar", bagli: false, ortam: "OPENROUTER_API_KEY" },
        ],
      };
      return { ok: true, ...data };
    }),
  } as unknown as ProtocolClient;
}

describe("ControlPanel — kapsam", () => {
  /* Panel altı bölüm taşıyordu ve kullanıcının ölçülmüş tepkisi şuydu:
     "kontrol panelindeki mcp alanı ne işe yarıyor", "güncellemeler neden
     kontrol panelinde", "gateway nedir ben bile bilmiyorum". Hepsi ait
     oldukları yerlere taşındı; burada yalnız sağlayıcılar kaldı. */
  it("yalnız sağlayıcıları yönetir; taşınan bölümleri göstermez", async () => {
    render(<ControlPanel client={client()} onClose={() => undefined} />);

    expect(await screen.findByRole("button", { name: /OpenRouter/i })).toBeTruthy();
    for (const gitmis of ["Modeller", "Gateway", "MCP", "Güncellemeler", "İzinler"]) {
      expect(screen.queryByRole("button", { name: gitmis })).toBeNull();
    }
    expect(screen.queryByLabelText("Panelde ara")).toBeNull();
  });

  it("kapatma isteğini iletir", async () => {
    const onClose = vi.fn();
    render(<ControlPanel client={client()} onClose={onClose} />);

    fireEvent.click(await screen.findByRole("button", { name: "Kapat" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  /* Anahtarlık çalışmıyorsa kullanıcı bunu anahtar GİRMEDEN ÖNCE bilmeli;
     yazdığı anahtar kaydedilemeyecek. */
  it("sır deposu hatasını anahtar girilmeden önce gösterir", async () => {
    render(
      <ControlPanel
        client={client({ sirHatasi: "Sistem anahtarlığı kullanılamıyor." })}
        onClose={() => undefined}
      />,
    );

    expect(await screen.findByText("Sistem anahtarlığı kullanılamıyor.")).toBeTruthy();
  });
});

describe("ControlPanel — sağlayıcı anahtarı", () => {
  it("anahtarı parola alanından kaydeder, değeri ekrana yansıtmaz", async () => {
    const fake = client();
    render(<ControlPanel client={fake} onClose={() => undefined} />);

    // Anahtar alanı listede AÇIK durmaz; satıra tıklayınca açılır.
    fireEvent.click(await screen.findByRole("button", { name: /OpenRouter/ }));
    const input = (await screen.findByLabelText(/API anahtarı/i)) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "sk-gizli-test-degeri" } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));

    await waitFor(() =>
      expect(fake.request).toHaveBeenCalledWith("kontrol.anahtar_kaydet", {
        saglayici: "openrouter",
        deger: "sk-gizli-test-degeri",
      }),
    );
    expect(screen.queryByText("sk-gizli-test-degeri")).toBeNull();
  });

  it("anahtar kaydı sistem izin penceresi açmaz", async () => {
    const bridge: PermissionBridge = { request: vi.fn(async () => "denied"), openSettings: vi.fn() };
    render(<ControlPanel client={client()} onClose={() => undefined} permissionBridge={bridge} />);

    fireEvent.click(await screen.findByRole("button", { name: /OpenRouter/i }));
    fireEvent.change(await screen.findByLabelText(/API anahtarı/i), {
      target: { value: "sk-secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    await screen.findByText(/anahtarı kaydedildi/);

    expect(screen.queryByRole("button", { name: "Sistem Ayarlarını Aç" })).toBeNull();
    expect(bridge.request).not.toHaveBeenCalled();
  });
});

describe("ControlPanel — web oturumu", () => {
  it("bekleyen web girişini izler ve kapanınca doğrulamayı sürdürür", async () => {
    const base = client();
    let open = true;
    const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "web.giris") return { ok: true, pid: 42 };
      if (name === "web.giris_durumu") return { ok: true, acik: open };
      return base.request(name, data);
    });
    render(
      <ControlPanel client={{ request } as unknown as ProtocolClient} onClose={() => undefined} />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /ChatGPT Web/i }));
    vi.useFakeTimers();
    try {
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "Oturum aç" }));
      });
      open = false;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500);
      });

      expect(request).toHaveBeenCalledWith("web.baglan", {
        saglayici: "chatgpt_web",
        hesap: "main",
      });
      expect(request).toHaveBeenCalledWith("web.dogrula", {
        saglayici: "chatgpt_web",
        hesap: "main",
      });
    } finally {
      vi.useRealTimers();
    }
  });
});

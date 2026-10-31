import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { UsagePanel } from "./UsagePanel";

afterEach(cleanup);

function client(payload: unknown) {
  return { request: vi.fn(async () => payload) } as unknown as ProtocolClient;
}

describe("UsagePanel", () => {
  it("token ve maliyeti çekirdekten okur", async () => {
    render(
      <UsagePanel
        client={client({
          ok: true,
          kullanim: {
            cagri: 3,
            girdi_token: 1200,
            cikti_token: 800,
            toplam_token: 2000,
            maliyet_usd: 0.0125,
            modeller: [{ model: "openrouter/x", toplam_token: 2000, maliyet_usd: 0.0125 }],
          },
          saglik: [],
        })}
      />,
    );
    // Toplam ve model kırılımı aynı tutarı gösterir; ikisi de bulunmalı.
    expect((await screen.findAllByText("$0.0125")).length).toBe(2);
    expect(screen.getByText(/2\.000 \(1\.200 girdi · 800 çıktı\)/)).toBeTruthy();
  });

  it("sıfır maliyeti model ücretsizmiş gibi yorumlamaz", async () => {
    render(
      <UsagePanel
        client={client({
          ok: true,
          kullanim: {
            cagri: 1,
            girdi_token: 10,
            cikti_token: 10,
            toplam_token: 20,
            maliyet_usd: 0,
            modeller: [],
          },
          saglik: [],
        })}
      />,
    );
    expect(await screen.findByText("Hesaplanan maliyet · $0")).toBeTruthy();
    expect(screen.queryByText(/Ücretsiz modeller/)).toBeNull();
  });

  it("çağrı yokken boş sayı göstermez", async () => {
    render(<UsagePanel client={client({ ok: true, kullanim: { cagri: 0, girdi_token: 0, cikti_token: 0, toplam_token: 0, maliyet_usd: 0, modeller: [] }, saglik: [] })} />);
    expect(await screen.findByText(/henüz model çağrısı yapılmadı/i)).toBeTruthy();
  });

  it("ölçülmüş model sağlığını gösterir", async () => {
    render(
      <UsagePanel
        client={client({
          ok: true,
          kullanim: { cagri: 0, girdi_token: 0, cikti_token: 0, toplam_token: 0, maliyet_usd: 0, modeller: [] },
          saglik: [{ model: "a/b", durum: "sağlıklı", skor: 0.97, ornek: 12, gecikme_ms: 340 }],
        })}
      />,
    );
    expect(await screen.findByText(/sağlıklı · %97 · 340 ms/)).toBeTruthy();
  });

  it("protokol hatasını boş kullanım gibi göstermez ve yeniden dener", async () => {
    const request = vi
      .fn()
      .mockRejectedValueOnce(new Error("bağlantı yok"))
      .mockResolvedValueOnce({
        ok: true,
        kullanim: {
          cagri: 0,
          girdi_token: 0,
          cikti_token: 0,
          toplam_token: 0,
          maliyet_usd: 0,
          modeller: [],
        },
        saglik: [],
      });
    render(<UsagePanel client={{ request } as unknown as ProtocolClient} />);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Kullanım bilgisi alınamadı.",
    );
    expect(screen.queryByText(/henüz model çağrısı yapılmadı/i)).toBeNull();

    screen.getByRole("button", { name: "Yeniden dene" }).click();
    expect(await screen.findByText(/henüz model çağrısı yapılmadı/i)).toBeTruthy();
    expect(request).toHaveBeenCalledTimes(2);
  });
});

// Ölçüldü (31 Ekim, P-066): panel `limitler` alanını okumuyordu; "sağlayıcı beni bekletiyor mu" görünmüyordu.
describe("UsagePanel hız sınırları ve kota", () => {
  it("kota bekleten modeli ve ayarlı dakikalık sınırı gösterir", async () => {
    render(
      <UsagePanel
        client={client({
          ok: true,
          kullanim: { cagri: 0, girdi_token: 0, cikti_token: 0, toplam_token: 0, maliyet_usd: 0, modeller: [] },
          saglik: [],
          limitler: {
            dakikaLimitleri: [{ saglayici: "nvidia_nim", dakikaLimiti: 40 }],
            kotaBekleyen: [{ model: "nim/llama", seri: 2, yenidenSn: 90 }],
          },
        })}
      />,
    );
    expect(await screen.findByText("nim/llama")).toBeTruthy();
    expect(screen.getByText(/90 sn sonra yeniden/)).toBeTruthy();
    expect(screen.getByText(/40 istek\/dk/)).toBeTruthy();
  });

  it("eski çekirdek limit göndermezse hata vermez ve 'bekletmiyor' der", async () => {
    render(
      <UsagePanel
        client={client({
          ok: true,
          kullanim: { cagri: 0, girdi_token: 0, cikti_token: 0, toplam_token: 0, maliyet_usd: 0, modeller: [] },
          saglik: [],
        })}
      />,
    );
    expect(await screen.findByText("Şu an hiçbir sağlayıcı kota bekletmiyor.")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

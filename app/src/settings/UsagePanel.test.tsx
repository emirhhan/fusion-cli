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

  /* Ölçüldü (31 Ekim): `gecmis`/`atif` alanları için test yoktu; günlük kapalıyken
     bölümler sessizce gizleniyor, kullanıcıya nedeni söylenmiyordu. */
  const bos = { cagri: 0, girdi_token: 0, cikti_token: 0, toplam_token: 0, maliyet_usd: 0, modeller: [] };

  it("kalıcı günlükten son dönem ve kim harcadı bölümlerini gösterir", async () => {
    render(
      <UsagePanel
        client={client({
          ok: true,
          kullanim: bos,
          saglik: [],
          gunluk_acik: true,
          gecmis: [
            { pencere: "son 24 saat", cagri: 4, toplam_token: 1500, maliyet_usd: 0.02, maliyet_tam: true },
            { pencere: "son 7 gün", cagri: 9, toplam_token: 3000, maliyet_usd: 0.05, maliyet_tam: false },
          ],
          atif: {
            pencere: "son 7 gün",
            kaynaklar: [{ ad: "alt ajan", cagri: 2, toplam_token: 400, maliyet_usd: 0.01 }],
            mcp: [{ ad: "github", cagri: 3 }],
            beceriler: [{ ad: "pdf", cagri: 1 }],
          },
        })}
      />,
    );
    expect(await screen.findByText("Son dönem")).toBeTruthy();
    expect(screen.getByText("son 24 saat")).toBeTruthy();
    expect(screen.getByText("en az $0.0500")).toBeTruthy();
    expect(screen.getByText("Kim harcadı (son 7 gün)")).toBeTruthy();
    expect(screen.getByText("MCP · github")).toBeTruthy();
    expect(screen.getByText("Beceri · pdf")).toBeTruthy();
    expect(screen.queryByText(/günlüğü kapalı/)).toBeNull();
  });

  it("günlük kapalıysa nedenini ve nasıl açılacağını söyler", async () => {
    render(<UsagePanel client={client({ ok: true, kullanim: bos, saglik: [], gunluk_acik: false })} />);
    expect(await screen.findByText(/Kullanım günlüğü kapalı/)).toBeTruthy();
    expect(screen.getByText(/runtime\.usage_log/)).toBeTruthy();
    expect(screen.queryByText("Son dönem")).toBeNull();
  });

  it("eski çekirdek gunluk_acik göndermezse kapalı notu çıkmaz", async () => {
    render(<UsagePanel client={client({ ok: true, kullanim: bos, saglik: [] })} />);
    expect(await screen.findByText(/henüz model çağrısı yapılmadı/i)).toBeTruthy();
    expect(screen.queryByText(/Kullanım günlüğü kapalı/)).toBeNull();
  });
});

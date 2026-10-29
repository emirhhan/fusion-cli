import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { useAccount } from "./useAccount";

const GIRDI = { kullanici_adi: "kullanici", eposta: "e@ornek.com", parola: "parola1234", avatar: "" };

function istemci(kayitYaniti: Record<string, unknown>) {
  let etkin = "";
  const request = vi.fn(async (ad: string) => {
    if (ad === "hesap.durum") return { ok: true, hesaplar: [], etkin, kurulum_gerekli: etkin === "" };
    if (ad === "hesap.kayit") { etkin = "1"; return kayitYaniti; }
    return { ok: true };
  });
  return { client: { request } as unknown as ProtocolClient, request };
}

describe("useAccount.kayit", () => {
  // Ölçüldü (29 Ekim, U5-30): kayıt sonrası durum tazelenince `etkin` doluyor ve giriş kapısı
  // kalkıyordu; kod yalnız kapının kendi durumunda olduğundan kurtarma ekranı hiç çizilmiyordu.
  it("kurtarma kodunu, durum tazelenip etkin dolmadan önce saklar", async () => {
    const { client } = istemci({ ok: true, hesap: { kimlik: "1" }, kurtarma_kodu: "ABCD-EFGH", devralinan_ayarlar: [] });
    const { result } = renderHook(() => useAccount(client));
    await waitFor(() => expect(result.current.yukleniyor).toBe(false));

    await act(async () => { await result.current.kayit(GIRDI); });

    expect(result.current.durum?.etkin).toBe("1");
    expect(result.current.kurtarmaKodu).toBe("ABCD-EFGH");
  });

  it("kurtarma kodu eksik/boş gelirse sessiz kalmaz, hata bildirir", async () => {
    const { client } = istemci({ ok: true, hesap: { kimlik: "1" }, kurtarma_kodu: "  " });
    const { result } = renderHook(() => useAccount(client));
    await waitFor(() => expect(result.current.yukleniyor).toBe(false));

    let sonuc: unknown = "bekliyor";
    await act(async () => { sonuc = await result.current.kayit(GIRDI); });

    expect(sonuc).toBeNull();
    expect(result.current.kurtarmaKodu).toBeNull();
    expect(result.current.hata).toContain("kurtarma kodu alınamadı");
  });
});

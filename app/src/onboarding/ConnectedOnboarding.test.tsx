import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { ConnectedOnboarding } from "./ConnectedOnboarding";

afterEach(() => { cleanup(); localStorage.clear(); });
function navigate(count: number) { for (let index = 0; index < count; index++) fireEvent.click(screen.getByRole("button", { name: "İleri" })); }
function draw(request: (name: string) => Promise<Record<string, unknown>>) {
  return render(<ConnectedOnboarding client={{ request } as unknown as ProtocolClient} projects={[]} onFinish={vi.fn()} />);
}
describe("Bağımsız onboarding otoriteleri", () => {
  it("provider bağlantısı mevcut formu açar ve aynı adıma döner", async () => {
    draw(async (name) => name === "saglayici.katalog" ? { ok: true, saglayicilar: [{ id: "openai", ad: "OpenAI", bagli: false, eylem: "anahtar", tur: "anahtar" }] } : { ok: true, model: {}, saglayicilar: [{ id: "openai", ad: "OpenAI", kurulu: false }] });
    navigate(3);
    fireEvent.click(await screen.findByRole("button", { name: "Bağlan" }));
    expect(await screen.findByLabelText(/API anahtarı/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Kapat" }));
    expect(await screen.findByRole("heading", { name: "Sağlayıcı durumu" })).toBeTruthy();
  });
  it("reset transport hatasında önceki model kalır", async () => {
    draw(async (name) => {
      if (name === "kontrol.cirak_varsayilanina_don") throw new Error("Reset bağlantısı kapandı.");
      return { ok: true, model: { cirak_aktif: false } };
    });
    navigate(3);
    fireEvent.click(await screen.findByRole("button", { name: "Ücretsiz çırağa dön" }));
    expect(await screen.findByText(/Reset bağlantısı kapandı/)).toBeTruthy();
    expect(screen.getByText("Kullanılmıyor")).toBeTruthy();
  });
  it("eski client sonucu yeni provider durumunu değiştirmez", async () => {
    let resolveOld!: (payload: Record<string, unknown>) => void;
    const previous = { request: vi.fn(async (name: string) => name === "kontrol.durum" ? new Promise<Record<string, unknown>>((resolve) => { resolveOld = resolve; }) : { ok: true }) } as unknown as ProtocolClient;
    const next = { request: vi.fn(async () => ({ ok: true, model: {}, saglayicilar: [{ id: "new", ad: "Yeni sağlayıcı", kurulu: true }] })) } as unknown as ProtocolClient;
    const { rerender } = render(<ConnectedOnboarding client={previous} projects={[]} onFinish={vi.fn()} />);
    navigate(3);
    rerender(<ConnectedOnboarding client={next} projects={[]} onFinish={vi.fn()} />);
    await screen.findByText("Yeni sağlayıcı");
    await act(async () => resolveOld({ ok: true, model: { cirak_aktif: true }, saglayicilar: [{ id: "old", ad: "Eski sağlayıcı", kurulu: true }] }));
    expect(screen.queryByText("Eski sağlayıcı")).toBeNull();
    expect(screen.getByText("Yeni sağlayıcı")).toBeTruthy();
  });
  it("reset ok:false modeli korur ve retry reset isteğini yineler", async () => {
    const request = vi.fn(async (name: string) => name === "kontrol.cirak_varsayilanina_don" ? { ok: false, metin: "Çırak değişimi reddedildi." } : { ok: true, model: { cirak_aktif: false, onerilen_cirak: "test/model" } });
    draw(request); navigate(3);
    fireEvent.click(await screen.findByRole("button", { name: "Ücretsiz çırağa dön" }));
    await screen.findByText(/Çırak değişimi reddedildi/);
    expect(screen.getByText("Kullanılmıyor")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Yeniden dene" }));
    await waitFor(() => expect(request.mock.calls.filter(([name]) => name === "kontrol.cirak_varsayilanina_don")).toHaveLength(2));
  });
  it("projesiz ilerleme yeniden bağlanınca restore edilir", () => {
    const request = async () => ({ ok: true });
    const first = draw(request); navigate(2); first.unmount();
    draw(request);
    expect(screen.getByRole("heading", { name: /Kaynaklar/ })).toBeTruthy();
    expect(localStorage.getItem("fusion.onboarding.progress.v1")).toBe(JSON.stringify({ version: 1, step: "sources", selectedProjectId: null }));
  });
  it("kontrol reddedilse de başarılı history kaynağını korur", async () => {
    draw(async (name) => { if (name === "kontrol.durum") throw new Error("Kontrol bağlantısı yok."); return { ok: true, kaynaklar: [{ ad: "codex" }] }; });
    navigate(2);
    expect(await screen.findByText("Bulundu")).toBeTruthy();
    expect(screen.queryByText("1 öğe")).toBeNull();
  });
  it("eksik apprentice boolean ve yalnız yapılandırılmış anahtarı doğrulanmış saymaz", async () => {
    draw(async () => ({ ok: true, model: {}, saglayicilar: [{ id: "openai", ad: "OpenAI", kurulu: true }] }));
    navigate(3);
    await screen.findByText("OpenAI");
    expect(screen.queryByText("Etkin")).toBeNull();
    expect(screen.queryByText("Hazır")).toBeNull();
    expect(screen.getByText(/Yapılandırıldı.*doğrulanmadı/i)).toBeTruthy();
  });
  it("fulfilled başarısız history nedenini boş keşif yerine sunar", async () => {
    draw(async (name) => name === "gecmis.kaynaklar" ? { ok: false, metin: "Kaynak taraması reddedildi." } : { ok: true, model: {} });
    navigate(2);
    expect(await screen.findByText(/Kaynak taraması reddedildi/)).toBeTruthy();
  });
  it("bekleyen reset tek request başlatır", async () => {
    const request = vi.fn(async (name: string) => {
      if (name === "kontrol.cirak_varsayilanina_don") return new Promise<Record<string, unknown>>(() => undefined);
      return { ok: true, model: { cirak_aktif: false } };
    });
    draw(request); navigate(3);
    const reset = await screen.findByRole("button", { name: "Ücretsiz çırağa dön" });
    fireEvent.click(reset); fireEvent.click(reset);
    expect(request.mock.calls.filter(([name]) => name === "kontrol.cirak_varsayilanina_don")).toHaveLength(1);
  });
});

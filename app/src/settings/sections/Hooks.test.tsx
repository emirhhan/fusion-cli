import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../../protocol/client";
import { HookList, type HookRow } from "./Hooks";

function client(payload: Record<string, unknown>) {
  const request = vi.fn(async () => ({ ok: true, kullanici_dosyasi: "/ev/.config/fusion-cli/hooks.json", ...payload }));
  return { request } as unknown as ProtocolClient & { request: ReturnType<typeof vi.fn> };
}

const satir: HookRow = { olay: "PreToolUse", eslestirici: "Bash", komut: "~/bin/denetle", sure_sn: 30, kaynak: "kullanici", dosya: "/ev/.claude/settings.json", atlandi: "" };

afterEach(cleanup);

describe("HookList — kanca listesi (P-009)", () => {
  it("kancaları olay · eşleştirici · komut · kaynak ile listeler; atlananı gerekçesiyle gösterir", async () => {
    const fake = client({
      kancalar: [satir, { ...satir, olay: "Stop", eslestirici: "", komut: "depo-kancasi", sure_sn: null, kaynak: "proje", atlandi: "proje güvenilmiyor (fusion trust)" }],
      guvensiz_katmanlar: ["proje"],
    });
    render(<HookList client={fake} />);
    await waitFor(() => expect(screen.getByText("~/bin/denetle")).toBeTruthy());
    expect(fake.request).toHaveBeenCalledWith("kanca.listele", {});
    const tablo = within(screen.getByRole("table"));
    expect(tablo.getByText("Claude (kullanıcı) · 30 sn")).toBeTruthy();
    expect(tablo.getByText("tümü")).toBeTruthy();
    expect(tablo.getByText(/atlandı: proje güvenilmiyor/)).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("Proje");
  });

  it("kanca yoksa nereye ekleneceğini, kapalıysa nedenini söyler", async () => {
    render(<HookList client={client({ kancalar: [], kapali: "runtime.hooks_enabled: false" })} />);
    await waitFor(() => expect(screen.getByText(/Tanımlı kanca yok/)).toBeTruthy());
    expect(screen.getByText("/ev/.config/fusion-cli/hooks.json")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("runtime.hooks_enabled: false");
  });

  it("güvenilmeyen depodaki disableAllHooks'un yok sayıldığını söyler", async () => {
    render(<HookList client={client({ kancalar: [satir], yok_sayilan_kapatma: ["proje"] })} />);
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("disableAllHooks yok sayıldı (Proje)"));
  });

  it("anahtarlarla kancaları ve Claude kancalarını açıp kapatır", async () => {
    const request = vi.fn(async (name: string, data?: Record<string, unknown>) =>
      name === "kanca.ayar"
        ? { ok: true, kancalar: [satir], etkin: true, claude_kancalari: data?.deger === true }
        : { ok: true, kancalar: [satir], etkin: true, claude_kancalari: false });
    render(<HookList client={{ request } as unknown as ProtocolClient} />);
    const claude = await screen.findByRole("switch", { name: "Claude Code kancalarını da çalıştır" });
    expect((claude as HTMLInputElement).checked).toBe(false);
    fireEvent.click(claude);
    await waitFor(() => expect(request).toHaveBeenCalledWith("kanca.ayar", { anahtar: "claude_hooks", deger: true }));
    await waitFor(() => expect((screen.getByRole("switch", { name: "Claude Code kancalarını da çalıştır" }) as HTMLInputElement).checked).toBe(true));
  });

  it("ayar yazılamazsa nedenini gösterir", async () => {
    const request = vi.fn(async (name: string) =>
      name === "kanca.ayar" ? { ok: false, metin: "disk dolu" } : { ok: true, kancalar: [], etkin: true, claude_kancalari: false });
    render(<HookList client={{ request } as unknown as ProtocolClient} />);
    fireEvent.click(await screen.findByRole("switch", { name: "Kancaları çalıştır" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Kanca ayarı değiştirilemedi: disk dolu"));
  });

  it("çekirdek hatasını Türkçe gösterir", async () => {
    const request = vi.fn(async () => { throw new Error("bağlantı koptu"); });
    render(<HookList client={{ request } as unknown as ProtocolClient} />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Kancalar okunamadı: bağlantı koptu"));
  });
});

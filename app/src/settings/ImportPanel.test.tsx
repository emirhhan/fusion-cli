import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { ImportPanel } from "./ImportPanel";
import { ReleaseNotesPanel } from "./ReleaseNotesPanel";

afterEach(cleanup);

it("kaynağı önizler ve yalnız eklenecekleri uygular", async () => {
  let uygulandi = false;
  const request = vi.fn(async (name: string) => {
    if (name === "ice_aktar.onizle") return {
      ok: true, kaynak: "codex", eklenecek: uygulandi ? 0 : 1, uyarilar: [],
      ogeler: [
        { tur: "mcp", ad: "figma", durum: uygulandi ? "zaten var" : "eklenecek", ayrinti: "http https://mcp.figma.com/mcp", dosya: "~/.codex/config.toml" },
        { tur: "talimat", ad: "AGENTS.md", durum: "zaten okunuyor", ayrinti: "", dosya: "~/.codex/AGENTS.md" },
      ],
    };
    if (name === "ice_aktar.uygula") { uygulandi = true; return { ok: true, uygulanan: 1, hatalar: [], yazilan: [] }; }
    return { ok: false };
  });
  render(<ImportPanel client={{ request } as unknown as ProtocolClient} />);
  fireEvent.click(screen.getByRole("button", { name: "Codex" }));
  expect(await screen.findByText("figma")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "İçe aktar (1)" }));
  await waitFor(() => expect(request).toHaveBeenCalledWith("ice_aktar.uygula", { kaynak: "codex" }));
  expect(await screen.findByText(/İçe aktarıldı: 1 öğe/)).toBeTruthy();
  expect(await screen.findByRole("button", { name: "Yeni bir şey yok" })).toBeTruthy();
});

it("sunucu ok:false ve metin döndürünce başarı bildirimi yerine hata gösterir", async () => {
  const request = vi.fn(async (name: string) => {
    if (name === "ice_aktar.onizle") return { ok: true, kaynak: "claude", eklenecek: 1, uyarilar: [], ogeler: [{ tur: "mcp", ad: "x", durum: "eklenecek", ayrinti: "", dosya: "" }] };
    return { ok: false, metin: "Bilinmeyen kaynak: claude" };
  });
  render(<ImportPanel client={{ request } as unknown as ProtocolClient} />);
  fireEvent.click(screen.getByRole("button", { name: "Claude Code" }));
  fireEvent.click(await screen.findByRole("button", { name: "İçe aktar (1)" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Bilinmeyen kaynak");
  expect(screen.queryByText(/İçe aktarıldı/)).toBeNull();
});

it("sürüm notlarını gösterir ve bölüm seçer", async () => {
  const request = vi.fn(async (_name: string, data: Record<string, unknown>) => ({
    ok: true, kurulu: "0.7.18", metin: data.surum ? `## ${String(data.surum)}\n- eski` : "## Yayımlanmamış\n- yeni",
    bolumler: [{ baslik: "Yayımlanmamış", surum: "", tarih: "" }, { baslik: "0.7.18 — 2026-10-21", surum: "0.7.18", tarih: "2026-10-21" }],
  }));
  render(<ReleaseNotesPanel client={{ request } as unknown as ProtocolClient} />);
  expect((await screen.findByLabelText("Sürüm notu metni")).textContent).toContain("yeni");
  expect(screen.getByText(/Kurulu sürüm: 0.7.18/)).toBeTruthy();
  fireEvent.change(screen.getByRole("combobox", { name: "Sürüm notu bölümü" }), { target: { value: "0.7.18" } });
  await waitFor(() => expect(screen.getByLabelText("Sürüm notu metni").textContent).toContain("eski"));
});

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { TrustProject, trustMatters } from "./TrustProject";

function client(durum: Record<string, unknown>) {
  const request = vi.fn(async (name: string) => {
    if (name === "proje.guven_durum") return durum;
    if (name === "proje.guven_ver") return { ...durum, ok: true, guvenildi: true };
    return { ok: true };
  });
  return { request } as unknown as ProtocolClient & { request: ReturnType<typeof vi.fn> };
}

const guvensiz = {
  ok: true,
  guvenildi: false,
  neden: "proje için güven kaydı yok",
  dusurulen_bolumler: ["mcp_servers"],
  yok_sayilan_dosyalar: [".claude/settings.local.json"],
  yuklenmeyen_araclar: 0,
};

afterEach(cleanup);

describe("TrustProject — güvenilmeyen proje şeridi (P-012)", () => {
  it("düşürülen ayar yoksa hiçbir şey çizmez", async () => {
    const fake = client({ ...guvensiz, dusurulen_bolumler: [], yok_sayilan_dosyalar: [] });
    const { container } = render(<TrustProject client={fake} kok="/proje-a" />);
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("proje.guven_durum", {}));
    expect(container.querySelector(".trust-project")).toBeNull();
    expect(trustMatters({ guvenildi: true, neden: "", dusurulen_bolumler: ["x"], yok_sayilan_dosyalar: [], yuklenmeyen_araclar: 0 })).toBe(false);
  });

  it("düşürülen ayarları sayar ve 'Evet, güven' proje.guven_ver gönderir", async () => {
    const fake = client(guvensiz);
    const onTrusted = vi.fn();
    render(<TrustProject client={fake} kok="/proje-b" onTrusted={onTrusted} />);
    const serit = await screen.findByRole("note", { name: "Proje güveni" });
    expect(serit.textContent).toContain("mcp_servers, .claude/settings.local.json");
    expect(serit.textContent).toContain("proje için güven kaydı yok");
    fireEvent.click(screen.getByRole("button", { name: "Evet, güven" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("proje.guven_ver", {}));
    await waitFor(() => expect(onTrusted).toHaveBeenCalled());
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("'Şimdilik kapat' aynı kökte bir daha göstermez; tur sürerken güven düğmesi kapalıdır", async () => {
    const fake = client(guvensiz);
    const view = render(<TrustProject client={fake} kok="/proje-c" running />);
    await screen.findByRole("note", { name: "Proje güveni" });
    expect((screen.getByRole("button", { name: "Evet, güven" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Önce çalışan görevi durdur.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Şimdilik kapat" }));
    expect(screen.queryByRole("note")).toBeNull();
    view.unmount();
    render(<TrustProject client={client(guvensiz)} kok="/proje-c" />);
    await waitFor(() => expect(screen.queryByRole("note")).toBeNull());
  });
});

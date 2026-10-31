import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../../protocol/client";
import { SandboxCard, type SandboxStatus } from "./SandboxCard";

const durum: SandboxStatus = {
  ok: true,
  acik: true,
  platform: "macOS (sandbox-exec)",
  kullanilabilir: true,
  neden: "",
  ag: "allowlist",
  izinli_alanlar: ["github.com"],
  yasak_alanlar: ["gist.github.com"],
  localhost: true,
  ek_yazma: [],
  okuma_engeli: ["~/.ssh", "~/.aws"],
  zorunlu: false,
  disari_izinli: true,
  oto_izin: false,
  disari_komutlar: [],
  sir_ortami_gizli: true,
};

function client(ilk: Partial<SandboxStatus> = {}, ayarla?: (veri: Record<string, unknown>) => unknown) {
  const request = vi.fn(async (name: string, veri: Record<string, unknown>) => {
    if (name === "sandbox.durum") return { ...durum, ...ilk };
    if (name === "sandbox.ayarla") return ayarla ? ayarla(veri) : { ...durum, ...ilk };
    return { ok: true };
  });
  return { request } as unknown as ProtocolClient & { request: ReturnType<typeof vi.fn> };
}

afterEach(cleanup);

describe("SandboxCard — kabuk sandbox'ı (P-010)", () => {
  it("durumu, alan adlarını ve okuma engelini gösterir; kaldırma isteğini gönderir", async () => {
    const fake = client();
    render(<SandboxCard client={fake} />);
    await waitFor(() => expect(screen.getByText("Kabuk sandbox'ı")).toBeTruthy());
    expect(screen.getByText("macOS (sandbox-exec)")).toBeTruthy();
    const liste = within(screen.getByRole("list", { name: "Alan adları" }));
    expect(liste.getByText("github.com")).toBeTruthy();
    expect(liste.getByText("Yasak")).toBeTruthy();
    expect(screen.getByText("Okunamayan yollar (2)")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "github.com alan adını kaldır" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("sandbox.ayarla", { islem: "kaldir", deger: "github.com" }));
  });

  it("aç/kapat, ağ kipi ve bayraklar doğru eylemle gider", async () => {
    const fake = client({ ag: "open" });
    render(<SandboxCard client={fake} />);
    await waitFor(() => expect(screen.getByRole("switch", { name: "Sandbox'ı aç" })).toBeTruthy());
    fireEvent.click(screen.getByRole("switch", { name: "Sandbox'ı aç" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("sandbox.ayarla", { islem: "kapat", deger: "" }));
    fireEvent.click(screen.getByRole("button", { name: /Yalnız izinli alan adları/ }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("sandbox.ayarla", { islem: "ag", deger: "allowlist" }));
    fireEvent.click(screen.getByRole("switch", { name: "Sandbox içindeki komutları sormadan çalıştır" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("sandbox.ayarla", { islem: "oto", deger: true }));
    // Ağ açıkken alan adı listesi gösterilmez.
    expect(screen.queryByRole("list", { name: "Alan adları" })).toBeNull();
  });

  it("alan adı ekler; çekirdeğin Türkçe hatasını gösterir", async () => {
    const fake = client({}, (veri) => (veri.deger === "a b" ? { ok: false, metin: "Geçerli bir alan adı değil: 'a b'" } : durum));
    render(<SandboxCard client={fake} />);
    await waitFor(() => expect(screen.getByLabelText("Alan adı")).toBeTruthy());
    fireEvent.change(screen.getByLabelText("Alan adı kararı"), { target: { value: "engelle" } });
    fireEvent.change(screen.getByLabelText("Alan adı"), { target: { value: " evil.test " } });
    fireEvent.click(screen.getByRole("button", { name: "Alan adı ekle" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("sandbox.ayarla", { islem: "engelle", deger: "evil.test" }));
    fireEvent.change(screen.getByLabelText("Alan adı"), { target: { value: "a b" } });
    fireEvent.click(screen.getByRole("button", { name: "Alan adı ekle" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Geçerli bir alan adı değil"));
  });

  it("ayar yanıtındaki notları gösterir; sır ve localhost anahtarları doğru eylemle gider", async () => {
    const fake = client({}, (veri) => ({
      ...durum,
      notlar: veri.islem === "localhost" ? ["Ağ kipi allowlist'e geçti: yalnız github.com"] : [],
    }));
    render(<SandboxCard client={fake} />);
    await waitFor(() => expect(screen.getByRole("switch", { name: "Sır ortam değişkenlerini gizle" })).toBeTruthy());
    fireEvent.click(screen.getByRole("switch", { name: "Sır ortam değişkenlerini gizle" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("sandbox.ayarla", { islem: "sir", deger: false }));
    fireEvent.click(screen.getByRole("switch", { name: "localhost'a izin ver" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("sandbox.ayarla", { islem: "localhost", deger: false }));
    await waitFor(() => expect(screen.getByText(/allowlist'e geçti/)).toBeTruthy());
  });

  it("ağ açıkken sorusuz çalıştırma açıksa etkisiz olduğunu uyarır", async () => {
    render(<SandboxCard client={client({ ag: "open", oto_izin: true })} />);
    await waitFor(() => expect(screen.getByText(/Ağ açıkken etkisiz/)).toBeTruthy());
  });

  it("kurulamayan sandbox'ta nedeni uyarı olarak gösterir", async () => {
    render(<SandboxCard client={client({ kullanilabilir: false, neden: "bubblewrap (bwrap) bulunamadı" })} />);
    await waitFor(() => expect(screen.getByText(/Kurulamaz: bubblewrap/)).toBeTruthy());
  });

  it("eski çekirdek durum vermezse kart hiç çizilmez", async () => {
    const request = vi.fn(async () => ({ ok: true }));
    const { container } = render(<SandboxCard client={{ request } as unknown as ProtocolClient} />);
    await waitFor(() => expect(request).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("varsayılan okuma engelinden açılan yolları gösterir", async () => {
    render(<SandboxCard client={client({ okuma_izni: ["~/.kube"] })} />);
    await waitFor(() => expect(screen.getByText("Okunamayan yollar (2)")).toBeTruthy());
    expect(screen.getByText(/Varsayılan engelden bilerek açılanlar/)).toBeTruthy();
    expect(screen.getByText("~/.kube")).toBeTruthy();
  });
});

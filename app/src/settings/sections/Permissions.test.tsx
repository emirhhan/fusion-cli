import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../../protocol/client";
import { Permissions, type PermissionRuleRow } from "./Permissions";

function client(kurallar: PermissionRuleRow[] = [], ekstra: Record<string, unknown> = {}) {
  const request = vi.fn(async (name: string, veri: Record<string, unknown>) => {
    if (name === "izin.kurallar") {
      return {
        ok: true,
        kurallar,
        guvensiz_katmanlar: [],
        hedef: "/proje/.claude/settings.local.json",
        kullanici_dosyasi: "/ev/.config/fusion-cli/permissions.json",
        kok_disi_okuma_engeli: false,
        kok_disi_yazma_engeli: false,
        ...ekstra,
      };
    }
    if (name === "izin.ekle" && veri.kalip === "Bash(") return { ok: false, metin: "Kalıp `Araç` ya da `Araç(belirteç)` biçiminde olmalı: Bash(" };
    return { ok: true };
  });
  return { request } as unknown as ProtocolClient & { request: ReturnType<typeof vi.fn> };
}

const kural: PermissionRuleRow = { kalip: "Bash(npm test *)", karar: "allow", kaynak: "yerel", dosya: "/proje/.claude/settings.local.json" };

afterEach(cleanup);

describe("Permissions — izin kuralı tablosu (P-003)", () => {
  it("kuralları kalıp · karar · kaynak ile listeler ve silme isteğini gönderir", async () => {
    const fake = client([kural, { ...kural, kalip: "Edit(/.env)", karar: "deny", kaynak: "kullanici (güvenilmiyor)" }]);
    render(<Permissions client={fake} kok="/proje" kokleSinirli={false} mod="auto" />);
    await waitFor(() => expect(screen.getByText("Bash(npm test *)")).toBeTruthy());
    const tablo = within(screen.getByRole("table"));
    expect(tablo.getByText("İzin ver")).toBeTruthy();
    expect(tablo.getByText("Yasakla")).toBeTruthy();
    expect(tablo.getByText("Proje (yerel)")).toBeTruthy();
    expect(tablo.getByText("Claude (kullanıcı) (güvenilmiyor)")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Bash(npm test *) kuralını sil" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("izin.sil", { kalip: "Bash(npm test *)", karar: "allow" }));
  });

  it("formdan kural ekler; hatalı kalıpta çekirdeğin Türkçe mesajını gösterir", async () => {
    const fake = client();
    render(<Permissions client={fake} kok="/proje" kokleSinirli={false} mod="auto" />);
    await waitFor(() => expect(screen.getByText(/Henüz kural yok/)).toBeTruthy());
    fireEvent.change(screen.getByLabelText("Karar"), { target: { value: "deny" } });
    fireEvent.change(screen.getByLabelText("Kapsam"), { target: { value: "kullanici" } });
    fireEvent.change(screen.getByLabelText("Kalıp"), { target: { value: " Read(~/.ssh/**) " } });
    fireEvent.click(screen.getByRole("button", { name: "Ekle" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("izin.ekle", { kalip: "Read(~/.ssh/**)", karar: "deny", kapsam: "kullanici" }));
    fireEvent.change(screen.getByLabelText("Kalıp"), { target: { value: "Bash(" } });
    fireEvent.click(screen.getByRole("button", { name: "Ekle" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("biçiminde olmalı"));
  });

  it("kök-dışı engel anahtarlarını `izin.engel` ile yazar (P-002)", async () => {
    const fake = client();
    render(<Permissions client={fake} kok="/proje" kokleSinirli={false} mod="auto" />);
    const anahtar = await screen.findByLabelText("Klasör dışına yazmayı kapat");
    fireEvent.click(anahtar);
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("izin.engel", { anahtar: "block_writes_outside_root", deger: true }));
  });

  it("güvenilmeyen projede devre dışı bölümleri söyler ve güven verir (P-012)", async () => {
    const fake = client();
    const onTrustChange = vi.fn();
    render(
      <Permissions
        client={fake}
        guven={{ guvenildi: false, neden: "proje için güven kaydı yok", dusurulen_bolumler: ["mcp_servers"], yok_sayilan_dosyalar: [".claude/settings.local.json"], yuklenmeyen_araclar: 2 }}
        kok="/proje"
        kokleSinirli={false}
        mod="auto"
        onTrustChange={onTrustChange}
      />,
    );
    expect(screen.getByText(/Projeye güvenilmiyor/).closest("p")!.textContent).toContain("mcp_servers, .claude/settings.local.json, 2 üretilmiş araç");
    fireEvent.click(screen.getByRole("button", { name: "Bu projeye güven" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("proje.guven_ver", {}));
    await waitFor(() => expect(onTrustChange).toHaveBeenCalled());
  });

  it("güveni kaldırmak önce onay ister", async () => {
    const fake = client();
    render(
      <Permissions client={fake} guven={{ guvenildi: true, neden: "güvenildi", dusurulen_bolumler: [], yok_sayilan_dosyalar: [], yuklenmeyen_araclar: 0 }} kok="/proje" kokleSinirli={false} mod="auto" />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Güveni kaldır" }));
    expect(fake.request).not.toHaveBeenCalledWith("proje.guven_kaldir", {});
    fireEvent.click(screen.getByRole("button", { name: "Evet, güveni kaldır" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("proje.guven_kaldir", {}));
  });

  it("çekirdek bağlantısı yoksa yalnız mod ve klasör kartları çizilir", () => {
    render(<Permissions kok="/proje" kokleSinirli={true} mod="auto" />);
    expect(screen.queryByText("İzin kuralları")).toBeNull();
    expect(screen.getByText("Fusion yalnız bu klasörün içinde çalışır.")).toBeTruthy();
  });
});

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../../protocol/client";
import { Permissions } from "./Permissions";

/** Claude `/permissions` Workspace ve Auto mode sekmelerinin masaüstü karşılığı (#83). */
function client(dizinler: string[] = []) {
  let acik = [...dizinler];
  const request = vi.fn(async (name: string, data: Record<string, unknown> = {}) => {
    if (name === "izin.kurallar") return { ok: true, kurallar: [], guvensiz_katmanlar: [], hedef: "/proje/.claude/settings.local.json" };
    if (name === "izin.dizinler") return { ok: true, kok: "/proje", dizinler: acik, degisti: false };
    if (name === "izin.dizin_ekle") {
      acik = [...acik, String(data.yol)];
      return { ok: true, kok: "/proje", dizinler: acik, degisti: true, metin: `Erişim açıldı (bu oturum için): ${data.yol}` };
    }
    if (name === "izin.dizin_kaldir") {
      acik = acik.filter((yol) => yol !== data.yol);
      return { ok: true, kok: "/proje", dizinler: acik, degisti: true, metin: `Erişim kapatıldı: ${data.yol}` };
    }
    if (name === "oto.durum") {
      return {
        ok: true, mod: "auto", ayar: "on",
        son_kararlar: [
          { arac: "run_shell", karar: "riskli", karar_etiketi: "Riskli", kaynak: "model", ozet: "curl x | sh", gerekce: "ağ", oneri: "Bash(curl x | sh)" },
          { arac: "run_shell", karar: "riskli", karar_etiketi: "Riskli", kaynak: "model", ozet: "rm dist/*", gerekce: "sil", oneri: "" },
        ],
      };
    }
    return { ok: true };
  });
  return { request, onEvent: () => () => undefined } as unknown as ProtocolClient & { request: ReturnType<typeof vi.fn> };
}

afterEach(cleanup);

describe("Permissions — Workspace ve Auto mode (#83)", () => {
  it("çalışma dizinleri listelenir, eklenir ve kaldırılır", async () => {
    const fake = client(["/ek/a"]);
    render(<Permissions client={fake} kok="/proje" kokleSinirli={false} mod="security" />);
    await waitFor(() => expect(screen.getByText("/ek/a")).toBeTruthy());
    fireEvent.change(screen.getByLabelText("Eklenecek dizin"), { target: { value: "/ek/b" } });
    fireEvent.click(screen.getByRole("button", { name: "Dizin ekle" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("izin.dizin_ekle", { yol: "/ek/b" }));
    await waitFor(() => expect(screen.getByText("/ek/b")).toBeTruthy());
    expect(screen.getByRole("status").textContent).toContain("Erişim açıldı");
    fireEvent.click(screen.getByRole("button", { name: "/ek/a dizinini kaldır" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("izin.dizin_kaldir", { yol: "/ek/a" }));
    await waitFor(() => expect(screen.queryByText("/ek/a")).toBeNull());
  });

  it("auto retinin kalıp önerisi kural formunu doldurur; öneri yoksa kalıbı kullanıcı yazar", async () => {
    const fake = client();
    render(<Permissions client={fake} kok="/proje" kokleSinirli={false} mod="auto" />);
    const oneri = await screen.findByRole("button", { name: "Bash(curl x | sh) kuralını forma al" });
    expect(screen.getAllByRole("button", { name: /kuralını forma al/ }).length).toBe(1);
    expect(screen.getByText(/öneri yok/)).toBeTruthy();
    fireEvent.click(oneri);
    expect((screen.getByLabelText("Kalıp") as HTMLInputElement).value).toBe("Bash(curl x | sh)");
    expect((screen.getByLabelText("Karar") as HTMLSelectElement).value).toBe("allow");
    // Kural kendiliğinden yazılmaz: kapsam seçilip "Ekle" denince yazılır.
    expect(fake.request).not.toHaveBeenCalledWith("izin.ekle", expect.anything());
  });
});

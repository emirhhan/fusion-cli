import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../../protocol/client";
import { setAutoPolicyDisabled } from "../../sessions/autoGate";
import { Permissions } from "./Permissions";

function client() {
  const request = vi.fn(async (name: string) => {
    if (name === "izin.kurallar") {
      return {
        ok: true,
        kurallar: [],
        guvensiz_katmanlar: [],
        hedef: "/proje/.claude/settings.local.json",
        paylasilan_dosyasi: "/proje/.claude/settings.json",
        kullanici_dosyasi: "/ev/.claude/settings.json",
      };
    }
    return { ok: true };
  });
  return { request } as unknown as ProtocolClient & { request: ReturnType<typeof vi.fn> };
}

afterEach(() => {
  cleanup();
  act(() => setAutoPolicyDisabled(false));
});

describe("Permissions — Claude kapsamları ve disableAutoMode (#83, #85)", () => {
  it("kural paylaşılan proje dosyasına (.claude/settings.json) eklenebilir", async () => {
    const fake = client();
    render(<Permissions client={fake} kok="/proje" kokleSinirli={false} mod="security" />);
    await waitFor(() => expect(screen.getByText("/proje/.claude/settings.json")).toBeTruthy());
    fireEvent.change(screen.getByLabelText("Kapsam"), { target: { value: "paylasilan" } });
    fireEvent.change(screen.getByLabelText("Kalıp"), { target: { value: "Bash(npm test *)" } });
    fireEvent.click(screen.getByRole("button", { name: "Ekle" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("izin.ekle", { kalip: "Bash(npm test *)", karar: "allow", kapsam: "paylasilan" }));
  });

  it("ayar auto'yu kapattıysa Çalışma modu listesinde auto görünmez", () => {
    act(() => setAutoPolicyDisabled(true));
    const { container } = render(<Permissions kok="/proje" kokleSinirli={false} mod="security" onSelectMode={vi.fn()} />);
    const auto = container.querySelector<HTMLButtonElement>("button.settings__choice[hidden]");
    expect(auto?.textContent).toContain("Otomatik");
  });
});

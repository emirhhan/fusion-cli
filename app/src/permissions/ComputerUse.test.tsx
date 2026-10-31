import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ComputerUse } from "./ComputerUse";

afterEach(cleanup);

function client(durum: Record<string, unknown> = {}) {
  const calls: { name: string; data: Record<string, unknown> }[] = [];
  const state = { accessibility: "denied", screen_recording: "denied", platform: "macos", ...durum };
  return {
    calls,
    request: vi.fn(async (name: string, data: Record<string, unknown>) => {
      calls.push({ name, data });
      if (name === "izin.masaustu_iste") {
        state[data.tur as string] = "granted";
        return { ok: true, ...state };
      }
      return { ok: true, ...state };
    }),
  };
}

describe("ComputerUse", () => {
  it("durumu çekirdekten okur ve eksik izinler için eylem sunar", async () => {
    const api = client();
    render(<ComputerUse client={api} permissionBridge={{ openSettings: vi.fn().mockResolvedValue(undefined) }} />);

    await waitFor(() => expect(screen.getAllByRole("status")).toHaveLength(2));
    expect(api.calls[0]?.name).toBe("izin.masaustu_durum");
    expect(screen.getByText("Erişilebilirlik")).toBeTruthy();
    expect(screen.getAllByText("Verilmedi")).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "İzin iste" })).toHaveLength(2);
  });

  it("izin isteği çekirdeğe tür ile gider ve durum yenilenir", async () => {
    const api = client();
    render(<ComputerUse client={api} permissionBridge={{ openSettings: vi.fn().mockResolvedValue(undefined) }} />);
    await waitFor(() => expect(screen.getAllByRole("button", { name: "İzin iste" })).toHaveLength(2));

    fireEvent.click(screen.getAllByRole("button", { name: "İzin iste" })[0]);

    await waitFor(() => expect(screen.getByText("Verildi")).toBeTruthy());
    expect(api.calls.some((c) => c.name === "izin.masaustu_iste" && c.data.tur === "accessibility")).toBe(true);
    expect(screen.getAllByRole("button", { name: "İzin iste" })).toHaveLength(1);
  });

  it("Sistem Ayarları bağlantısı Tauri köprüsünden ilgili türle açılır", async () => {
    const openSettings = vi.fn().mockResolvedValue(undefined);
    render(<ComputerUse client={client({ accessibility: "granted" })} permissionBridge={{ openSettings }} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Sistem Ayarlarını Aç" })).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "Sistem Ayarlarını Aç" }));

    expect(openSettings).toHaveBeenCalledWith("screenRecording");
    expect(screen.getByText(/yeniden açman gerekebilir/)).toBeTruthy();
  });

  it("macOS dışında açık bir not gösterir, buton sunmaz", async () => {
    render(<ComputerUse client={client({ platform: "linux", accessibility: "unsupported", screen_recording: "unsupported" })} permissionBridge={{ openSettings: vi.fn() }} />);

    await waitFor(() => expect(screen.getByText(/yalnız macOS/)).toBeTruthy());
    expect(screen.queryByRole("button", { name: "İzin iste" })).toBeNull();
  });
});

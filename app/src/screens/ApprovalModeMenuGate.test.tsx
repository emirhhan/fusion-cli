import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { modlariOku } from "../sessions/useSessionModes";
import { autoPolicyDisabled, setAutoPolicyDisabled } from "../sessions/autoGate";
import { APPROVAL_MODES, ApprovalModeMenu, nextApprovalMode } from "./ApprovalModeMenu";

afterEach(() => {
  cleanup();
  act(() => setAutoPolicyDisabled(false));
});

describe("ApprovalModeMenu — Claude kapsamı ve disableAutoMode (#53, #85)", () => {
  it("acceptEdits ipucu Claude'un dosya komutlarını söyler", () => {
    const hint = APPROVAL_MODES.find((item) => item.id === "edits")?.hint ?? "";
    expect(hint).toContain("mkdir, touch, rm, rmdir, mv, cp, sed");
    expect(hint).toContain("öteki komutları sorar");
  });

  it("oturum.durum auto_kapali gelince auto menüden ve döngüden çıkar", () => {
    modlariOku({ mod: "security", auto_kapali: true });
    expect(autoPolicyDisabled()).toBe(true);
    render(<ApprovalModeMenu mode="security" onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /İzin modu: Manuel/ }));
    expect(screen.queryByRole("menuitemradio", { name: /Otomatik/ })).toBeNull();
    // auto gizli; bypass da Ayarlar anahtarı kapalıyken listelenmez (#442).
    expect(screen.getAllByRole("menuitemradio").length).toBe(APPROVAL_MODES.length - 2);
    for (const mode of ["security", "edits", "plan"] as const) {
      expect(nextApprovalMode(mode)).not.toBe("auto");
    }
  });

  it("alan yoksa kapı değişmez; false gelince auto geri gelir", () => {
    act(() => setAutoPolicyDisabled(true));
    modlariOku({ mod: "security" });
    expect(autoPolicyDisabled()).toBe(true);
    act(() => { modlariOku({ auto_kapali: false }); });
    render(<ApprovalModeMenu mode="security" onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /İzin modu: Manuel/ }));
    expect(screen.getByRole("menuitemradio", { name: /Otomatik/ })).toBeTruthy();
  });
});

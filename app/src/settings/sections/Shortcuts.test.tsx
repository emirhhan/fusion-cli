import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../../protocol/client";
import { KEYMAP_CHANGED_EVENT } from "../../shortcuts/useAppShortcuts";
import { Shortcuts } from "./Shortcuts";

const listing = (baglar: Record<string, string>) => ({
  ok: true, yol: "/ev/.fusion/keybindings.json", baglar, uyarilar: ["masaustu.k: mod, ctrl ya da alt ile birlikte olmalı"],
  eylemler: [{ ad: "palet", etiket: "Komut paletini aç" }, { ad: "terminal", etiket: "Terminali aç/kapat" }],
});

afterEach(cleanup);

function client(handler: (name: string, data: Record<string, unknown>) => unknown) {
  return { request: vi.fn(async (name: string, data: Record<string, unknown>) => handler(name, data)) } as unknown as ProtocolClient & { request: ReturnType<typeof vi.fn> };
}

describe("Ayarlar › Kısayollar", () => {
  it("bağları, dosya yolunu ve uyarıları gösterir", async () => {
    render(<Shortcuts client={client(() => listing({ "mod+k": "palet", "mod+j": "terminal" }))} />);
    expect(await screen.findByText("Komut paletini aç")).toBeTruthy();
    expect(screen.getByText("/ev/.fusion/keybindings.json")).toBeTruthy();
    expect(screen.getByText(/masaustu\.k/)).toBeTruthy();
  });

  it("yeni tuşu kaydeder, sistem tuşunu reddeder, değişikliği yayınlar", async () => {
    const fake = client((name) => name === "kisayol.ata" ? listing({ "mod+k": "palet", "mod+shift+t": "terminal" }) : listing({ "mod+k": "palet", "mod+j": "terminal" }));
    const changed = vi.fn();
    window.addEventListener(KEYMAP_CHANGED_EVENT, changed);
    render(<Shortcuts client={fake} />);
    fireEvent.click(await screen.findByRole("button", { name: "Terminali aç/kapat kısayolunu değiştir" }));
    // jsdom macOS değildir: Ctrl = mod. Ctrl+C sistem kısayoludur, kaydedilmez; tek Shift beklenir.
    const capture = screen.getByRole("button", { name: /yeni tuşa bas/ });
    fireEvent.keyDown(capture, { key: "c", code: "KeyC", ctrlKey: true });
    expect(screen.getByRole("alert").textContent).toMatch(/bağlanamaz/);
    fireEvent.keyDown(capture, { key: "Shift", code: "ShiftLeft", shiftKey: true });
    expect(fake.request).not.toHaveBeenCalledWith("kisayol.ata", expect.anything());
    fireEvent.keyDown(capture, { key: "T", code: "KeyT", ctrlKey: true, shiftKey: true });
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("kisayol.ata", { eylem: "terminal", tus: "mod+shift+t" }));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    window.removeEventListener(KEYMAP_CHANGED_EVENT, changed);
  });

  it("dolu tuşta sorar; Taşı zorla gönderir", async () => {
    const fake = client((name, data) => {
      if (name === "kisayol.ata" && !data.zorla) return { ok: false, cakisma: "palet", metin: "dolu" };
      if (name === "kisayol.ata") return listing({ "mod+k": "terminal" });
      return listing({ "mod+k": "palet", "mod+j": "terminal" });
    });
    render(<Shortcuts client={fake} />);
    fireEvent.click(await screen.findByRole("button", { name: "Terminali aç/kapat kısayolunu değiştir" }));
    fireEvent.keyDown(screen.getByRole("button", { name: /yeni tuşa bas/ }), { key: "k", code: "KeyK", ctrlKey: true });
    const dialog = await screen.findByRole("alertdialog", { name: "Kısayol çakışması" });
    expect(dialog.textContent).toMatch(/Komut paletini aç/);
    fireEvent.click(screen.getByRole("button", { name: "Taşı" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("kisayol.ata", expect.objectContaining({ zorla: true })));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(screen.getByRole("row", { name: /Terminali aç\/kapat/ }).textContent).toMatch(/Ctrl\+K/);
  });

  it("devredilmiş tuşu varsayılana döndürürken sorar; Taşı zorla sıfırlar", async () => {
    // Ölçüldü (31 Ekim): çekirdek sessizce ok:true dönüyordu; artık çakışma ve tuş döner.
    const fake = client((name, data) => {
      if (name === "kisayol.sifirla" && !data.zorla) return { ok: false, cakisma: "terminal", tus: "mod+n", metin: "dolu" };
      if (name === "kisayol.sifirla") return listing({ "mod+n": "yeni_sohbet" });
      return listing({ "mod+n": "terminal" });
    });
    render(<Shortcuts client={fake} />);
    fireEvent.click(await screen.findByRole("button", { name: "Yeni sohbet kısayolunu varsayılana döndür" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Kısayol çakışması" });
    expect(dialog.textContent).toMatch(/Ctrl\+N zaten “Terminali aç\/kapat”/);
    fireEvent.click(screen.getByRole("button", { name: "Taşı" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("kisayol.sifirla", { eylem: "yeni_sohbet", zorla: true }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(screen.getByRole("row", { name: /Yeni sohbet/ }).textContent).toMatch(/Ctrl\+N/);
  });

  it("Esc kaydı iptal eder; Kaldır ve Tümünü varsayılana döndür istek atar", async () => {
    const fake = client(() => listing({ "mod+k": "palet", "mod+j": "terminal" }));
    render(<Shortcuts client={fake} />);
    fireEvent.click(await screen.findByRole("button", { name: "Terminali aç/kapat kısayolunu değiştir" }));
    fireEvent.keyDown(screen.getByRole("button", { name: /yeni tuşa bas/ }), { key: "Escape", code: "Escape" });
    expect(screen.queryByRole("button", { name: /yeni tuşa bas/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Terminali aç/kapat kısayolunu kaldır" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("kisayol.kaldir", { eylem: "terminal" }));
    fireEvent.click(screen.getByRole("button", { name: "Tümünü varsayılana döndür" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("kisayol.sifirla", {}));
  });
});

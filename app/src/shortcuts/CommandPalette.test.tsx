import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CommandPalette } from "./CommandPalette";
import { RECENT_KEY, type PaletteItem } from "./paletteItems";

const items = (): PaletteItem[] => [
  { id: "eylem:yeni", kind: "eylem", label: "Yeni sohbet", shortcut: "⌘N", run: vi.fn() },
  { id: "eylem:terminal", kind: "eylem", label: "Terminali aç/kapat", shortcut: "⌘J", run: vi.fn() },
  { id: "sohbet:s1", kind: "sohbet", label: "Dünkü hata", detail: "proje", run: vi.fn() },
];

afterEach(() => { cleanup(); localStorage.clear(); vi.useRealTimers(); });

describe("CommandPalette", () => {
  it("odağı alır, süzer ve Enter ile seçileni çalıştırıp kapanır", () => {
    const list = items(), onClose = vi.fn();
    render(<CommandPalette initialQuery="" items={list} onClose={onClose} />);
    const input = screen.getByRole("combobox", { name: /ara/ });
    expect(document.activeElement).toBe(input);
    fireEvent.change(input, { target: { value: "term" } });
    expect(screen.getAllByRole("option")).toHaveLength(1);
    expect(screen.getByText("⌘J")).toBeTruthy();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(list[1].run).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
    expect(JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]")).toEqual(["eylem:terminal"]);
  });

  it("oklarla gezer, Esc kapatır, eşleşme yoksa söyler", () => {
    const list = items(), onClose = vi.fn();
    render(<CommandPalette initialQuery="" items={list} onClose={onClose} />);
    const input = screen.getByRole("combobox");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(screen.getAllByRole("option")[2].getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(screen.getAllByRole("option")[0].getAttribute("aria-selected")).toBe("true");
    fireEvent.change(input, { target: { value: "zzzz" } });
    expect(screen.getByRole("status").textContent).toMatch(/Eşleşen/);
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("dosyaları bekletip arar; eski sorgunun cevabı yenisini ezmez", async () => {
    vi.useFakeTimers();
    const open = vi.fn();
    const searchFiles = vi.fn(async (text: string) => [
      { id: `dosya:${text}.py`, kind: "dosya" as const, label: `${text}.py`, detail: `src/${text}.py`, run: open },
    ]);
    render(<CommandPalette initialQuery="@" items={items()} onClose={vi.fn()} searchFiles={searchFiles} />);
    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "@ap" } });
    fireEvent.change(input, { target: { value: "@app" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(200); });
    expect(searchFiles).toHaveBeenCalledTimes(1);
    expect(searchFiles).toHaveBeenCalledWith("app");
    expect(screen.getByText("app.py")).toBeTruthy();
    fireEvent.click(screen.getByText("app.py"));
    expect(open).toHaveBeenCalled();
  });
});

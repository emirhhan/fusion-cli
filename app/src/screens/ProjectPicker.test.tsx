import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectPicker } from "./ProjectPicker";
afterEach(cleanup);
const projects = [{ root: "/work/oyun", name: "Oyun", updatedAt: 1 }];
describe("ProjectPicker", () => {
  it("proje arar ve gerçek kökü seçer", async () => {
    const select = vi.fn().mockResolvedValue(undefined);
    render(<ProjectPicker root="/Users/test/Desktop" projects={projects} onSelect={select} onNew={vi.fn()} onSettings={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Proje seç: Desktop" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Proje ara" }), { target: { value: "oyun" } });
    fireEvent.click(screen.getByRole("button", { name: "Oyun" }));
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "Proje ara" })).toBeNull());
    expect(select).toHaveBeenCalledWith("/work/oyun");
  });
  it("proje açılamazsa hatayı gösterir ve menüyü korur", async () => {
    render(<ProjectPicker root="/Users/test/Desktop" projects={projects} onSelect={vi.fn().mockRejectedValue(new Error("failed"))} onNew={vi.fn()} onSettings={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Proje seç: Desktop" }));
    fireEvent.click(screen.getByRole("button", { name: "Oyun" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Proje ara" })).toBeTruthy();
  });
  it("klasör seçimi ve ayarlara bağlanır", () => {
    const create = vi.fn(); const settings = vi.fn();
    render(<ProjectPicker root="/Users/test/Desktop" projects={[]} onSelect={vi.fn()} onNew={create} onSettings={settings} />);
    fireEvent.click(screen.getByRole("button", { name: "Proje seç: Desktop" }));
    fireEvent.click(screen.getByRole("button", { name: "Yeni proje / klasör seç" }));
    expect(create).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Proje seç: Desktop" }));
    fireEvent.click(screen.getByRole("button", { name: "Proje ayarları" }));
    expect(settings).toHaveBeenCalledOnce();
  });
});

it("Escape arama alanını kapatıp odağı proje düğmesine döndürür", () => {
  render(<ProjectPicker root="/Users/test/Desktop" projects={[]} onSelect={vi.fn()} onNew={vi.fn()} onSettings={vi.fn()} />);
  const trigger = screen.getByRole("button", { name: "Proje seç: Desktop" });
  fireEvent.click(trigger);
  expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "Proje ara" }));
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(screen.queryByRole("textbox", { name: "Proje ara" })).toBeNull();
  expect(document.activeElement).toBe(trigger);
});

it("mevcut proje seçildiğinde odağı tetikleyiciye döndürür", () => {
  render(<ProjectPicker root="/Users/test/Desktop" projects={[]} onSelect={vi.fn()} onNew={vi.fn()} onSettings={vi.fn()} />);
  const trigger = screen.getByRole("button", { name: "Proje seç: Desktop" });
  fireEvent.click(trigger);
  fireEvent.click(screen.getByRole("button", { name: "Desktop" }));
  expect(screen.queryByRole("textbox", { name: "Proje ara" })).toBeNull();
  expect(document.activeElement).toBe(trigger);
});

it("başarılı proje seçiminden sonra odağı tetikleyiciye döndürür", async () => {
  render(<ProjectPicker root="/Users/test/Desktop" projects={projects} onSelect={vi.fn().mockResolvedValue(undefined)} onNew={vi.fn()} onSettings={vi.fn()} />);
  const trigger = screen.getByRole("button", { name: "Proje seç: Desktop" });
  fireEvent.click(trigger);
  fireEvent.click(screen.getByRole("button", { name: "Oyun" }));
  await waitFor(() => expect(screen.queryByRole("textbox", { name: "Proje ara" })).toBeNull());
  expect(document.activeElement).toBe(trigger);
});

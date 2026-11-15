import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NewTaskDialog } from "./NewTaskDialog";

afterEach(cleanup);

describe("NewTaskDialog", () => {
  it("delegates the user-triggered folder action to the centralized App gate", () => {
    const onFolder = vi.fn();
    render(<NewTaskDialog onCancel={vi.fn()} onChat={vi.fn()} onFolder={onFolder} open />);

    fireEvent.click(screen.getByRole("button", { name: "Klasörde kod görevi" }));
    expect(onFolder).toHaveBeenCalledOnce();
  });
  it("sohbet ve klasörde kod görevi seçeneklerini açıkça sunar", () => {
    render(<NewTaskDialog onCancel={vi.fn()} onChat={vi.fn()} onFolder={vi.fn()} open />);

    expect(screen.getByRole("dialog", { name: "Yeni görev" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sohbet başlat" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Klasörde kod görevi" })).toBeTruthy();
  });

  it("seçimi yalnız bir kez bildirir ve Escape ile kapanır", () => {
    const onChat = vi.fn();
    const onCancel = vi.fn();
    const { rerender } = render(
      <NewTaskDialog onCancel={onCancel} onChat={onChat} onFolder={vi.fn()} open />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Sohbet başlat" }));
    expect(onChat).toHaveBeenCalledOnce();

    rerender(<NewTaskDialog onCancel={onCancel} onChat={onChat} onFolder={vi.fn()} open />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledOnce();
  });

  // Ölçüldü (30 Ekim, U4-20): busy iken Vazgeç/Esc/arka plan kapalıydı; yerel seçici kaybolursa çıkış yoktu.
  it("klasör seçici beklerken de Vazgeç, Esc ve arka plan tıklaması çalışır", () => {
    const onCancel = vi.fn();
    render(<NewTaskDialog busy onCancel={onCancel} onChat={vi.fn()} onFolder={vi.fn()} open />);

    const vazgec = screen.getByRole("button", { name: "Vazgeç" }) as HTMLButtonElement;
    expect(vazgec.disabled).toBe(false);
    fireEvent.click(vazgec);
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.mouseDown(document.querySelector(".new-task-backdrop") as Element);

    expect(onCancel).toHaveBeenCalledTimes(3);
    expect((screen.getByRole("button", { name: "Sohbet başlat" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Klasörde kod görevi" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

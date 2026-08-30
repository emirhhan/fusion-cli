import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NewTaskDialog } from "./NewTaskDialog";

afterEach(cleanup);

describe("NewTaskDialog", () => {
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
});

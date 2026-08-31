import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PermissionBridge } from "../permissions/types";
import { NewTaskDialog } from "./NewTaskDialog";

afterEach(cleanup);

describe("NewTaskDialog", () => {
  it("opens the folder picker only after the user grants workspace access", async () => {
    let grant!: (state: "granted") => void;
    const bridge: PermissionBridge = {
      request: vi.fn(() => new Promise((resolve) => { grant = resolve; })),
      openSettings: vi.fn(),
    };
    const onFolder = vi.fn();
    render(<NewTaskDialog permissionBridge={bridge} onCancel={vi.fn()} onChat={vi.fn()} onFolder={onFolder} open />);

    fireEvent.click(screen.getByRole("button", { name: "Klasörde kod görevi" }));
    expect(onFolder).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Devam et/i }));
    grant("granted");

    await waitFor(() => expect(onFolder).toHaveBeenCalledOnce());
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
});

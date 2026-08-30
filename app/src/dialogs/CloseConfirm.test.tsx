import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CloseConfirm } from "./CloseConfirm";

afterEach(cleanup);

describe("CloseConfirm", () => {
  it("odağı VAZGEÇ'e verir; yanlışlıkla Enter kapatmasın", () => {
    render(<CloseConfirm onCancel={vi.fn()} onConfirm={vi.fn()} />);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Vazgeç" }));
  });

  it("çalışan tur varsa uyarıyı sertleştirir", () => {
    render(<CloseConfirm onCancel={vi.fn()} onConfirm={vi.fn()} running />);
    expect(screen.getByText(/yarım kalır/i)).toBeTruthy();
  });

  it("Escape vazgeçer, kapatmaz", () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(<CloseConfirm onCancel={onCancel} onConfirm={onConfirm} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

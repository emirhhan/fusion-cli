import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DeepLinkConfirm } from "./DeepLinkConfirm";

afterEach(cleanup);

describe("DeepLinkConfirm (fusion://yeni kök onayı, P-064)", () => {
  it("klasörü gösterir, odağı Vazgeç'e verir; Escape vazgeçer, açmaz", () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(<DeepLinkConfirm kok="/Users/ali/proje" onCancel={onCancel} onConfirm={onConfirm} />);

    expect(screen.getByText("/Users/ali/proje")).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Vazgeç" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("Sohbeti aç onaylar", () => {
    const onConfirm = vi.fn();
    render(<DeepLinkConfirm kok="/Users/ali/proje" onCancel={vi.fn()} onConfirm={onConfirm} />);
    fireEvent.click(screen.getByRole("button", { name: "Sohbeti aç" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
